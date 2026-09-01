"""数据集统计：python -m scholarbench.stats_cmd"""
from __future__ import annotations

import argparse
import json

from .dataset import dataset_stats, existing_families


def main() -> None:
    ap = argparse.ArgumentParser(description="查看数据集统计")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    stats = dataset_stats()
    if not stats["families"]:
        print("数据集为空，请先运行：python -m scholarbench.build_dataset --offline")
        return
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return
    print(f"版本 {stats['version']} · 共 {stats['total']} 条 · "
          f"已构建任务族：{', '.join(existing_families()) or '无'}")
    for fam, d in stats["families"].items():
        diff = " ".join(f"{k}={v}" for k, v in sorted(d["difficulty"].items()))
        print(f"  {fam:<22} {d['count']:>3} 条   {diff}")


if __name__ == "__main__":
    main()
