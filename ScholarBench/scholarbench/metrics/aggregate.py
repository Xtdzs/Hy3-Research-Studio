"""指标聚合：总分 / 任务族分 / 难度曲线 / 8 维能力画像 / 错误分布。

合成规则：
    task_score     = α · objective + (1-α) · rubric      （α 见 schema.FAMILY_ALPHA）
    family_score   = mean(task_score)
    bench_score    = Σ family_weight · family_score（按已评测族归一化）
    capability(Cj) = 依赖 Cj 的任务族得分均值
"""
from __future__ import annotations

from collections import defaultdict

from ..schema import (CAPABILITIES, FAMILIES, FAMILY_CAPABILITIES,
                      FAMILY_WEIGHTS, EvalResult)


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else 0.0


def task_score(objective: float, rubric: float, alpha: float) -> float:
    return round(alpha * objective + (1 - alpha) * rubric, 2)


def aggregate(results: list[EvalResult]) -> dict:
    """把逐条结果聚合为系统级报告数据。"""
    by_system: dict[str, list[EvalResult]] = defaultdict(list)
    for r in results:
        by_system[r.system].append(r)

    out: dict[str, dict] = {}
    for system, rs in by_system.items():
        fam_scores: dict[str, list[float]] = defaultdict(list)
        fam_obj: dict[str, list[float]] = defaultdict(list)
        fam_rub: dict[str, list[float]] = defaultdict(list)
        diff_scores: dict[str, list[float]] = defaultdict(list)
        dim_scores: dict[str, list[float]] = defaultdict(list)
        errors: dict[str, int] = defaultdict(int)
        failed: list[dict] = []
        t5_diag: dict[str, dict] = {}

        for r in rs:
            fam_scores[r.family].append(r.task_score)
            fam_obj[r.family].append(r.objective_score)
            fam_rub[r.family].append(r.rubric_score)
            diff_scores[r.difficulty].append(r.task_score)
            for s in r.rubric:
                if s.score > 0:
                    dim_scores[s.dim].append(s.score)
            for e in r.errors:
                errors[e] += 1
            if r.task_score < 60 or r.errors:
                failed.append({"task_id": r.task_id, "family": r.family,
                               "difficulty": r.difficulty, "score": r.task_score,
                               "errors": r.errors})

        # [CorrectFaith] T5 分组诊断：正确性 vs 忠实度 vs 伪造检出
        t5_groups: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
        for r in rs:
            if r.family != "T5":
                continue
            c = r.objective.get("construct", "unknown")
            t5_groups[c]["n"] += 1
            t5_groups[c]["correct"] += float(r.objective.get("correct", 0.0))
        if t5_groups:
            t5_diag = {
                k: {"n": v["n"],
                    "accuracy": round(v["correct"] / max(1, v["n"]), 4)}
                for k, v in sorted(t5_groups.items())
            }
            t5_diag["_faithfulness"] = t5_diag.get(
                "cross_pair", {"n": 0, "accuracy": -1.0})    # [CorrectFaith] 忠实度探针
            t5_diag["_forgery_detection"] = t5_diag.get(
                "mutated_title", {"n": 0, "accuracy": -1.0})  # [FactCheck] 伪造引用检出

        family = {f: _mean(v) for f, v in fam_scores.items()}
        bench = sum(FAMILY_WEIGHTS.get(f, 0.0) * s for f, s in family.items())
        wsum = sum(FAMILY_WEIGHTS.get(f, 0.0) for f in family)
        bench = round(bench / wsum, 2) if wsum > 0 else 0.0

        cap_acc: dict[str, list[float]] = defaultdict(list)
        for fam, sc in family.items():
            for c in FAMILY_CAPABILITIES.get(fam, []):
                cap_acc[c].append(sc)
        capability = {c: _mean(v) for c, v in sorted(cap_acc.items())}

        out[system] = {
            "bench_score": bench,
            "family_scores": {f"{f} {FAMILIES.get(f, '')}": round(s, 2)
                              for f, s in sorted(family.items())},
            "family_objective": {f: _mean(v) for f, v in sorted(fam_obj.items())},
            "family_rubric": {f: _mean(v) for f, v in sorted(fam_rub.items())},
            "difficulty_curve": {d: _mean(diff_scores.get(d, []))
                                 for d in ("easy", "medium", "hard")},
            "rubric_dims": {d: _mean(v) for d, v in sorted(dim_scores.items())},
            "capability": {f"{c} {CAPABILITIES.get(c, '')}": v
                           for c, v in capability.items()},
            "error_distribution": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
            "n_samples": len(rs),
            "n_failed": len(failed),
            "failed_cases": sorted(failed, key=lambda x: x["score"])[:20],
            "t5_diagnostics": t5_diag,
        }
    return out


def leaderboard_rows(agg: dict) -> list[dict]:
    """按 bench_score 降序输出 Leaderboard 行。"""
    rows = []
    for system, d in agg.items():
        rows.append({
            "system": system,
            "bench_score": d["bench_score"],
            "n_samples": d["n_samples"],
            "easy": d["difficulty_curve"].get("easy", 0.0),
            "medium": d["difficulty_curve"].get("medium", 0.0),
            "hard": d["difficulty_curve"].get("hard", 0.0),
        })
    return sorted(rows, key=lambda r: -r["bench_score"])
