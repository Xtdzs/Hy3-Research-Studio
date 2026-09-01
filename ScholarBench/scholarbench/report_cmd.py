"""从已有结果生成报告：python -m scholarbench.report_cmd --results results --out eval_results"""
from __future__ import annotations

import argparse

from .attribution import analyze, render_markdown as attr_md
from .report import generate
from .schema import EvalResult, read_jsonl


def main() -> None:
    ap = argparse.ArgumentParser(description="生成评测报告")
    ap.add_argument("--results", default="results/results.jsonl")
    ap.add_argument("--out", default="eval_results")
    ap.add_argument("--title", default="ScholarBench 评测报告")
    args = ap.parse_args()

    rows = read_jsonl(args.results)
    results = []
    for d in rows:
        r = EvalResult(**{k: v for k, v in d.items()
                          if k in EvalResult.__dataclass_fields__ and k != "rubric"})
        from .schema import RubricScore
        r.rubric = [RubricScore(**s) for s in d.get("rubric", [])]
        results.append(r)
    if not results:
        print("没有结果，请先运行：python -m scholarbench.run")
        return

    from pathlib import Path
    out = generate(results, args.out, args.title)
    attr = analyze(results)
    Path(args.out, "attribution.md").write_text(attr_md(attr), encoding="utf-8")
    print(f"报告已生成：{out['dir']}（图表 {len(out['charts'])} 个）")


if __name__ == "__main__":
    main()
