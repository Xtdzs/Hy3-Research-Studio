"""引用核对模块（T5 用例的端点化实现）。

方法学依据：
- [FactCheck]：Agent 化核查 = 先检索真实世界证据（OpenAlex），再基于证据判定。
- [CorrectFaith]：区分「引用正确性」与「引用忠实度」；输出三分类：
  supported（真实且支撑）/ unrelated（真实但无关）/ nonexistent（疑似伪造）。

对外接口：``verify_citation(client, claim, reference) -> dict``
通过 HTTP 端点 ``/api/citation/verify`` 供其他系统复用。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .hy3_client import Hy3Client
from . import prompts

VALID_VERDICTS = ("supported", "unrelated", "nonexistent")
OPENALEX = "https://api.openalex.org/works"


def _tokens(text: str) -> set[str]:
    import re
    return set(re.sub(r"[^\w\u4e00-\u9fff ]", " ", (text or "").lower()).split())


def _title_overlap(ref_title: str, top_title: str) -> float:
    """归一化 token 重合率：|ref ∩ top| / |ref|。用于识别"改写/伪造标题"。"""
    rt, tt = _tokens(ref_title), _tokens(top_title)
    if not rt:
        return 0.0
    return len(rt & tt) / len(rt)


def lookup_openalex(reference: dict, timeout: float = 12.0) -> dict:
    """外部证据：查询 OpenAlex 判断被引文献是否真实存在。

    返回 {"searched", "found", "title_match", "top_title", "n_results", "doi_hit"}。
    found 仅表示"检索有结果"；title_match∈[0,1] 表示标题归一化重合率——
    改写/伪造标题通常重合率低，这是判定层判定 nonexistent 的关键证据。
    网络失败时 searched=False，判定流程自动降级为纯 LLM 判断。
    """
    title = (reference.get("title") or "").strip()
    doi = (reference.get("doi") or "").strip()
    if not title and not doi:
        return {"searched": False, "found": False, "title_match": 0.0,
                "top_title": "", "n_results": 0}
    params = urllib.parse.urlencode({
        "search": title[:200] if title else doi,
        "per_page": 3,
        "select": "title,doi,publication_year",
    })
    req = urllib.request.Request(
        f"{OPENALEX}?{params}", headers={"User-Agent": "Hy3-Research-Studio/1.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return {"searched": False, "found": False, "title_match": 0.0,
                "top_title": "", "n_results": 0, "error": str(exc)[:80]}
    results = data.get("results", [])
    if not results:
        return {"searched": True, "found": False, "title_match": 0.0,
                "top_title": "", "n_results": 0}
    top = results[0]
    return {
        "searched": True,
        "found": bool((top.get("title") or "").strip()),
        "title_match": round(max(_title_overlap(title, (r.get("title") or ""))
                                for r in results), 4),
        "top_title": (top.get("title") or "")[:200],
        "n_results": len(results),
        "doi_hit": bool(doi) and (top.get("doi") or "").replace(
            "https://doi.org/", "") == doi.replace("https://doi.org/", ""),
    }


def verify_citation(client: Hy3Client, claim: str, reference: dict,
                    lookup: dict | None = None) -> dict:
    """三分类核查判定。lookup 缺省时自动执行 OpenAlex 外部核查。"""
    lookup = lookup if lookup is not None else lookup_openalex(reference)
    messages = prompts.citation_verify_messages(claim, reference, lookup)
    try:
        data = client.chat_json(messages, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "unrelated", "reason": f"核查调用失败：{exc}",
                "lookup": lookup, "confidence": 0.0}
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = "unrelated"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"verdict": verdict,
            "reason": str(data.get("reason", ""))[:300],
            "lookup": lookup,
            "confidence": max(0.0, min(1.0, confidence))}
