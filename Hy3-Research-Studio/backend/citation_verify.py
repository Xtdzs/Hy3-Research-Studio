"""引用核对模块（T5 用例的端点化实现）。

方法学依据：
- [FactCheck]：Agent 化核查 = 先检索真实世界证据，再基于证据判定。
- [CorrectFaith]：区分「引用正确性」与「引用忠实度」；输出三分类：
  supported（真实且支撑）/ unrelated（真实但无关）/ nonexistent（疑似伪造）。

对外接口：``verify_citation(client, claim, reference) -> dict``
通过 HTTP 端点 ``/api/citation/verify`` 供其他系统复用。

注：已移除 OpenAlex 外部核查（限流风险高、不稳定），
核查完全基于 LLM 对被引摘要与论断的语义一致性（lookup 仅为占位，
不再注入提示词，避免将「未检索」误引导为「文献不存在」）。
"""
from __future__ import annotations

from .hy3_client import Hy3Client
from . import prompts

VALID_VERDICTS = ("supported", "unrelated", "nonexistent")


def _skipped_lookup(reference: dict) -> dict:
    """外部证据缺失时的占位结果（保持返回结构稳定）。"""
    return {"searched": False, "found": False, "title_match": 0.0,
            "top_title": "", "n_results": 0, "skipped": True}


def verify_citation(client: Hy3Client, claim: str, reference: dict,
                    lookup: dict | None = None) -> dict:
    """三分类核查判定。lookup 缺省时为"未做外部核查"占位（不触发任何网络请求）。"""
    lookup = lookup if lookup is not None else _skipped_lookup(reference)
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
