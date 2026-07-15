"""FastAPI application: SSE research stream, literature search, library,
writing-studio tools, settings, uploads, refinement, static UI.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .hy3_client import Hy3Client
from .models import (
    Language,
    PaperChatRequest,
    RefineRequest,
    ResearchRequest,
    ResearchTask,
    SmartSearchRequest,
    SourceDocument,
    Style,
    TaskStatus,
    ToolRequest,
)
from . import prompts
from .pipeline import ResearchPipeline
from . import retrieval_tool
from .search import gather_sources, search_literature, search_literature_iter
from .store import PaperDoc, UploadedDoc, store
from . import features as feature_store
from . import feedback as feedback_store

app = FastAPI(title="Hy3 Research Studio", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# 思路提炼进行多轮后给出的『收敛提示』：避免对话无穷无尽、尽快收口成可执行的方案
CONVERGE_HINT = (
    "提示：我们已经讨论多轮，请在这一轮收敛——直接给出『建议的研究问题 + 1~2 条可证伪假设』"
    "以及『最小验证实验（方法 / 数据 / 指标 / 基线）』，并提示用户可点『生成指南』把结论固化。"
    "不要再抛一堆开放式反问，让思考向前推进并收口；若信息不足，只问最关键的 1 个问题。"
)

# 寒暄 / 致谢 / 极短消息不触发检索，避免无意义的文献检索
_GREET_RE = re.compile(
    r"^(你好|您好|hi|hello|hey|嗨|谢谢|感谢|多谢|好的|好|ok|okay|yes|对|嗯|恩|可以|行|没问题|"
    r"明白|收到|继续|了解|thanks|thx|辛苦了|赞|棒)\b",
    re.I,
)


def _advisor_wants_retrieval(message: str) -> bool:
    """判断本轮思路对话是否需要检索真实文献。

    策略（对齐『除简单问题外，凡专业相关都必须检索以确保真实性』）：
    - 简单问题（寒暄 / 致谢 / 极短消息 / 纯闲聊）返回 False，不检索；
    - 其余任何与专业 / 学术相关的提问都返回 True，由 agent 先调用
      ``retrieve_papers`` 检索真实文献再作答。
    """
    m = (message or "").strip()
    if not m or len(m) <= 2:
        return False
    if _GREET_RE.match(m):
        return False
    return True


# 中文（CJK）检测：用于判断检索式是否需要改写为英文
_CJK_RE = re.compile(r"[一-鿿]")


def _is_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _build_search_query(client, message: str, language: str) -> str:
    """把用户问题重构为英文检索式。

    学术文献库（OpenAlex / Crossref / arXiv / Semantic Scholar）以英文索引为主，
    中文检索式召回质量差、易命中无关语料（如『压缩』匹配到图像/视频压缩）。
    故统一用英文关键词检索；当用户意在了解领域/现状/空白时末尾加 survey/review。
    失败时回退为原消息（由下游检索逻辑兜底）。
    """
    if not settings.is_configured:
        return message
    sys = (
        "You convert a user's research question into a short English academic search query "
        "for a paper database. Rules: ① keep only 2-5 core English keywords, never a full sentence; "
        "② if the user wants to understand a FIELD/DIRECTION/STATE-OF-THE-ART/RESEARCH GAP, "
        "append 'survey' or 'review'; ③ for a specific method/dataset/model question, do NOT add survey/review. "
        "Output ONLY the query string, no quotes, no explanation."
    )
    try:
        q = client.chat(
            [{"role": "system", "content": sys},
             {"role": "user", "content": f"User question ({language}): {message}"}],
            temperature=0.2,
        ).strip().strip('"').strip("'")
        if q:
            return q
    except Exception:  # noqa: BLE001
        pass
    return message


# --- helpers -----------------------------------------------------------------
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_client() -> Hy3Client:
    try:
        return Hy3Client()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


def _sources_block(docs: list[SourceDocument]) -> str:
    lines = []
    for d in docs:
        content = d.snippet or d.abstract
        lines.append(f"[{d.source_id}] {d.title} ({d.venue or ''} {d.year or ''})\n{content}")
    return "\n\n".join(lines) if lines else ""


# --- API ---------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "configured": settings.is_configured,
        "model": settings.model,
        "base_url": settings.base_url,
    }


@app.get("/api/settings")
def get_settings() -> dict:
    cfg = store.get_settings()
    return {
        "configured": settings.is_configured,
        "model": settings.model,
        "base_url": settings.base_url,
        "defaults": {
            "depth": cfg.get("depth", "standard"),
            "style": cfg.get("style", "academic"),
            "language": cfg.get("language", "zh"),
            "sources": cfg.get("sources", settings.default_sources),
            "task_type": cfg.get("task_type", "literature_review"),
            "cite_count": cfg.get("cite_count", 0),
        },
        "profile": cfg.get("profile", {}),
        "source_status": {
            "openalex": "已启用（免 Key）",
            "crossref": "已启用（免 Key）",
            "arxiv": "已启用（免 Key）",
            "semantic_scholar": "已配置 Key" if settings.s2_api_key else "未配置（可选增强）",
        },
    }


@app.post("/api/settings")
def post_settings(body: dict) -> dict:
    cfg = store.get_settings()
    for k in ("depth", "style", "language", "sources", "task_type", "cite_count"):
        if k in body:
            cfg[k] = body[k]
    if isinstance(body.get("profile"), dict):
        prof = dict(cfg.get("profile") or {})
        prof.update(body["profile"])
        # 研究兴趣去重并去空
        interests = prof.get("interests")
        if isinstance(interests, list):
            seen: list[str] = []
            for it in interests:
                s = str(it).strip()
                if s and s not in seen:
                    seen.append(s)
            prof["interests"] = seen
        cfg["profile"] = prof
    store.save_settings(cfg)
    return {"ok": True, "defaults": cfg, "profile": cfg.get("profile", {})}


@app.get("/api/search")
def api_search(
    q: str,
    sources: str = "openalex,crossref,arxiv",
    limit: int = 20,
    year: Optional[int] = None,
    page: int = 1,
    oa: bool = False,
    doc_type: Optional[str] = None,
) -> dict:
    srcs = [s.strip() for s in sources.split(",") if s.strip()]
    doc_type = doc_type if doc_type in ("article", "preprint", "book") else None
    results = search_literature(q, srcs, limit, year, page, oa, doc_type)
    store.add_search_history(q, "search")
    return {"results": results, "count": len(results), "page": page}


@app.get("/api/search/stream")
def api_search_stream(
    q: str,
    sources: str = "openalex,crossref,arxiv",
    limit: int = 20,
    year: Optional[int] = None,
    page: int = 1,
    oa: bool = False,
    doc_type: Optional[str] = None,
) -> StreamingResponse:
    srcs = [s.strip() for s in sources.split(",") if s.strip()]
    doc_type = doc_type if doc_type in ("article", "preprint", "book") else None
    store.add_search_history(q, "search")

    def gen():
        try:
            for event, payload in search_literature_iter(q, srcs, limit, year, page, oa, doc_type):
                yield _sse(event, payload)
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 首页「为您推荐」：跨若干热点方向检索近 2 年文献，去重后返回若干最新且高相关的结果。
_RECO_TOPICS = [
    "large language models",
    "diffusion models",
    "retrieval augmented generation",
    "graph neural networks",
]
# 推荐结果缓存（多主题并行检索较慢，缓存 5 分钟显著降低延迟）
_RECO_CACHE: dict = {"ts": 0.0, "data": None, "key": ""}
_RECO_TTL = 300


@app.get("/api/recommend")
def api_recommend(limit: int = 6) -> dict:
    now = time.time()
    # 检索主题种子：结合 level2 用户卡片（长期兴趣）+ level1 最近检索，
    # 无画像时回退到默认热门主题，保证界面不空。
    card = build_user_card()
    seeds: list[str] = []
    for k in card["keywords"][:4]:
        if k not in seeds:
            seeds.append(k)
    for q in card["recent_activity"][:2]:
        if q not in seeds:
            seeds.append(q)
    topics = seeds[:4] if seeds else _RECO_TOPICS

    # 缓存键随主题变化失效（画像更新后及时刷新推荐）
    cache_key = hashlib.md5(("|".join(topics)).encode()).hexdigest()
    if _RECO_CACHE.get("key") == cache_key and _RECO_CACHE["data"] is not None and now - _RECO_CACHE["ts"] < _RECO_TTL:
        return _RECO_CACHE["data"]

    year = datetime.now().year - 2
    out: list[dict] = []
    seen: set[str] = set()

    def _fetch(t: str) -> list[dict]:
        try:
            return search_literature(t, ["openalex", "crossref", "arxiv"], limit=4, year=year, page=1)
        except Exception:  # noqa: BLE001
            return []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(topics)) as ex:
            for res in ex.map(_fetch, topics):
                for r in res:
                    key = re.sub(r"[^a-z0-9]", "", (r.get("title") or "").lower())[:60]
                    if key and key not in seen:
                        seen.add(key)
                        out.append(r)
                if len(out) >= limit:
                    break
    except Exception:  # noqa: BLE001
        pass
    payload = {"results": out[:limit], "count": len(out[:limit])}
    _RECO_CACHE["key"] = cache_key
    _RECO_CACHE["data"] = payload
    _RECO_CACHE["ts"] = now
    return payload


@app.post("/api/search/smart/stream")
def api_smart_search(req: SmartSearchRequest) -> StreamingResponse:
    client = _get_client()
    store.add_search_history(req.topic, "smart")

    def gen():
        try:
            yield _sse("status", {"stage": "planning", "label": "提炼目的并规划检索与分析"})
            # 1) 多步检索：由模型拆出多条精准检索式
            try:
                data = client.chat_json(
                    prompts.smart_queries_prompt(req.topic, req.steps), temperature=0.4
                )
            except Exception:  # noqa: BLE001
                data = {}
            queries = [q for q in (data.get("queries") or []) if q][: req.steps] or [req.topic]
            intent = data.get("intent", req.topic)
            structure = data.get("report_structure") or {}
            yield _sse("queries", {"intent": intent, "queries": queries})
            yield _sse("format_plan", {
                "title": structure.get("title"),
                "groups": structure.get("groups") or [],
                "count_hint": structure.get("count_hint"),
                "analysis_sections": structure.get("analysis_sections") or [],
                "format": structure.get("format") or "",
            })

            # 2) 逐条检索并汇总去重（统一走 retrieval_tool，与 agent 工具同源）
            yield _sse("status", {"stage": "searching", "label": "多源检索中"})
            all_docs = retrieval_tool.retrieve_many(queries, per_query=req.per_query, language=req.language)
            for i, q in enumerate(queries):
                yield _sse("step_done", {"index": i + 1, "query": q, "found": len(all_docs)})
            # 3) 回传来源
            yield _sse("sources", {
                "sources": [d.model_dump() for d in all_docs],
                "count": len(all_docs),
            })

            # 4) 生成简要检索报告（流式，带引用）
            yield _sse("status", {"stage": "writing", "label": "撰写检索报告"})
            block = _sources_block(all_docs)
            messages = prompts.smart_report_prompt(req.topic, block, req.language, structure)
            for delta in client.chat_stream(messages, temperature=0.5):
                yield _sse("report_delta", {"delta": delta})
            yield _sse("done", {"count": len(all_docs)})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/library")
def list_library() -> dict:
    return {"items": store.list_library()}


# --- paper discussion (interactive PDF seminar) ------------------------------
PAPER_CHAR_CAP = 90000


@app.post("/api/paper/upload")
async def paper_upload(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    name = file.filename or "paper.pdf"
    text = _extract_text(name, raw)
    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从该文件提取文本（请确认是文本型 PDF / txt / md）")
    trunc_note = ""
    if len(text) > PAPER_CHAR_CAP:
        text = text[:PAPER_CHAR_CAP]
        trunc_note = f"（全文较长，仅载入前 {PAPER_CHAR_CAP} 字用于研讨）"
    paper_id = f"p_{uuid.uuid4().hex[:10]}"
    store.save_paper(PaperDoc(paper_id=paper_id, filename=name, text=text))
    return {"paper_id": paper_id, "filename": name, "chars": len(text), "trunc_note": trunc_note}


@app.post("/api/paper/from-library")
def paper_from_library(body: dict) -> dict:
    saved_id = (body or {}).get("saved_id", "")
    item = next((x for x in store.list_library() if x.get("saved_id") == saved_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="文库文献不存在")
    text = (item.get("text") or "").strip()
    if len(text) < 50:
        raise HTTPException(
            status_code=400,
            detail="该文库文献没有可研讨的正文（可能只是检索元数据），请重新上传 PDF 后再研讨",
        )
    trunc_note = ""
    if len(text) > PAPER_CHAR_CAP:
        text = text[:PAPER_CHAR_CAP]
        trunc_note = f"（全文较长，仅载入前 {PAPER_CHAR_CAP} 字用于研讨）"
    name = item.get("title") or "文库文献"
    paper_id = f"p_{uuid.uuid4().hex[:10]}"
    store.save_paper(PaperDoc(paper_id=paper_id, filename=name, text=text))
    return {"paper_id": paper_id, "filename": name, "chars": len(text), "trunc_note": trunc_note}


@app.post("/api/paper/chat/stream")
def paper_chat(req: PaperChatRequest) -> StreamingResponse:
    client = _get_client()
    paper = store.get_paper(req.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在，请重新上传")

    messages = prompts.paper_chat_system(req.language)
    messages.append({"role": "user", "content": f"<paper>\n{paper.text}\n</paper>"})
    for turn in req.history[-12:]:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message})

    def gen():
        try:
            for delta in client.chat_stream(messages, temperature=0.45):
                yield _sse("paper_delta", {"delta": delta})
            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- research intent recognition ---------------------------------------------
@app.post("/api/research/intent")
def research_intent(body: dict) -> dict:
    query = (body.get("query") or "").strip()
    if not query:
        return {"available": settings.is_configured, "confidence": 0}
    if not settings.is_configured:
        return {"available": False, "confidence": 0}
    try:
        client = Hy3Client()
        data = client.chat_json(prompts.research_intent_prompt(query), temperature=0.2)
    except Exception:  # noqa: BLE001
        return {"available": True, "confidence": 0}

    def _pick(val, valid, default):
        return val if val in valid else default

    return {
        "available": True,
        "task_type": _pick(data.get("task_type"), prompts.VALID_TASK_TYPES, "literature_review"),
        "style": _pick(data.get("style"), prompts.VALID_STYLES, "academic"),
        "depth": _pick(data.get("depth"), prompts.VALID_DEPTHS, "standard"),
        "language": _pick(data.get("language"), prompts.VALID_LANGS, "zh"),
        "confidence": float(data.get("confidence", 0) or 0),
        "reason": data.get("reason", ""),
    }


# --- 用户卡片（内部个性化机制，不暴露给前端） ---------------------------------
def build_user_card() -> dict:
    """组装「用户卡片」（内部机制，不对外暴露）。

    两层信号：
      - level1（即时信号）：最近检索 / 最近研究内容，随时间滚动，捕捉用户当下关注点；
      - level2（稳定画像）：用户在「个人主页」显式声明的身份 / 机构 / 研究兴趣，
        以及从行为中沉淀的派生兴趣，构成长期个性化基线。
    推荐时同时结合两层，使结果既贴合当下、又不脱离用户长期方向。
    """
    cfg = store.get_settings() or {}
    prof = (cfg.get("profile") or {}) if isinstance(cfg, dict) else {}

    # level2：显式声明的研究身份与兴趣（稳定基线）
    identity = {
        "name": (prof.get("name") or "").strip(),
        "role": (prof.get("identity") or "").strip(),
        "institution": (prof.get("institution") or "").strip(),
    }
    declared = [str(x).strip() for x in (prof.get("interests") or []) if str(x).strip()]

    # level1：最近行为信号
    history = store.get_search_history()
    recent_queries = [h.get("query", "") for h in history[:8] if (h.get("query") or "").strip()]
    recent_titles: list[str] = []
    for it in store.list_unified_history():
        if it.get("kind") in ("research", "search", "smart", "studio"):
            t = (it.get("title") or "").strip()
            if t and t not in recent_titles:
                recent_titles.append(t)
    recent_titles = recent_titles[:8]

    # 从行为中沉淀的派生兴趣（level2 补充）：简单按分隔符抽取候选词
    derived: list[str] = []
    for text in recent_queries + recent_titles:
        for tok in re.split(r"[，,；;、/\s]+", text):
            tok = tok.strip()
            if 2 <= len(tok) <= 20 and tok not in derived:
                derived.append(tok)
    derived = derived[:24]

    # 合并关键词：声明兴趣优先（保证长期方向始终参与），其次派生兴趣
    keywords: list[str] = []
    for k in declared + derived:
        if k not in keywords:
            keywords.append(k)
    keywords = keywords[:30]

    return {
        "identity": identity,
        "declared_interests": declared,          # level2 显式
        "recent_activity": recent_queries,       # level1 最近检索
        "recent_titles": recent_titles,          # level1 最近研究
        "derived_interests": derived,            # level2 从行为沉淀
        "keywords": keywords,
    }


# --- "猜你想搜" suggestions from search habits -------------------------------
@app.get("/api/suggestions")
def suggestions() -> dict:
    card = build_user_card()
    recent = card["recent_activity"]

    # level1（即时信号）：最近检索 + 最近研究内容，捕捉当下关注点
    level1 = (recent + card["recent_titles"])[:12]
    # level2（稳定画像）：用户研究兴趣卡片（长期方向，参与但不喧宾夺主）
    level2 = card["keywords"][:12]

    # 无信号：返回一组默认示例，保证界面不空且零延迟
    defaults = [
        {"topic": "面向 RAG 的长上下文压缩方法综述与研究空白分析", "keywords": ["RAG", "长上下文", "综述"]},
        {"topic": "多模态检索增强生成（Multimodal RAG）的方法分类与评测现状", "keywords": ["多模态", "RAG", "评测"]},
        {"topic": "大语言模型代码智能体（Code Agent）的任务规划方法综述", "keywords": ["LLM", "Code Agent", "规划"]},
    ]
    if not level1 and not level2:
        return {"recent": [], "suggestions": defaults, "available": settings.is_configured}

    # 缓存键结合 level1 + level2，任一层变化都触发重算（基于用户卡片，低延迟）
    key_src = "|".join(level1[-10:]) + "#" + "|".join(level2[:10])
    key = hashlib.md5(key_src.encode()).hexdigest()
    cached = store.get_cached_suggestions(key)
    if cached is not None:
        return {**cached, "recent": recent}

    if settings.is_configured:
        try:
            client = Hy3Client()
            data = client.chat_json(
                prompts.recommend_prompt(level1, level2, Language.zh), temperature=0.5
            )
            raw = [s for s in (data.get("suggestions") or []) if s][:6]
            sugg = _normalize_suggestions(raw)
            if sugg:
                payload = {"recent": recent, "suggestions": sugg, "available": True}
                store.cache_suggestions(key, payload)
                return payload
        except Exception:  # noqa: BLE001
            pass

    # 启发式兜底：即时信号 + 同主题的子方向扩展关键词
    seed = level1[-1] if level1 else (level2[0] if level2 else "")
    raw = list(dict.fromkeys(recent[:4] + _expand_keywords(seed)))
    payload = {"recent": recent, "suggestions": _normalize_suggestions(raw), "available": settings.is_configured}
    store.cache_suggestions(key, payload)
    return payload


def _normalize_suggestions(raw: list) -> list[dict]:
    """将 LLM / 启发式返回的建议规整为 {topic, keywords} 结构，兼容字符串与对象。"""
    out: list[dict] = []
    for s in raw:
        if isinstance(s, dict):
            topic = (s.get("topic") or "").strip()
            kws = [str(k).strip() for k in (s.get("keywords") or []) if str(k).strip()][:3]
        else:
            topic = str(s).strip()
            kws = []
        if topic:
            out.append({"topic": topic, "keywords": kws})
    return out


def _expand_keywords(query: str) -> list[str]:
    """极简启发式：基于最近一次检索词，生成相邻方向的检索建议。"""
    if not query:
        return []
    seeds = ["方法综述", "评测指标", "最新进展", "研究空白", "应用实践", "对比分析"]
    base = query.replace("综述", "").replace("调研", "").replace("分析", "").strip()
    return [f"{base}{s}" for s in seeds][:4]


@app.post("/api/library")
def add_library(body: dict) -> dict:
    item = body.get("item", {}) if isinstance(body, dict) else {}
    title = (item.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="缺少标题")
    saved_id = "p_" + hashlib.md5(title.lower().encode()).hexdigest()[:10]
    record = {
        "saved_id": saved_id,
        "title": title,
        "source_type": item.get("source_type", "paper"),
        "url": item.get("url"),
        "authors": item.get("authors", []) or [],
        "year": item.get("year"),
        "venue": item.get("venue"),
        "abstract": item.get("abstract", "") or "",
        "text": item.get("text", "") or "",
        "retrieved_from": item.get("retrieved_from", "文库"),
        "saved_at": __import__("datetime").datetime.utcnow().isoformat(),
        "tags": item.get("tags", []) or [],
        "folder": item.get("folder", "") or "",
    }
    store.add_library(record)
    return {"saved_id": saved_id, "item": record}


@app.delete("/api/library/{saved_id}")
def delete_library(saved_id: str) -> dict:
    store.remove_library(saved_id)
    return {"ok": True}


# --- library folders ---------------------------------------------------------
@app.get("/api/library/folders")
def list_folders() -> dict:
    return {"folders": store.list_folders()}


@app.post("/api/library/folders")
def create_folder(body: dict) -> dict:
    rec = store.add_folder((body or {}).get("name", ""), (body or {}).get("parent_id", ""))
    if not rec:
        raise HTTPException(status_code=400, detail="文件夹名称无效")
    return {"folder": rec}


@app.put("/api/library/folders/{fid}")
def rename_folder(fid: str, body: dict) -> dict:
    ok = store.rename_folder(fid, (body or {}).get("name", ""))
    return {"ok": ok}


@app.delete("/api/library/folders/{fid}")
def delete_folder(fid: str) -> dict:
    ok = store.remove_folder(fid)
    return {"ok": ok}


@app.post("/api/library/move")
def move_library(body: dict) -> dict:
    ids = (body or {}).get("ids", []) or []
    folder = (body or {}).get("folder", "") or ""
    n = store.move_library(ids, folder)
    return {"moved": n}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    name = file.filename or "uploaded"
    text = _extract_text(name, raw)
    if not text.strip():
        raise HTTPException(status_code=400, detail="无法从该文件提取文本")
    upload_id = f"u_{uuid.uuid4().hex[:10]}"
    store.save_upload(UploadedDoc(upload_id=upload_id, filename=name, text=text))
    return {"upload_id": upload_id, "filename": name, "chars": len(text), "text": text}


@app.post("/api/research/stream")
def research_stream(req: ResearchRequest) -> StreamingResponse:
    client = _get_client()
    store.add_search_history(req.query, "research")
    task = ResearchTask(task_id=f"t_{uuid.uuid4().hex[:10]}", request=req)
    store.save_task(task)
    pipeline = ResearchPipeline(task, client)

    def gen():
        yield _sse("task_created", {"task_id": task.task_id})
        for event, payload in pipeline.run():
            yield _sse(event, payload)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/tools/run")
def tools_run(req: ToolRequest) -> StreamingResponse:
    client = _get_client()
    messages = prompts.tool_prompt(req.tool, req.topic, req.language)

    def gen():
        try:
            for delta in client.chat_stream(messages, temperature=0.5):
                yield _sse("tool_delta", {"delta": delta})
            yield _sse("tool_done", {})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/refine")
def refine(req: RefineRequest) -> dict:
    task = store.get_task(req.task_id)
    if not task or not task.plan:
        raise HTTPException(status_code=404, detail="任务不存在")
    section = next((s for s in task.sections if s.section_id == req.section_id), None)
    if not section:
        raise HTTPException(status_code=404, detail="章节不存在")

    client = _get_client()
    pipeline = ResearchPipeline(task, client)
    packets_block = pipeline._packets_block()
    target_style = Style(req.style) if req.style else None
    messages = prompts.refine_prompt(
        task.request, req.action, section.section_title, section.content,
        packets_block, target_style,
    )
    new_content = client.chat(messages, temperature=0.5)
    section.content = new_content.strip()
    section.citation_source_ids = sorted(
        set(re.findall(r"\[(s\d+)\]", new_content)), key=lambda x: int(x[1:])
    )
    store.save_task(task)
    return {
        "section_id": section.section_id,
        "content": section.content,
        "citations": section.citation_source_ids,
        "tokens": client.usage.snapshot(),
    }


@app.get("/api/task/{task_id}")
def get_task(task_id: str) -> dict:
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.model_dump()


@app.get("/api/tasks")
def list_tasks() -> list[dict]:
    return [
        {
            "task_id": t.task_id,
            "query": t.request.query,
            "task_type": t.request.task_type,
            "status": t.status,
            "created_at": t.created_at.isoformat(),
            "num_sections": len(t.sections),
        }
        for t in store.list_tasks()
    ]


# --- unified history across the 4 modules -------------------------------------
@app.get("/api/history")
def unified_history() -> dict:
    return {"items": store.list_unified_history()}


@app.delete("/api/history")
def delete_unified_history(payload: dict) -> dict:
    items = payload.get("items", []) if isinstance(payload, dict) else []
    n = store.delete_unified_history(items)
    return {"removed": n}


@app.post("/api/studio/history")
def studio_history(body: dict) -> dict:
    store.add_studio_history(body.get("topic", ""), body.get("tool", ""), body.get("snippet", ""))
    return {"ok": True}


@app.post("/api/paper/history")
def paper_history(body: dict) -> dict:
    store.add_paper_history(
        body.get("paper_id", ""), body.get("filename", ""), body.get("transcript", [])
    )
    return {"ok": True}


@app.post("/api/advisor/history")
def advisor_history(body: dict) -> dict:
    store.add_advisor_history(
        body.get("advisor_id", ""), body.get("topic", ""), body.get("transcript", [])
    )
    return {"ok": True}


@app.delete("/api/paper/history/{paper_id}")
def delete_paper_history(paper_id: str) -> dict:
    store.delete_paper_history(paper_id)
    return {"ok": True}


# --- text extraction ---------------------------------------------------------
def _extract_text(filename: str, raw: bytes) -> str:
    lower = filename.lower()
    if lower.endswith((".txt", ".md", ".markdown")):
        return raw.decode("utf-8", errors="ignore")
    if lower.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:  # noqa: BLE001
            print(f"[upload] pdf parse failed: {exc}")
            return ""
    return raw.decode("utf-8", errors="ignore")


# --- 创造工坊 (Creator Workshop): discover / favourite / create / use ----------
@app.get("/api/features")
def api_list_features(q: str = "", category: str = "", scope: str = "") -> dict:
    # scope: discover | mine | templates （favorites 单独走 /api/features/favorites）
    return {"features": feature_store.list_features(q or None, category or None, scope or None)}


@app.get("/api/features/favorites")
def api_list_favorites() -> dict:
    return {"features": feature_store.list_favorites()}


@app.get("/api/features/{fid}")
def api_get_feature(fid: str) -> dict:
    f = feature_store.get_feature(fid)
    if not f:
        raise HTTPException(status_code=404, detail="功能不存在")
    return {"feature": f}


@app.post("/api/features/{fid}/use")
def api_use_feature(fid: str) -> dict:
    # 进入功能工作区时记录一次使用（方案 §8 独立运行 / 使用统计）
    feature_store.incr_use(fid)
    return {"ok": True}


@app.post("/api/features/{fid}/fork")
def api_fork_feature(fid: str) -> dict:
    rec = feature_store.fork_feature(fid)
    if not rec:
        raise HTTPException(status_code=404, detail="功能不存在")
    return {"feature": rec}


@app.post("/api/features/{fid}/rate")
def api_rate_feature(fid: str, body: dict) -> dict:
    raw = body.get("stars") or body.get("rating") or 0
    try:
        stars = int(raw)
    except (TypeError, ValueError):
        stars = 0
    rec = feature_store.rate_feature(fid, stars)
    if not rec:
        raise HTTPException(status_code=404, detail="功能不存在")
    return {"feature": rec}


@app.put("/api/features/{fid}")
def api_update_feature(fid: str, body: dict) -> dict:
    rec = feature_store.update_feature(fid, body)
    if not rec:
        raise HTTPException(status_code=404, detail="功能不存在")
    return {"feature": rec}




@app.post("/api/features")
def api_create_feature(body: dict) -> dict:
    rec = feature_store.create_feature(body)
    return {"feature": rec}


@app.delete("/api/features/{fid}")
def api_delete_feature(fid: str) -> dict:
    feature_store.delete_feature(fid)
    return {"ok": True}


@app.post("/api/features/favorite")
def api_toggle_favorite(body: dict) -> dict:
    fid = body.get("id") or body.get("feature_id")
    if not fid:
        raise HTTPException(status_code=400, detail="缺少功能 id")
    state = feature_store.toggle_favorite(fid)
    return {"ok": True, "favorited": state}


@app.post("/api/features/generate")
def api_generate_feature(body: dict) -> dict:
    desc = (body.get("description") or "").strip()
    if not desc:
        raise HTTPException(status_code=400, detail="请描述你想要的功能")
    if not settings.is_configured:
        return {"feature": feature_store.heuristic_feature(desc)}
    try:
        client = Hy3Client()
        data = client.chat_json(
            prompts.feature_gen_prompt(desc, body.get("language", "zh")), temperature=0.6
        )
        layout_type = (data.get("layout_type") or "chat").lower().strip()
        valid_layouts = {"research", "review", "experiment", "meeting", "medical", "coding", "chat"}
        if layout_type not in valid_layouts:
            layout_type = feature_store._infer_layout(desc)
        rec = {
            "name": (data.get("name") or desc)[:40],
            "emoji": (data.get("emoji") or "🧩"),
            "description": data.get("description") or desc,
            "category": data.get("category") or "Others",
            "layout_type": layout_type,
            "version": data.get("version") or "1.0.0",
            "prompt": data.get("prompt") or f"你是一个助手，帮助用户：{desc}",
            "tags": data.get("tags", []) or [],
            "design_level": "simple",
            "ui": feature_store._layout_ui(layout_type),
            "workflow": feature_store._layout_workflow(layout_type),
            "starters": data.get("starters", []) or _default_starters(layout_type, desc),
        }
        return {"feature": rec}
    except Exception:  # noqa: BLE001
        return {"feature": feature_store.heuristic_feature(desc)}


def _default_starters(layout_type: str, desc: str) -> list[str]:
    defaults = {
        "research": ["上传一篇论文开始阅读", "帮我提取这篇论文的创新点", "总结这节的实验结果"],
        "review": ["上传一篇论文进行审稿", "从创新性维度评估这篇论文", "给出完整审稿意见"],
        "experiment": ["帮我设计一个实验方案", "分析这个实验的混淆因素", "生成实验时间表"],
        "meeting": ["粘贴一段会议记录", "提取会议中的决策事项", "列出待办行动项"],
        "medical": ["帮我生成一份病历", "分析可能的鉴别诊断", "给出诊疗计划建议"],
        "coding": ["帮我review这段代码", "解释这个函数的作用", "帮我修复这个bug"],
        "chat": [f"帮我处理：{desc[:20]}", "给我一个示例", "有什么注意事项？"],
    }
    return defaults.get(layout_type, defaults["chat"])


@app.post("/api/features/design/chat")
def api_design_chat(body: dict) -> dict:
    """初步设计级别：多轮对话，引导用户讲清需求。"""
    history = body.get("history", []) or []
    if not settings.is_configured:
        n = len([h for h in history if h.get("role") == "user"])
        hints = [
            "你想让这个功能做什么？一句话描述即可。",
            "它的输入通常是什么？比如文本、链接、还是选项？",
            "你希望页面上有哪些模块？比如输入框、下拉、对话区、结果区。",
            "需求已经比较清晰了，可以点「生成页面」了。",
        ]
        return {"reply": hints[min(n, len(hints) - 1)]}
    try:
        client = Hy3Client()
        msgs = prompts.feature_design_chat_prompt(history, body.get("language", "zh"))
        reply = "".join(client.chat_stream(msgs, temperature=0.7))
        return {"reply": reply}
    except Exception:  # noqa: BLE001
        return {"reply": "（离线模式）请继续描述你的功能需求，比如：输入是什么、希望得到什么输出、需要哪些模块。"}


@app.post("/api/features/build")
def api_build_feature(body: dict) -> dict:
    """初步设计级别：把需求对话转成可拖拽布局。"""
    desc = (body.get("description") or "").strip()
    transcript = (body.get("transcript") or "").strip()
    src = transcript or desc
    if not settings.is_configured:
        return {"feature": feature_store.heuristic_design(desc or transcript, transcript)}
    try:
        client = Hy3Client()
        data = client.chat_json(prompts.feature_build_prompt(src, body.get("language", "zh")), temperature=0.6)
        layout = data.get("layout") or feature_store.heuristic_layout(desc)
        if not isinstance(layout, list):
            layout = feature_store.heuristic_layout(desc)
        # 规范化每个 block
        norm_layout = []
        for i, b in enumerate(layout):
            if not isinstance(b, dict) or not b.get("type"):
                continue
            b.setdefault("key", f"block_{i}")
            norm_layout.append(b)
        rec = {
            "name": (data.get("name") or desc or "自定义功能")[:40],
            "emoji": (data.get("emoji") or "🧩"),
            "description": data.get("description") or desc,
            "prompt": data.get("prompt") or f"你是一个助手，帮助用户：{src}",
            "tags": data.get("tags", []) or [],
            "design_level": "builder",
            "ui": {"type": "builder", "layout": norm_layout},
            "starters": [],
        }
        return {"feature": rec}
    except Exception:  # noqa: BLE001
        return {"feature": feature_store.heuristic_design(desc or transcript, transcript)}


@app.post("/api/features/{fid}/chat/stream")
def api_feature_chat(fid: str, req: dict) -> StreamingResponse:
    client = _get_client()
    feat = feature_store.get_feature(fid)
    if not feat:
        raise HTTPException(status_code=404, detail="功能不存在")
    messages = [{"role": "system", "content": feat["prompt"]}]
    for turn in (req.get("history") or [])[-12:]:
        role = turn.get("role")
        content = turn.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.get("message", "")})

    def gen():
        try:
            for delta in client.chat_stream(messages, temperature=0.6):
                yield _sse("feat_delta", {"delta": delta})
            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    feature_store.incr_use(fid)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- 思路提炼 (Idea Refiner): 互动式想法打磨，不写报告 ------------
@app.post("/api/advisor/chat/stream")
def advisor_chat(req: dict) -> StreamingResponse:
    """互动式研究教练：多轮对话，帮用户想清楚方向与实验。绝不代写论文。

    核心：agent 通过工具调用（retrieve_papers）**在生成回答之前自主检索**真实文献，
    再把文献作为证据、用 [rN] 引用作答——全程无需用户手动触发，且回答前必带证据。
    若模型端点不支持工具调用，则降级为『元决策 → 检索 → 注入』的兜底流程。
    """
    client = _get_client()
    history = (req or {}).get("history", []) or []
    message = (req or {}).get("message", "") or ""
    language = (req or {}).get("language", "zh") or "zh"
    # 仅把最近 12 轮作为上下文传给模型
    recent = [h for h in history[-12:] if h.get("role") in ("user", "assistant") and h.get("content")]
    user_turns = sum(1 for h in recent if h.get("role") == "user")

    def gen():
        try:
            # 多轮后给出收敛提示，避免对话『无穷无尽』
            extra = CONVERGE_HINT if user_turns >= 3 else None
            messages = prompts.advisor_chat_prompt(recent, language, extra_system=extra)
            messages.append({"role": "user", "content": message})

            tools = [retrieval_tool.TOOL_SPEC]
            # 实质性提问才检索（寒暄 / 致谢 / 极短消息不检索，避免无意义检索）
            want_retrieval = settings.is_configured and _advisor_wants_retrieval(message)

            if want_retrieval:
                # 强制 agent 先调用 retrieve_papers —— 保证『先检索、再回答』，而非凭记忆作答
                try:
                    msg = client.chat_message(
                        messages, tools=tools, force_tool_name="retrieve_papers", temperature=0.6
                    )
                    tc = (getattr(msg, "tool_calls", None) or [None])[0]
                    if tc:
                        fname = getattr(getattr(tc, "function", None), "name", "") or "retrieve_papers"
                        args_str = getattr(tc.function, "arguments", "") or "{}"
                        # 解析模型给出的检索式
                        try:
                            _args = json.loads(args_str) if args_str else {}
                        except Exception:  # noqa: BLE001
                            _args = {}
                        top_k = max(3, min(int(_args.get("top_k") or 6), 12))
                        q = str(_args.get("query") or message).strip()
                        q = q[:120]
                        # 在「真正开始检索」之前就通知前端，让网络检索 + LLM 过滤这段时间
                        # 气泡持续显示『正在检索真实文献依据…』的 flush 动画（而非检索做完才通知）
                        yield _sse("need_evidence", {"reason": "检索真实文献以支撑严谨性"})
                        # 学术库英文索引为主：检索式含中文则统一改写为英文；
                        # 首次未命中则自动用英文重构式重试，提升对口率、避免错语料。
                        # 检索 + 两层过滤（关键词规则 + LLM 结合用户问题的语义过滤），
                        # 无关文献直接剔除、相关文献重新编号后再展示与回灌。
                        evidence_block, docs = retrieval_tool.run_retrieval(
                            q, top_k, language, client=client, question=message
                        )
                        if _is_cjk(q) or not docs:
                            alt_q = _build_search_query(client, message, language)
                            if alt_q and (not docs or alt_q.lower() != q.lower()):
                                evidence_block, docs = retrieval_tool.run_retrieval(
                                    alt_q, top_k, language, client=client, question=message
                                )
                                q = alt_q
                        yield _sse("plan", {"strategy": f"检索：{q}", "queries": [q]})
                        yield _sse("step_done", {"index": 1, "query": q, "found": len(docs)})
                        if docs:
                            yield _sse("sources", {
                                "sources": [d.model_dump() for d in docs],
                                "count": len(docs),
                            })
                        # 把工具调用与检索结果回灌，模型据此作答（带 [rN] 引用）
                        messages.append({
                            "role": "assistant",
                            "content": msg.content or "",
                            "tool_calls": [{
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": fname, "arguments": args_str},
                            }],
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": evidence_block or "（未检索到相关文献；请基于常识谨慎回答，并明确说明缺乏文献支撑）",
                        })
                except Exception:  # noqa: BLE001
                    # 端点不支持工具调用 -> 直接检索（等价『agent 检索』，仍先检索再答）
                    fb_q = _build_search_query(client, message, language)
                    yield _sse("need_evidence", {"reason": "检索真实文献以支撑严谨性"})
                    docs = retrieval_tool._filter_relevant(
                        retrieval_tool.retrieve_many([fb_q], per_query=6, language=language), fb_q
                    )
                    docs = retrieval_tool.llm_filter_relevant(client, message, docs, language)
                    if docs:
                        yield _sse("plan", {"strategy": f"检索：{fb_q[:120]}", "queries": [fb_q[:120]]})
                        yield _sse("step_done", {"index": 1, "query": fb_q[:120], "found": len(docs)})
                        yield _sse("sources", {
                            "sources": [d.model_dump() for d in docs],
                            "count": len(docs),
                        })
                        lines = []
                        for d in docs:
                            meta_line = ", ".join((d.authors or [])[:3])
                            if d.year: meta_line += f" · {d.year}"
                            if d.venue: meta_line += f" · {d.venue}"
                            snippet = (d.abstract or d.snippet or "")[:200]
                            lines.append(f"[{d.source_id}] {d.title}\n    {meta_line}\n    {snippet}")
                        ev = "\n\n".join(lines)
                        msgs = prompts.advisor_chat_prompt(recent, language)
                        msgs.append({"role": "user", "content": message})
                        msgs.append(prompts.advisor_evidence_explain_user(ev, language))
                        messages = msgs

            # 最终作答：若已检索则结合 [rN] 证据，否则直接作答
            full: list[str] = []
            for delta in client.chat_stream(messages, temperature=0.6):
                full.append(delta)
                yield _sse("advisor_delta", {"delta": delta})
            reply = "".join(full)


            # 提取选择题（引导下一步），失败不影响主流程
            try:
                meta_post = client.chat_json(
                    prompts.advisor_meta_prompt(history, message, reply, language), temperature=0.3
                )
                choices = meta_post.get("choices") or []
            except Exception:  # noqa: BLE001
                choices = []
            if isinstance(choices, list) and choices:
                yield _sse("advisor_choices", {"questions": choices})
            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/advisor/guide")
def advisor_guide(req: dict) -> dict:
    """把教练对话收敛成一份『思路提炼指南』（思考框架，并非成稿），分已锚定 / 待论证两组。"""
    if not settings.is_configured:
        raise HTTPException(status_code=503, detail="HY3_API_KEY 未配置")
    history = (req or {}).get("history", []) or []
    language = (req or {}).get("language", "zh") or "zh"
    try:
        client = Hy3Client()
        data = client.chat_json(prompts.advisor_guide_prompt(history, language), temperature=0.5)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"生成指南失败：{exc}")
    # 容错：至少保证两组结构完整
    def _group(key: str) -> list[dict]:
        items = data.get(key) or []
        if not isinstance(items, list):
            return []
        return [
            {"title": (s.get("title") or "未命名"), "body": s.get("body") or ""}
            for s in items if isinstance(s, dict)
        ]
    return {
        "title": (data.get("title") or "思路提炼指南")[:60],
        "summary": data.get("summary", "") or "",
        "confirmed": _group("confirmed"),
        "pending": _group("pending"),
    }


def _retrieve_evidence_docs(history: list[dict], topic: str, language: str) -> tuple[str, list[str], list]:
    """（兜底流程用）规划检索式并跨源检索真实文献作为证据。

    现统一走 retrieval_tool.retrieve_many，保证与 agent 工具调用同一套检索实现。
    返回 (strategy, queries, docs)，docs 已用 rN 编号。
    """
    try:
        client = _get_client()
    except Exception:  # noqa: BLE001
        return topic, [], []
    try:
        plan = client.chat_json(
            prompts.advisor_evidence_plan_prompt(history, language), temperature=0.4
        )
    except Exception:  # noqa: BLE001
        plan = {}
    strategy = plan.get("strategy") or topic
    queries = [q for q in (plan.get("queries") or []) if q][:4] or [topic]
    docs = retrieval_tool.retrieve_many(queries, per_query=6, language=language)
    return strategy, queries, docs


# --- 反馈看板 (Feedback board): word cloud + 收集 ---------------------------------
@app.get("/api/feedback")
def api_list_feedback() -> dict:
    return feedback_store.list_feedback()


@app.post("/api/feedback")
def api_create_feedback(body: dict) -> dict:
    try:
        rec = feedback_store.create_feedback(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "item": rec}


@app.post("/api/feedback/{fb_id}/up")
def api_upvote_feedback(fb_id: str) -> dict:
    try:
        res = feedback_store.upvote_feedback(fb_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, **res}


@app.post("/api/feedback/{fb_id}/down")
def api_downvote_feedback(fb_id: str) -> dict:
    try:
        res = feedback_store.downvote_feedback(fb_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, **res}


# --- static frontend (mounted last so /api takes priority) -------------------
if FRONTEND_DIR.exists():
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/feature/{fid}")
    def feature_standalone(fid: str) -> FileResponse:
        # 独立工作空间（方案 §8）：每个功能拥有独立 URL，进入后整个页面重新加载为专属界面。
        # 具体渲染由前端 SPA 读取 pathname 后boot进该功能。
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")
