"""统一的『检索工具』（Retrieval Tool）。

这是整个系统唯一的、规范的文献检索入口：

- ``retrieve_many`` / ``run_retrieval`` 封装底层 ``search.gather_sources``，负责
  跨源检索、去重、统一编号（r1, r2, …）。
- ``TOOL_SPEC`` 是 OpenAI 兼容的 function-calling 工具描述，交给 LLM 自主调用：
  当 agent 认为需要真实文献来支撑严谨性时，它会在**生成回答之前**调用
  ``retrieve_papers(query, top_k)``，我们把结果作为证据回灌，agent 再用 ``[rN]``
  引用作答。

所有需要检索的地方（思路提炼、智能检索、深度研究流水线等）都应经由本模块，
保证检索行为单一、可观测、可降级。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from .config import settings
from .models import SourceDocument
from .search import gather_sources


# ---------------------------------------------------------------------------
# OpenAI 兼容的工具描述：交给 agent 自主调用
# ---------------------------------------------------------------------------
TOOL_SPEC: dict = {
    "type": "function",
    "function": {
        "name": "retrieve_papers",
        "description": (
            "当需要就用户的研究想法 / 问题检索真实学术文献作为证据支撑时调用。"
            "应在正式回答之前调用，用检索到的文献（[r1]、[r2]… 编号）来支撑你的判断，"
            "而不是凭记忆编造论文。检索结果会以工具消息返回给你，你在回答中用 [rN] 引用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "检索式：必须是【英文】学术检索式（论文库 OpenAlex/Crossref/arXiv/Semantic Scholar "
                        "均以英文索引为主，中文检索式召回质量差、易命中无关语料，例如『压缩』会被匹配到图像/视频压缩）。"
                        "规则：① 只保留 2~5 个英文核心关键词，不要整句、不要中文；"
                        "② 当用户意在了解某『领域 / 方向 / 现状 / 研究空白 / 还缺什么』时，末尾追加 'survey' 或 'review'；"
                        "③ 具体方法 / 数据集 / 模型问题不要加 survey。"
                        "示例：用户问『了解世界模型的空白』→ 'world model survey'；"
                        "用户问『RAG 的上下文压缩从哪切入』→ 'retrieval augmented generation context compression'；"
                        "用户问『medical RAG context compression methods』→ 'medical RAG context compression'。"
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "希望返回的文献数量，默认 6，范围 3~12。",
                },
            },
            "required": ["query"],
        },
    },
}


def _renumber(docs: list[SourceDocument]) -> list[SourceDocument]:
    for idx, d in enumerate(docs, 1):
        d.source_id = f"r{idx}"
    return docs


def retrieve_many(
    queries: list[str],
    per_query: int = 6,
    language: str = "zh",
) -> list[SourceDocument]:
    """跨源检索并去重、统一编号（r1…）。供智能检索、深度研究等复用。

    返回 ``SourceDocument`` 列表（已按 rN 编号），检索失败 / 未配置时返回空列表。
    """
    if not queries:
        return []
    per_query = max(3, min(per_query or 6, 20))
    out: list[SourceDocument] = []
    seen: set[str] = set()
    for q in queries:
        try:
            docs = gather_sources([q], use_paper=True, per_query=per_query)
        except Exception:  # noqa: BLE001
            docs = []
        for d in docs:
            key = re.sub(r"[^a-z0-9]", "", (d.title or "").lower())[:60]
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(d)
    return _renumber(out)


def format_evidence(docs: list[SourceDocument], max_snippet: int = 240) -> str:
    """把检索到的文献格式化为给 LLM 阅读的证据文本（带 [rN] 编号）。"""
    if not docs:
        return ""
    lines: list[str] = []
    for d in docs:
        meta_line = ", ".join((d.authors or [])[:3])
        if d.year:
            meta_line += f" · {d.year}"
        if d.venue:
            meta_line += f" · {d.venue}"
        snippet = (d.abstract or d.snippet or "")[:max_snippet]
        lines.append(f"[{d.source_id}] {d.title}\n    {meta_line}\n    {snippet}")
    return "\n\n".join(lines)


# 相关性过滤：跨源检索（尤其 Crossref）常宽松匹配到无关『survey/study』等词，
# 这里要求文献标题/摘要包含检索式首个核心词、且覆盖绝大多数关键词，过滤掉明显错语料。
_FILTER_STOP = set(
    "a an the of for and or to in on with via using based survey review study "
    "studies analysis approach".split()
)


def _query_words(q: str) -> list[str]:
    return [w for w in re.findall(r"[a-zA-Z]{3,}", (q or "").lower()) if w not in _FILTER_STOP]


def _filter_relevant(docs: list[SourceDocument], q: str) -> list[SourceDocument]:
    words = _query_words(q)
    if len(words) < 2:
        return docs
    first = words[0]
    kept: list[SourceDocument] = []
    for d in docs:
        t = f"{(d.title or '')} {(d.abstract or '')} {(d.snippet or '')}".lower()
        if first not in t:
            continue
        overlap = sum(1 for w in words if w in t)
        if overlap >= max(1, len(words) - 1):
            kept.append(d)
    # 兜底：过滤后若全被丢弃，保留原始结果，避免一轮检索完全无文献
    return kept if kept else docs


def llm_filter_relevant(
    client,
    question: str,
    docs: list[SourceDocument],
    language: str = "zh",
) -> list[SourceDocument]:
    """LLM 相关性过滤层：结合【用户原始问题】逐篇判断检索结果是否真正相关。

    关键词规则过滤（``_filter_relevant``）只能做浅层字面匹配，无法理解语义，
    这里再叠加一层由大模型做的语义过滤：把用户问题 + 每篇文献的标题/摘要交给模型，
    让它判断哪些文献与用户问题真正相关，丢弃无关文献，仅保留相关的并**重新编号**
    （r1, r2 …），保证前端展示与 [rN] 引用连续、干净。

    失败 / 未配置 / 模型异常时回退为传入的 ``docs``，保证检索链不中断。
    """
    if not docs or client is None:
        return docs
    listing_lines: list[str] = []
    for i, d in enumerate(docs):
        snippet = (d.abstract or d.snippet or "")[:220]
        meta = ", ".join((d.authors or [])[:2])
        if d.year:
            meta += f" · {d.year}"
        listing_lines.append(f"[{i}] {d.title}\n    {meta}\n    {snippet}")
    listing = "\n\n".join(listing_lines)
    sys = (
        "你是学术检索的相关性审阅助手。给定【用户的研究问题】和一批候选文献，"
        "逐篇判断该文献是否与用户问题**真正相关**（主题一致、能作为回答该问题的证据）。"
        "严格剔除只是字面撞词、领域完全不同、或明显跑题的文献"
        "（例如用户问『RAG 上下文压缩』，则图像/视频压缩、数据压缩等无关文献要剔除）。"
        "只输出 JSON，格式为 {\"relevant\": [编号, …]}，编号为需要保留的文献方括号数字，"
        "按相关性从高到低排列；若全部无关则返回 {\"relevant\": []}。不要输出多余文字。"
    )
    user = f"用户的研究问题：{question}\n\n候选文献：\n{listing}"
    try:
        result = client.chat_json(
            [{"role": "system", "content": sys},
             {"role": "user", "content": user}],
            temperature=0.1,
        )
        idxs = result.get("relevant") if isinstance(result, dict) else result
        if not isinstance(idxs, list):
            return docs
        kept: list[SourceDocument] = []
        seen: set[int] = set()
        for i in idxs:
            try:
                i = int(i)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(docs) and i not in seen:
                seen.add(i)
                kept.append(docs[i])
        # 兜底：模型判定全部无关时保留原列表，避免一轮检索完全无文献可展示
        return _renumber(kept) if kept else docs
    except Exception:  # noqa: BLE001
        return docs


def run_retrieval(
    query: str,
    top_k: int = 6,
    language: str = "zh",
    client=None,
    question: str = "",
) -> tuple[str, list[SourceDocument]]:
    """agent 工具 ``retrieve_papers`` 的执行入口。

    返回 ``(evidence_block, docs)``：
    - ``evidence_block``：给 LLM 回灌的证据文本（[rN] 编号）；
    - ``docs``：结构化文献，用于前端「检索依据」与「本次引用」面板。

    过滤两层：① ``_filter_relevant`` 关键词规则过滤（丢弃字面错语料）；
    ② 传入 ``client`` 与用户原始 ``question`` 时，再叠加一层 LLM 语义相关性过滤，
    仅保留真正相关的文献并重新编号。
    """
    docs = retrieve_many([query], per_query=max(3, min(top_k or 6, 12)), language=language)
    docs = _filter_relevant(docs, query)  # 过滤跨源宽松匹配到的错语料（如『world model survey』误命中采购调查）
    if client is not None and question:
        docs = llm_filter_relevant(client, question, docs, language)
    return format_evidence(docs), docs


def execute_tool_call(name: str, arguments: str, language: str = "zh") -> tuple[str, list[SourceDocument]]:
    """统一执行一个工具调用（目前仅 ``retrieve_papers``），返回 (证据文本, 文献)。

    非检索类工具或解析失败会返回一条说明文本，保证调用链不中断。
    """
    if name != "retrieve_papers":
        return f"（未知工具：{name}，已忽略）", []
    try:
        args = json.loads(arguments or "{}")
    except Exception:  # noqa: BLE001
        args = {}
    q = (args.get("query") or "").strip()
    if not q:
        return "（检索式为空，未执行检索）", []
    top_k = args.get("top_k") or 6
    try:
        top_k = int(top_k)
    except Exception:  # noqa: BLE001
        top_k = 6
    return run_retrieval(q, top_k, language)
