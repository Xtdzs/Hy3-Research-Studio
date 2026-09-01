"""跨模型 Leaderboard 汇总：读各模型 results/<model>/aggregate.json → markdown 表。

    python -m scholarbench report_leaderboard --models hy3,deepseek-chat
    python -m scholarbench report_leaderboard --models hy3 --out README_LEADERBOARD.md

支持自动模式：--auto 扫描 results/ 下所有含 aggregate.json 的子目录。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load(results_root: Path, names: list[str] | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    candidates = []
    if names:
        for n in names:
            candidates.append((n, results_root / n / "aggregate.json"))
    else:  # auto 扫描
        for d in sorted(results_root.iterdir()):
            if d.is_dir() and (d / "aggregate.json").exists():
                candidates.append((d.name, d / "aggregate.json"))
    for name, p in candidates:
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if name in data:            # aggregate.json 顶层含系统名
            out[name] = data[name]
        elif data:                  # 取第一个系统（单模型跑批）
            out[name] = next(iter(data.values()))
    return out


def _family(agg: dict, prefix: str) -> float | None:
    fs = agg.get("family_scores", {})
    for k, v in fs.items():
        if k.startswith(prefix):
            return float(v)
    return None


def render(aggs: dict[str, dict], title: str = "ScholarBench 跨模型 Leaderboard") -> str:
    rows = sorted(aggs.items(), key=lambda kv: -kv[1].get("bench_score", 0))
    lines = [f"# {title}", ""]
    lines += ["| 排名 | 系统 | BenchScore | T3 | T5 | T6 | T7 | T8 | easy | medium | hard | 样本 |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    fams = ["T3", "T5", "T6", "T7", "T8"]
    for i, (name, a) in enumerate(rows, 1):
        dc = a.get("difficulty_curve", {})
        line = [str(i), name, f"{a.get('bench_score', 0):.2f}"]
        for f in fams:
            v = _family(a, f)
            line.append(f"{v:.1f}" if v is not None else "-")
        line += [f"{dc.get('easy', -1):.1f}", f"{dc.get('medium', -1):.1f}",
                 f"{dc.get('hard', -1):.1f}", str(a.get("n_samples", 0))]
        lines.append("| " + " | ".join(line) + " |")
    lines += ["", "> 指标说明：BenchScore 为族加权总分（0-100）；T3–T8 为各任务族得分；",
              "> 复现：`powershell -File eval_models.ps1`（各模型 Key 见脚本配置区）。", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="跨模型 Leaderboard 汇总")
    ap.add_argument("--models", nargs="*", help="模型目录名列表")
    ap.add_argument("--auto", action="store_true", help="自动扫描 results/ 下所有子目录")
    ap.add_argument("--root", default="results")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"没有结果目录 {root}，请先运行评测。")
        return
    names = None if args.auto else (args.models or [])
    aggs = _load(root, names)
    if not aggs:
        print(f"{root} 下没有可汇总的结果（需含 aggregate.json）。")
        return
    md = render(aggs)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"Leaderboard 已写入 {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
