"""失败归因：把低分样本归到统一的错误类型体系，并给出交叉分布与代表 case。

错误类型（9 类，对外可复用）：
    FACTUAL_HALLUCINATION  无源断言、数字/方法张冠李戴
    UNSUPPORTED_CITATION   引用不存在，或引用与论断不对应
    MISSED_KEY_POINT       预设关键点未覆盖
    TERM_MISUSE            术语生造、误用、堆砌
    LOGIC_GAP              跳步、循环论证、前后矛盾
    RETRIEVAL_MISS         检索未召回关键文献
    TOOL_MISUSE            该调的工具没调 / 调错 / 参数错
    COMPLIANCE_RISK        越界建议、缺免责、PII、长段复述
    VERBOSITY              注水、重复、信噪比低
"""
from __future__ import annotations

from collections import defaultdict

from .schema import EvalResult

ERROR_LABELS = {
    "FACTUAL_HALLUCINATION": "无源断言 / 幻觉",
    "UNSUPPORTED_CITATION": "引用不实或不对应",
    "MISSED_KEY_POINT": "关键点未覆盖",
    "TERM_MISUSE": "术语误用 / 堆砌",
    "LOGIC_GAP": "逻辑跳步 / 矛盾",
    "RETRIEVAL_MISS": "检索遗漏",
    "TOOL_MISUSE": "工具调用错误",
    "COMPLIANCE_RISK": "合规风险",
    "VERBOSITY": "注水 / 信噪比低",
}


def analyze(results: list[EvalResult], threshold: float = 60.0) -> dict:
    by_error: dict[str, int] = defaultdict(int)
    cross: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_family: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_difficulty: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    representatives: dict[str, dict] = {}

    total_bad = 0
    for r in results:
        bad = r.task_score < threshold or bool(r.errors)
        if not r.errors:
            continue
        if bad:
            total_bad += 1
        for e in r.errors:
            by_error[e] += 1
            cross[e][r.family] += 1
            by_family[r.family][e] += 1
            by_difficulty[r.difficulty][e] += 1
            cur = representatives.get(e)
            if cur is None or r.task_score < cur["score"]:
                representatives[e] = {
                    "task_id": r.task_id, "system": r.system,
                    "family": r.family, "difficulty": r.difficulty,
                    "score": r.task_score,
                    "objective": r.objective,
                    "reasons": [s.reason for s in r.rubric if s.score <= 2][:2],
                }

    ranked = sorted(by_error.items(), key=lambda kv: -kv[1])
    return {
        "n_results": len(results),
        "n_flagged": total_bad,
        "flag_rate": round(total_bad / max(1, len(results)), 3),
        "error_counts": [{"type": k, "label": ERROR_LABELS.get(k, k), "count": v}
                         for k, v in ranked],
        "by_family": {f: dict(sorted(d.items(), key=lambda kv: -kv[1]))
                      for f, d in sorted(by_family.items())},
        "by_difficulty": {d: dict(sorted(m.items(), key=lambda kv: -kv[1]))
                          for d, m in sorted(by_difficulty.items())},
        "representatives": representatives,
    }


def render_markdown(attr: dict) -> str:
    lines = ["# 失败归因分析", "",
             f"- 样本 {attr['n_results']} 条，其中 {attr['n_flagged']} 条被标记"
             f"（{attr['flag_rate'] * 100:.1f}%）", "",
             "## 错误类型分布", "",
             "| 错误类型 | 说明 | 次数 |", "| --- | --- | --- |"]
    for e in attr["error_counts"]:
        lines.append(f"| {e['type']} | {e['label']} | {e['count']} |")

    lines += ["", "## 错误类型 × 任务族", ""]
    fams = sorted({f for d in attr["by_family"].values() for f in []} |
                  set(attr["by_family"].keys()))
    lines.append("| 任务族 | " + " | ".join(f for f in fams) + " |")
    lines.append("|" + "|".join([" --- "] * (len(fams) + 1)) + "|")
    all_types = [e["type"] for e in attr["error_counts"]]
    for t in all_types:
        row = [t] + [str(attr["by_family"].get(f, {}).get(t, 0)) for f in fams]
        lines.append("| " + " | ".join(row) + " |")

    lines += ["", "## 代表 case（每类得分最低的一条）", ""]
    for t, rep in attr["representatives"].items():
        lines += [f"### {t} — {rep['task_id']}（{rep['family']}/{rep['difficulty']}，"
                  f"{rep['score']} 分）", "",
                  f"- 系统：{rep['system']}",
                  f"- 客观指标：`{rep['objective']}`"]
        for rsn in rep.get("reasons", []):
            lines.append(f"- 评审意见：{rsn}")
        lines.append("")
    return "\n".join(lines)
