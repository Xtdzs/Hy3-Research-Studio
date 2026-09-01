"""半自动人工标注 CLI：自动分作为建议分，人工逐维覆写。

    python -m scholarbench.annotate --results results --system studio \
        --sample 0.3 --annotator A

产出：data/v0.1/human_labels.jsonl
    {"task_id","system","annotator","dims":{"D1":4,...},"overridden":["D2"],"note":""}
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from .dataset import version_dir
from .metrics.rubric import DIM_ORDER
from .schema import read_jsonl, write_jsonl

LABEL_FILE = "human_labels.jsonl"


def _stratified_sample(rows: list[dict], frac: float, seed: int = 42) -> list[dict]:
    """按难度分层抽样，保证 easy/medium/hard 都有代表。"""
    by_diff: dict[str, list[dict]] = {}
    for r in rows:
        by_diff.setdefault(r.get("difficulty", "medium"), []).append(r)
    rng = random.Random(seed)
    out = []
    for diff, group in by_diff.items():
        k = max(1, round(len(group) * frac))
        out += rng.sample(group, min(k, len(group)))
    return out


def _auto_dims(row: dict) -> dict[str, float]:
    return {s["dim"]: s["score"] for s in row.get("rubric", []) if s.get("score", 0) > 0}


def run(args) -> None:
    results_path = Path(args.results)
    if results_path.is_dir():
        files = sorted(results_path.glob("results_*.jsonl"))
        rows = []
        for f in files:
            rows += read_jsonl(f)
    else:
        rows = read_jsonl(results_path)

    if args.system:
        rows = [r for r in rows if r.get("system") == args.system]
    if not rows:
        print("没有可标注的结果，请先运行评测。")
        return

    sample = _stratified_sample(rows, args.sample)
    print(f"共 {len(rows)} 条结果，抽取 {len(sample)} 条进行人工标注。\n")

    out_path = version_dir() / LABEL_FILE
    existing = read_jsonl(out_path)
    done = {(r["task_id"], r["annotator"]) for r in existing}
    labels = list(existing)

    for i, row in enumerate(sample, 1):
        tid = row.get("task_id", "")
        if (tid, args.annotator) in done:
            print(f"[{i}/{len(sample)}] {tid} 已标注，跳过")
            continue
        auto = _auto_dims(row)
        print("=" * 70)
        print(f"[{i}/{len(sample)}] {tid} · {row.get('family')} / "
              f"{row.get('difficulty')} · {row.get('system')}")
        print(f"自动分：{auto}")
        print(f"客观指标：{json.dumps(row.get('objective', {}), ensure_ascii=False)[:300]}")
        print("-" * 70)
        print("请逐维打分（1-5），直接回车=采用自动分，q=结束本次标注")
        dims: dict[str, float] = {}
        overridden: list[str] = []
        for d in DIM_ORDER:
            default = auto.get(d, "")
            raw = input(f"  {d}（自动 {default}）：").strip()
            if raw.lower() == "q":
                print("已中断。")
                _save(out_path, labels)
                return
            if raw == "":
                if default != "":
                    dims[d] = float(default)
                continue
            try:
                v = float(raw)
                if 1 <= v <= 5:
                    dims[d] = v
                    if default != "" and abs(v - float(default)) >= 1:
                        overridden.append(d)
            except ValueError:
                pass
        note = input("  备注（可空）：").strip()
        labels.append({"task_id": tid, "system": row.get("system", ""),
                       "annotator": args.annotator, "dims": dims,
                       "overridden": overridden, "note": note})
    _save(out_path, labels)


def _save(path: Path, labels: list[dict]) -> None:
    write_jsonl(path, labels)
    print(f"\n标注已保存：{path}（累计 {len(labels)} 条）")


def main() -> None:
    ap = argparse.ArgumentParser(description="ScholarBench 半自动人工标注")
    ap.add_argument("--results", default="results")
    ap.add_argument("--system", default="")
    ap.add_argument("--sample", type=float, default=0.3)
    ap.add_argument("--annotator", default="A")
    run(ap.parse_args())


if __name__ == "__main__":
    main()
