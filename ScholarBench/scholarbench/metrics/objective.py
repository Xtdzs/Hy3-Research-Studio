"""任务客观指标：全部由规则计算，零 LLM 调用，完全可复现。

每个任务族返回 (metrics, score_0_100, error_tags)。
error_tags 来自统一的失败归因体系，供 attribution.py 汇总。
"""
from __future__ import annotations

import math
import re

from ..schema import Answer, Task
from .base_helpers import lcs_rouge, norm_title, token_f1

# --- 失败归因标签 ---------------------------------------------------------
E_FACTUAL = "FACTUAL_HALLUCINATION"
E_CITATION = "UNSUPPORTED_CITATION"
E_MISSED = "MISSED_KEY_POINT"
E_TERM = "TERM_MISUSE"
E_LOGIC = "LOGIC_GAP"
E_RETRIEVAL = "RETRIEVAL_MISS"
E_TOOL = "TOOL_MISUSE"
E_COMPLIANCE = "COMPLIANCE_RISK"
E_VERBOSITY = "VERBOSITY"

SECTION_HINTS = {
    "T1": ["背景", "方法", "评测", "局限", "结论"],
    "T2": ["假设", "数据集", "指标", "基线", "预期"],
}


def _aliases(point: str) -> list[str]:
    return [a.strip().lower() for a in re.split(r"[/｜|、]", point) if a.strip()]


def _key_point_recall(content: str, key_points: list[str]) -> tuple[float, list[str]]:
    text_l = (content or "").lower()
    hit, missed = 0, []
    for p in key_points:
        if any(a in text_l for a in _aliases(p)):
            hit += 1
        else:
            missed.append(p)
    return hit / max(1, len(key_points)), missed


def _citation_resolution(answer: Answer) -> float:
    cites = answer.citations
    if not cites:
        return 0.0
    ok = sum(1 for c in cites if len((c.title or "").strip()) >= 8 or c.doi)
    return ok / len(cites)


def _structure_coverage(content: str, family: str) -> float:
    hints = SECTION_HINTS.get(family, [])
    if not hints:
        return 1.0
    return sum(1 for h in hints if h in (content or "")) / len(hints)


def _dcg(gains: list[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def _precision_recall_ndcg(retrieved: list[str], gold: list[str],
                           k_prec: int = 10, k_rec: int = 20, k_ndcg: int = 10):
    gold_n = {norm_title(g) for g in gold if g}
    if not gold_n:
        return 0.0, 0.0, 0.0
    r = [norm_title(t) for t in retrieved if t]
    precision = sum(1 for t in r[:k_prec] if t in gold_n) / k_prec
    recall = sum(1 for t in r[:k_rec] if t in gold_n) / len(gold_n)
    gains = [1.0 if t in gold_n else 0.0 for t in r[:k_ndcg]]
    idcg = _dcg([1.0] * min(len(gold_n), k_ndcg))
    ndcg = (_dcg(gains) / idcg) if idcg > 0 else 0.0
    return round(min(1.0, precision), 4), round(min(1.0, recall), 4), round(ndcg, 4)


def _span_hit(content: str, spans: list[str]) -> float:
    valid = [s for s in spans if len(re.sub(r"\s+", " ", s or "")) >= 8]
    if not valid:
        return 1.0
    text = re.sub(r"\s+", " ", (content or "").lower())
    hit = sum(1 for s in valid if re.sub(r"\s+", " ", s).lower()[:60] in text)
    return hit / len(valid)


def _set_f1(pred: set[str], gold: set[str]) -> float:
    if not pred or not gold:
        return float(bool(pred & gold))
    inter = len(pred & gold)
    if inter == 0:
        return 0.0
    p, r = inter / len(pred), inter / len(gold)
    return round(2 * p * r / (p + r), 4)


def _compliance_hit(content: str, redlines: list[str]) -> float:
    if not redlines:
        return 1.0
    text = (content or "").lower()
    bad = sum(1 for r in redlines if str(r).lower() in text)
    return max(0.0, 1.0 - bad)


# --- T1 文献综述 -----------------------------------------------------------
def _citation_consistency(content: str, answer: Answer) -> float:
    """正文引用标记 ↔ 文末参考文献 的双向覆盖率（[LITERAS] 引用一致性近似）。

    方法：抽出正文中所有 [sN]/[N] 标记，解析文末参考文献条目，比较序号集合：
    consistency = |标记序号 ∩ 条目序号| / |标记序号|。无标记则 0。
    """
    from ..adapters.base import extract_citation_markers, parse_reference_block

    def _num(marker: str) -> str:
        return re.sub(r"\D", "", marker)

    markers = extract_citation_markers(content)
    if not markers:
        return 0.0
    entries = parse_reference_block(content)
    if not entries:
        return 0.0
    mset = {_num(m) for m in markers}
    eset = {_num(e.marker) for e in entries}
    hit = len(mset & eset)
    return round(hit / len(mset), 4)


def _obj_t1(task: Task, answer: Answer, key: dict):
    recall, missed = _key_point_recall(answer.content, key.get("key_points", []))
    cres = _citation_resolution(answer)
    struct = _structure_coverage(answer.content, "T1")
    comp = _compliance_hit(answer.content, key.get("redlines", []))
    ccons = _citation_consistency(answer.content, answer)   # [LITERAS] 引用一致性
    score = 100 * (0.40 * recall + 0.20 * cres + 0.15 * ccons + 0.15 * struct + 0.10 * comp)
    tags = []
    if recall < 0.6:
        tags.append(E_MISSED)
    if cres < 0.5 or ccons < 0.5:
        tags.append(E_CITATION)
    if struct < 0.5:
        tags.append(E_LOGIC)
    if comp < 1.0:
        tags.append(E_COMPLIANCE)
    return ({"key_point_recall": round(recall, 4), "citation_resolution": round(cres, 4),
             "citation_consistency": ccons, "structure_coverage": round(struct, 4),
             "compliance": round(comp, 4), "missed_key_points": missed},
            round(score, 2), tags)


# --- T2 开题与实验设计 -----------------------------------------------------
def _obj_t2(task: Task, answer: Answer, key: dict):
    recall, missed = _key_point_recall(answer.content, key.get("key_points", []))
    elems = key.get("experiment_elements", ["数据集", "指标", "基线", "预期"])
    ecov = sum(1 for e in elems if str(e).lower() in (answer.content or "").lower()) / max(1, len(elems))
    fals = 1.0 if re.search(r"(若|如果|当|则|否则|不优于|没有显著|未能|至少|优于|低于)",
                            answer.content or "") else 0.0
    comp = _compliance_hit(answer.content, key.get("redlines", []))
    score = 100 * (0.35 * recall + 0.35 * ecov + 0.20 * fals + 0.10 * comp)
    tags = []
    if recall < 0.6 or ecov < 0.6:
        tags.append(E_MISSED)
    if not fals:
        tags.append(E_LOGIC)
    if comp < 1.0:
        tags.append(E_COMPLIANCE)
    return ({"key_point_recall": round(recall, 4), "experiment_element_cov": round(ecov, 4),
             "falsifiability": fals, "compliance": round(comp, 4),
             "missed_key_points": missed}, round(score, 2), tags)


# --- T3 学术检索 -----------------------------------------------------------
def _obj_t3(task: Task, answer: Answer, key: dict):
    gold = [d.get("title", "") if isinstance(d, dict) else str(d)
            for d in key.get("gold_docs", [])]
    retrieved = [c.title for c in answer.citations if c.title]
    if not retrieved:
        retrieved = [re.sub(r"^\d+[\.、]\s*", "", ln).strip()
                     for ln in (answer.content or "").splitlines() if ln.strip()][:20]
    p, r, n = _precision_recall_ndcg(retrieved, gold)
    score = 100 * (0.40 * p + 0.30 * r + 0.30 * n)
    tags = [E_RETRIEVAL] if (r < 0.5 or p < 0.3) else []
    return ({"precision@10": p, "recall@20": r, "ndcg@10": n,
             "retrieved": len(retrieved), "gold": len(gold)}, round(score, 2), tags)


# --- T4 论文深度问答 -------------------------------------------------------
def _obj_t4(task: Task, answer: Answer, key: dict):
    f1 = token_f1(answer.content, key.get("gold_answer", ""))
    span = _span_hit(answer.content, key.get("gold_spans", []))
    comp = _compliance_hit(answer.content, key.get("redlines", []))
    score = 100 * (0.50 * f1 + 0.40 * span + 0.10 * comp)
    tags = []
    if f1 < 0.4:
        tags.append(E_FACTUAL)
    if span < 0.5:
        tags.append(E_CITATION)
    if comp < 1.0:
        tags.append(E_COMPLIANCE)
    return ({"answer_f1": f1, "evidence_span_hit": round(span, 4),
             "compliance": round(comp, 4)}, round(score, 2), tags)


# --- T5 引用核对 -----------------------------------------------------------
VALID_VERDICTS = ("supported", "unrelated", "nonexistent")


# 兼容外部 Agent 的多种输出形态：
#   {"verdict": "supported", ...} / verdict: supported / 裸词 supported / 长文本内含 JSON
_VERDICT_RE = re.compile(
    r"[\"'`]?\bverdict\b[\"'`]?\s*[:=]\s*[\"'`]?(\w+)", re.I)


def _parse_verdict(answer: Answer) -> str:
    """提取 T5 三分类判定。对不同接入方式（HTTP/CLI/裸模型）保持同一口径。"""
    # 1) 适配层已解析好的 verdict
    v = str(answer.meta.get("verdict", "")).strip().lower()
    if v in VALID_VERDICTS:
        return v
    text = (answer.content or "").strip()
    # 2) 输出为 JSON（或长回答里嵌了 JSON 片段）
    m = _VERDICT_RE.search(text)
    if m:
        cand = m.group(1).strip().lower()
        if cand in VALID_VERDICTS:
            return cand
    # 3) 裸词开头（supported / unrelated / nonexistent）
    head = text.lower()
    for cand in VALID_VERDICTS:
        if head.startswith(cand):
            return cand
    return "none"


def _obj_t5(task: Task, answer: Answer, key: dict):
    gold = str(key.get("verdict", "")).strip().lower()
    pred = _parse_verdict(answer)
    correct = 1.0 if (gold and pred == gold) else 0.0
    # 伪造引用未被检出是最严重的失败，单独惩罚
    forged_missed = 1.0 if (gold == "nonexistent" and pred != "nonexistent") else 0.0
    score = 100 * (0.8 * correct + 0.2 * (1.0 - forged_missed))
    tags = []
    if not correct:
        tags.append(E_FACTUAL if gold != "nonexistent" else E_CITATION)
    # construct 用于 [CorrectFaith] 的分组诊断：
    #   real_supported / explicit_unrelated / cross_pair / mutated_title
    construct = str(key.get("construct", "")).strip() or (
        "real_supported" if gold == "supported" else "explicit_unrelated")
    return ({"verdict_pred": pred, "verdict_gold": gold, "correct": correct,
             "forged_missed": forged_missed, "construct": construct},
            round(score, 2), tags)


# --- T6 学术写作 -----------------------------------------------------------
def _obj_t6(task: Task, answer: Answer, key: dict):
    rouge = lcs_rouge(answer.content, key.get("reference_answer", ""))
    # 结构合法性：outline 必须是多级 markdown 列表
    kind = task.context.get("writing_type", "")
    if kind == "outline":
        items = re.findall(r"^\s*([-*]|\d+\.)\s+\S", answer.content or "", re.M)
        schema = min(1.0, len(items) / max(3, key.get("min_outline_items", 6)))
    else:
        schema = 1.0
    # 与源材料一致性：不出现无源断言的粗粒度代理——长度与参考的偏离度
    ref_len = max(1, len(key.get("reference_answer", "")))
    ratio = len(answer.content or "") / ref_len
    consistency = 1.0 - min(1.0, abs(math.log(max(ratio, 0.05))) / math.log(6))
    score = 100 * (0.60 * rouge + 0.25 * schema + 0.15 * consistency)
    tags = []
    if rouge < 0.25:
        tags.append(E_MISSED)
    if ratio > 3:
        tags.append(E_VERBOSITY)
    return ({"rouge_l": rouge, "schema_valid": round(schema, 4),
             "length_ratio": round(ratio, 3), "consistency": round(consistency, 4)},
            round(score, 2), tags)


# --- T7 研究思路 Agent 多轮对话 --------------------------------------------
def _obj_t7(task: Task, answer: Answer, key: dict):
    expected = {str(t).lower() for t in key.get("expected_tools", ["retrieve_papers"])}
    called = {str(c.get("name", "")).lower() for c in answer.tool_calls}
    tool_acc = 1.0 if (expected & called) else 0.0
    cited = 1.0 if (re.search(r"\[(s|r)?\d+\]", answer.content or "") or answer.citations) else 0.0
    # 多轮收敛：是否给出可执行的下一步（列表/编号/建议）
    conv = 1.0 if re.search(r"(建议|下一步|可以|应当|推荐|方案)", answer.content or "") else 0.0
    score = 100 * (0.50 * tool_acc + 0.30 * cited + 0.20 * conv)
    tags = []
    if not tool_acc:
        tags.append(E_TOOL)
    if not cited:
        tags.append(E_CITATION)
    return ({"tool_accuracy": tool_acc, "citation_rate": cited,
             "convergence": conv, "tools_called": sorted(called)}, round(score, 2), tags)


# --- T8 多步工具工作流 -----------------------------------------------------
def _obj_t8(task: Task, answer: Answer, key: dict):
    expected = {str(t).lower() for t in key.get("expected_tools", [])}
    called = {str(c.get("name", "")).lower() for c in answer.tool_calls}
    tool_f1 = _set_f1(called, expected) if expected else 1.0
    need = key.get("required_sections", [])
    covered = sum(1 for s in need if str(s).lower() in (answer.content or "").lower())
    schema = covered / max(1, len(need)) if need else 1.0
    score = 100 * (0.60 * tool_f1 + 0.40 * schema)
    tags = []
    if tool_f1 < 0.6:
        tags.append(E_TOOL)
    if schema < 0.6:
        tags.append(E_MISSED)
    return ({"tool_chain_f1": tool_f1, "artifact_coverage": round(schema, 4),
             "tools_called": sorted(called)}, round(score, 2), tags)


# --- 统一入口 -------------------------------------------------------------
_HANDLERS = {
    "T1": _obj_t1, "T2": _obj_t2, "T3": _obj_t3, "T4": _obj_t4,
    "T5": _obj_t5, "T6": _obj_t6, "T7": _obj_t7, "T8": _obj_t8,
}


def compute_objective(task: Task, answer: Answer, key: dict | None = None):
    """返回 (metrics, score_0_100, error_tags)。"""
    key = key or {}
    if not answer.ok:
        return ({"error": answer.meta.get("error", "empty answer")}, 0.0, [E_FACTUAL])
    handler = _HANDLERS.get(task.family)
    if handler is None:
        return ({}, 0.0, [])
    return handler(task, answer, key)
