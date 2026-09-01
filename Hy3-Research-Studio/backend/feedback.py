"""Persistence & analysis for the feedback board (词云 + 反馈收集).

Feedbacks are stored in a single JSON file under ``data/``. Each feedback carries
a category, free text, extracted keywords and a status. Keywords are aggregated
into a word cloud. A small sensitive-word list is masked on submit so the board
stays friendly. When the app runs locally (no network of other users yet) we seed
a few sample feedbacks so the cloud is never empty.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Optional

from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
FEEDBACK_FILE = DATA_DIR / "feedback.json"
_LOCK = threading.Lock()

# 轻量敏感词（屏蔽不当/广告内容，保持社区友好）。可按需扩充。
SENSITIVE_WORDS = [
    "垃圾", "废物", "滚蛋", "傻逼", "煞笔", "白痴", "智障", "fuck", "shit",
    "bitch", "广告", "代写", "刷单", "加微信", "代购", "色情", "赌博", "引流",
]

CATEGORIES = [
    "功能建议",     # 新增或增强某项功能
    "缺陷报告",     # 明确的 bug / 报错 / 结果错误
    "性能与稳定",   # 卡顿、慢、崩溃、超时
    "交互与界面",   # UI 布局、操作流程、可用性
    "内容与质量",   # 生成/翻译/引用等内容准确性
    "检索与数据",   # 检索源、数据覆盖、去重、排序
    "文档与帮助",   # 使用指南、说明、上手引导
    "其他",
]

_STOPWORDS = set(
    "的 了 是 我 你 他 她 它 们 这 那 有 和 与 及 在 也 都 就 不 没 没有 吗 呢 "
    "吧 啊 呀 把 被 让 给 对 为 以 于 而 但 却 很 太 非常 比较 一些 这个 那个 "
    "一个 可以 需要 希望 觉得 应该 可能 已经 还是 因为 所以 如果 怎么 什么 为什么 "
    "如何 怎样 一种 进行 通过 使用 目前 现在 我们 大家 用户 功能 问题 建议 期待 内容 "
    "质量 体验 想要 能够 支持".split()
)


def _load() -> dict:
    try:
        if FEEDBACK_FILE.exists():
            return json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {"items": []}


def _save(data: dict) -> None:
    try:
        FEEDBACK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[feedback] write failed: {exc}")


def _mask(text: str) -> tuple[str, bool]:
    """Return (masked_text, hit). Masks any sensitive word with ***."""
    hit = False
    out = text
    for w in SENSITIVE_WORDS:
        if w and w in out:
            hit = True
            out = out.replace(w, "***")
    return out, hit


def _heuristic_keywords(text: str) -> list[str]:
    """Offline keyword extraction without external NLP libs.

    Generates 2/3-grams for Chinese runs and latin words, then greedily selects
    a set of *non-overlapping* grams so the word cloud shows clean phrases
    (e.g. 「创造工坊」「工作流」) instead of fragmented overlapping characters.
    """
    t = text.lower()
    cands: list[tuple[str, int, int]] = []  # (gram, start, end)
    pos = 0
    for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9_\-]{2,}", t):
        w = m.group()
        if w not in _STOPWORDS:
            cands.append((w, pos, pos + 1))
            pos += 2
    for run in re.findall(r"[一-鿿]+", t):
        for n in (3, 2):
            for i in range(len(run) - n + 1):
                gram = run[i : i + n]
                if gram in _STOPWORDS:
                    continue
                if any(ch in _STOPWORDS for ch in gram):
                    continue
                cands.append((gram, pos + i, pos + i + n))
        pos += len(run) + 1
    cnt = Counter(g for g, _, _ in cands)
    order = sorted(set(g for g, _, _ in cands), key=lambda w: (-len(w), -cnt[w]))
    used: list[tuple[int, int]] = []
    selected: list[str] = []
    for w in order:
        for s, e in ((gs, ge) for gw, gs, ge in cands if gw == w):
            if not any(not (e <= us or s >= ue) for us, ue in used):
                used.append((s, e))
                selected.append(w)
                break
        if len(selected) >= 12:
            break
    return selected


def extract_keywords(text: str, language: str = "zh") -> list[str]:
    from .hy3_client import Hy3Client
    from . import prompts
    from .config import settings
    if settings.is_configured:
        try:
            client = Hy3Client()
            data = client.chat_json(prompts.feedback_keyword_prompt(text, language), temperature=0.3)
            if isinstance(data, list):
                return [str(k).strip() for k in data if str(k).strip()][:12]
        except Exception:  # noqa: BLE001
            pass
    return _heuristic_keywords(text)


def list_feedback() -> dict:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        items = data["items"]
        for it in items:  # 兼容旧数据：补齐点赞字段
            it.setdefault("upvotes", 0)
        cloud = _build_cloud(items)
        total_up = sum(int(it.get("upvotes", 0) or 0) for it in items)
        # 最近一次更新时间：取最新一条反馈的创建时间
        updated_at = max(
            (it.get("created_at") for it in items if it.get("created_at")),
            default=datetime.utcnow().isoformat(),
        )
    return {"items": items, "cloud": cloud, "categories": CATEGORIES,
            "total_up": total_up, "updated_at": updated_at}


def upvote_feedback(fb_id: str) -> dict:
    """点赞一条反馈，返回 {id, upvotes, total_up}。"""
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        target = None
        for it in data.get("items", []):
            if it.get("id") == fb_id:
                it["upvotes"] = int(it.get("upvotes", 0) or 0) + 1
                target = it
                break
        if target is None:
            raise ValueError("反馈不存在")
        _save(data)
        total_up = sum(int(it.get("upvotes", 0) or 0) for it in data["items"])
    return {"id": fb_id, "upvotes": target["upvotes"], "total_up": total_up}


def downvote_feedback(fb_id: str) -> dict:
    """撤回对一条反馈的 up，返回 {id, upvotes, total_up}。"""
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        target = None
        for it in data.get("items", []):
            if it.get("id") == fb_id:
                it["upvotes"] = max(0, int(it.get("upvotes", 0) or 0) - 1)
                target = it
                break
        if target is None:
            raise ValueError("反馈不存在")
        _save(data)
        total_up = sum(int(it.get("upvotes", 0) or 0) for it in data["items"])
    return {"id": fb_id, "upvotes": target["upvotes"], "total_up": total_up}


def _build_cloud(items: list[dict]) -> list[dict]:
    counter: Counter = Counter()
    ups: Counter = Counter()
    for it in items:
        u = int(it.get("upvotes", 0) or 0)
        for kw in (it.get("keywords") or []):
            counter[kw] += 1
            ups[kw] += u
    # 词的大小由「出现次数 + 所属反馈的 up 数」共同决定
    scores = {kw: counter[kw] + ups[kw] for kw in counter}
    maxs = max(scores.values()) if scores else 1
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:120]
    return [
        {"text": kw, "count": counter[kw], "ups": ups[kw],
         "weight": round(0.5 + 0.5 * (score / maxs), 3)}
        for kw, score in ranked
    ]


def create_feedback(payload: dict) -> dict:
    category = (payload.get("category") or "其他").strip()
    if category not in CATEGORIES:
        category = "其他"
    content = (payload.get("content") or "").strip()
    if not content:
        raise ValueError("反馈内容不能为空")
    content, hit = _mask(content)
    keywords = extract_keywords(content, payload.get("language", "zh"))
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        rec = {
            "id": "fb_" + uuid.uuid4().hex[:10],
            "category": category,
            "content": content,
            "keywords": keywords,
            "masked": hit,
            "upvotes": 0,
            "created_at": datetime.utcnow().isoformat(),
            "status": "open",
        }
        data.setdefault("items", []).insert(0, rec)
        _save(data)
    return rec


def _ensure_seed(data: dict) -> list[dict]:
    if data.get("items"):
        return data["items"]
    # (category, content, keywords, upvotes)
    # 关键词刻意重复出现，使词云词频有明显差异（大小不同）。
    samples = [
        ("功能建议", "希望创造工坊支持把多个功能组合成一个工作流，按顺序自动执行。",
         ["工作流", "创造工坊", "自动执行"], 42),
        ("功能建议", "深度研究能不能把检索、压缩、写作串成一条可复用的工作流模板。",
         ["工作流", "深度研究", "模板复用"], 27),
        ("功能建议", "希望论文研讨也能接入工作流，一键跑完概括、方法、局限三步。",
         ["工作流", "论文研讨", "一键执行"], 18),
        ("功能建议", "写作助手希望直接套用期刊模板，比如 IEEE 双栏和 ACM 格式。",
         ["期刊模板", "写作助手", "IEEE双栏"], 33),
        ("功能建议", "反馈页的词云能不能支持按分类高亮，一眼看清各类问题分布。",
         ["词云", "分类高亮", "反馈页"], 12),

        ("缺陷报告", "综述报告里引用格式偶尔错乱，编号和参考文献对不上。",
         ["引用格式", "引用错乱", "综述报告"], 51),
        ("缺陷报告", "导出 HTML 时公式渲染丢失，$E=mc^2$ 变成了纯文本。",
         ["公式渲染", "导出", "HTML"], 24),
        ("缺陷报告", "文献检索偶尔返回重复条目，同一篇论文出现好几次。",
         ["文献检索", "结果去重", "重复条目"], 30),
        ("缺陷报告", "引用溯源点开有时打不开原文链接，提示 404。",
         ["引用溯源", "链接失效", "引用格式"], 15),

        ("性能与稳定", "深度研究生成报告时偶尔会卡住，希望有进度百分比提示。",
         ["进度提示", "生成卡住", "深度研究"], 46),
        ("性能与稳定", "上传大 PDF 时解析较慢，希望有 loading 动画和预计时间。",
         ["解析慢", "loading动画", "进度提示"], 22),
        ("性能与稳定", "智能检索并发多源时偶尔超时，希望能自动重试。",
         ["检索超时", "自动重试", "文献检索"], 19),
        ("性能与稳定", "长报告在低配电脑上滚动有点卡，能否做虚拟滚动优化。",
         ["滚动卡顿", "性能优化"], 9),

        ("交互与界面", "移动端左侧栏太占空间，希望可以折叠收起。",
         ["移动端", "侧栏折叠"], 28),
        ("交互与界面", "移动端词云太挤看不清，希望能双指缩放查看。",
         ["移动端", "词云", "缩放查看"], 14),
        ("交互与界面", "希望增加深色模式以外的主题配色，比如护眼绿和纸张色。",
         ["主题配色", "深色模式", "护眼模式"], 37),
        ("交互与界面", "深色模式下部分浅色文字对比度不够，看着有点吃力。",
         ["深色模式", "对比度", "可读性"], 16),
        ("交互与界面", "反馈框希望固定在角落，边看已有反馈边写不用来回滚动。",
         ["反馈框", "布局优化"], 11),

        ("内容与质量", "有时摘要翻译不够通顺，专业术语希望保留英文原文。",
         ["翻译通顺", "专业术语", "英文原文"], 25),
        ("内容与质量", "期待加入论文对比功能，能并列两篇论文的方法与结论。",
         ["论文对比", "并列对比", "方法对比"], 40),
        ("内容与质量", "希望综述能自动区分观点与事实，避免把推测写成结论。",
         ["观点区分", "事实核查", "综述报告"], 17),

        ("检索与数据", "文献检索能否增加按被引量排序，方便找高影响力论文。",
         ["文献检索", "被引量排序", "高影响力"], 44),
        ("检索与数据", "希望检索能覆盖更多中文数据源，比如知网和万方。",
         ["中文数据源", "文献检索", "数据覆盖"], 31),
        ("检索与数据", "智能检索的去重再严格些，跨源的同名论文应合并。",
         ["结果去重", "跨源合并", "智能检索"], 20),

        ("文档与帮助", "期待反馈页能按关键词筛选，快速看同类问题。",
         ["关键词筛选", "反馈页"], 13),
        ("文档与帮助", "新手上手指南希望配个 60 秒动图，讲清一次完整研究流程。",
         ["上手指南", "新手引导", "动图教程"], 21),
        ("文档与帮助", "希望每个功能页右上角常驻一个使用贴士入口。",
         ["使用贴士", "帮助入口"], 8),

        ("其他", "整体非常好用，希望功能工坊能导出成分享链接发给同学一起用。",
         ["分享链接", "导出", "创造工坊"], 35),
        ("其他", "希望能把常用研究导出为 Markdown 归档到本地。",
         ["导出", "Markdown", "本地归档"], 10),
    ]
    items = []
    base = datetime(2026, 6, 1, 9, 0, 0)
    n = len(samples)
    for i, (cat, txt, kws, ups) in enumerate(samples):
        masked, _ = _mask(txt)
        # 越靠后创建时间越新，便于「最新排序」演示
        ts = base + timedelta(days=i, hours=(i * 7) % 11)
        items.append({
            "id": "fb_seed_" + str(i),
            "category": cat,
            "content": masked,
            "keywords": kws,
            "masked": False,
            "upvotes": ups,
            "created_at": ts.isoformat(),
            "status": "open",
        })
    # 按时间倒序（最新在前），与真实提交顺序一致
    items.reverse()
    data["items"] = items
    _save(data)
    return items
