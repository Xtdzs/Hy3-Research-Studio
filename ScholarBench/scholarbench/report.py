"""报告生成：results.md / results.csv / failures.md / 能力雷达图 / 难度曲线。

matplotlib 为可选依赖，缺失时跳过图表并继续生成表格（保证报告一定能产出）。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .dataset import dataset_stats
from .metrics.aggregate import leaderboard_rows
from .schema import EvalResult

DIM_NAMES = {
    "D1": "事实准确性", "D2": "证据可追溯性", "D3": "专业术语正确性",
    "D4": "覆盖与完整性", "D5": "逻辑与结构", "D6": "安全合规",
    "D7": "用户可理解性",
}


def _md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join([" --- "] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in r) + " |")
    return "\n".join(out)


def render_markdown(agg: dict, stats: dict | None = None,
                    title: str = "ScholarBench 评测报告") -> str:
    lines = [f"# {title}", ""]
    if stats:
        lines += [f"- 数据集版本：`{stats['version']}`，共 {stats.get('total', 0)} 条，"
                  f"对抗子集 {stats.get('adversarial', 0)} 条"]
    lines += ["", "## Leaderboard", ""]
    rows = [[r["system"], r["bench_score"], r["n_samples"],
             r["easy"], r["medium"], r["hard"]]
            for r in leaderboard_rows(agg)]
    lines.append(_md_table(["系统", "BenchScore", "样本数", "easy", "medium", "hard"], rows))

    for system, d in sorted(agg.items(), key=lambda kv: -kv[1]["bench_score"]):
        lines += ["", f"## {system}", "",
                  f"**BenchScore = {d['bench_score']}**（样本 {d['n_samples']}，"
                  f"低于 60 分或带错误标签 {d['n_failed']} 条）", ""]

        lines += ["### 各任务族得分", ""]
        lines.append(_md_table(
            ["任务族", "客观分", "Rubric 分", "族得分"],
            [[f, d["family_objective"].get(f[:2], "-"),
              d["family_rubric"].get(f[:2], "-"), s]
             for f, s in d["family_scores"].items()]))

        lines += ["", "### 难度曲线", ""]
        dc = d["difficulty_curve"]
        lines.append(_md_table(["难度", "得分"],
                               [[k, dc.get(k, "-")] for k in ("easy", "medium", "hard")]))

        if d["rubric_dims"]:
            lines += ["", "### Rubric 各维均分（1-5）", ""]
            lines.append(_md_table(["维度", "均分"],
                                   [[f"{k} {DIM_NAMES.get(k, '')}", v]
                                    for k, v in d["rubric_dims"].items()]))

        if d["capability"]:
            lines += ["", "### 能力画像（族分映射）", ""]
            lines.append(_md_table(["能力", "得分"],
                                   [[k, v] for k, v in d["capability"].items()]))

        if d.get("t5_diagnostics"):
            lines += ["", "### T5 引用核对诊断（[CorrectFaith] / [FactCheck]）", ""]
            diag = d["t5_diagnostics"]
            rows = [[k, v["n"], v["accuracy"]] for k, v in diag.items()
                    if not k.startswith("_") and v["n"] > 0]
            for key, label in (("_faithfulness", "faithfulness"), ("_forgery_detection", "forgery")):
                sub = diag.get(key, {})
                if sub.get("n", 0) > 0:
                    rows.append([f"**{label} ({key[1:]})**", sub["n"], sub["accuracy"]])
            lines.append(_md_table(["分组", "样本", "准确率"], rows))

        if d["error_distribution"]:
            lines += ["", "### 失败归因分布", ""]
            lines.append(_md_table(["错误类型", "次数"],
                                   [[k, v] for k, v in d["error_distribution"].items()]))

        if d["failed_cases"]:
            lines += ["", "### 典型失败 case（得分最低 10 条）", ""]
            lines.append(_md_table(
                ["task_id", "族", "难度", "得分", "归因"],
                [[c["task_id"], c["family"], c["difficulty"], c["score"],
                  ", ".join(c["errors"]) or "-"]
                 for c in d["failed_cases"][:10]]))
    return "\n".join(lines) + "\n"


def render_failures(results: list[EvalResult], top: int = 20) -> str:
    bad = [r for r in results if r.task_score < 60 or r.errors]
    bad.sort(key=lambda r: r.task_score)
    lines = ["# 失败 case 归因", "", f"共 {len(bad)} 条低分样本，列出得分最低 {top} 条。", ""]
    for r in bad[:top]:
        lines += [f"## {r.task_id}（{r.family} / {r.difficulty}）· {r.system} · "
                  f"{r.task_score} 分", "",
                  f"- 客观分 {r.objective_score} / Rubric 分 {r.rubric_score}",
                  f"- 归因标签：{', '.join(r.errors) or '无'}",
                  f"- 客观指标：`{json.dumps(r.objective, ensure_ascii=False)[:400]}`"]
        low = [s for s in r.rubric if s.score <= 2]
        for s in low:
            lines.append(f"- **{s.dim} {DIM_NAMES.get(s.dim, '')} {s.score} 分**：{s.reason}")
        lines.append("")
    return "\n".join(lines)


def write_csv(path: Path, results: list[EvalResult]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "family", "difficulty", "system", "objective_score",
                    "rubric_score", "task_score", "errors"])
        for r in results:
            w.writerow([r.task_id, r.family, r.difficulty, r.system,
                        r.objective_score, r.rubric_score, r.task_score,
                        ";".join(r.errors)])


def _charts(agg: dict, out_dir: Path) -> list[str]:
    try:
        import matplotlib  # noqa: PLC0415
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415
    except ImportError:
        return []
    made = []
    try:
        from .config_matplotlib import apply_cjk  # noqa: PLC0415
        apply_cjk()
    except Exception:  # noqa: BLE001
        pass

    for system, d in agg.items():
        cap = d.get("capability", {})
        if len(cap) >= 3:
            labels = list(cap.keys())
            vals = list(cap.values())
            vals += vals[:1]
            angles = [i * 2 * 3.141592653589793 / len(labels) for i in range(len(labels))]
            angles += angles[:1]
            fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
            ax.plot(angles, vals)
            ax.fill(angles, vals, alpha=0.25)
            ax.set_xticks(angles[:-1])
            ax.set_xticklabels(labels, fontsize=8)
            ax.set_title(f"{system} 能力画像", fontsize=11)
            p = out_dir / f"capability_{system.replace(':', '_').replace('/', '_')}.png"
            fig.tight_layout()
            fig.savefig(p, dpi=140)
            plt.close(fig)
            made.append(str(p))
    return made


def generate(results: list[EvalResult], out_dir: str | Path,
             title: str = "ScholarBench 评测报告") -> dict:
    from .metrics import aggregate
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    agg = aggregate(results)

    (out / "results.md").write_text(
        render_markdown(agg, dataset_stats(), title), encoding="utf-8")
    (out / "failures.md").write_text(render_failures(results), encoding="utf-8")
    write_csv(out / "results.csv", results)
    (out / "aggregate.json").write_text(
        json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")

    charts = []
    try:
        charts = _charts(agg, out)
    except Exception as exc:  # noqa: BLE001
        print(f"[report] 图表生成跳过：{exc}")
    return {"dir": str(out), "charts": charts, "systems": list(agg)}
