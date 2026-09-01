"""一致性检验：自动 Rubric 分 vs 人工标注分 + 标注者间一致性。

纯标准库实现（不依赖 numpy/scipy），保证零额外依赖即可复现：
    QWK      二次加权 Kappa（5 档有序分类的标准指标）
    Spearman 秩相关（单调一致性）
    MAE      逐维平均绝对误差
    ICC-like 标注者间一致性（两组人工标注时计算）

参考标准（规划 E2）：QWK ≥ 0.6、Spearman ≥ 0.7、逐维 MAE ≤ 0.8
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from .dataset import version_dir
from .metrics.rubric import DIM_ORDER
from .schema import read_jsonl

MIN_S, MAX_S = 1, 5
K = MAX_S - MIN_S + 1


def _rank(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else 0.0


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(_rank(xs), _rank(ys))


def qwk(a: list[int], b: list[int]) -> float:
    """二次加权 Kappa。"""
    n = len(a)
    if n == 0:
        return 0.0
    o = [[0] * K for _ in range(K)]
    for x, y in zip(a, b):
        o[x - MIN_S][y - MIN_S] += 1
    wa = [sum(o[i]) for i in range(K)]
    wb = [sum(o[i][j] for i in range(K)) for j in range(K)]
    w = [[(i - j) ** 2 / ((K - 1) ** 2) for j in range(K)] for i in range(K)]
    num = sum(w[i][j] * o[i][j] for i in range(K) for j in range(K))
    den = sum(w[i][j] * (wa[i] * wb[j]) / n for i in range(K) for j in range(K))
    return 1 - num / den if den else 0.0


def mae(a: list[float], b: list[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def compare(auto: dict[str, dict], human: dict[str, dict],
            annotator: str | None = None) -> dict:
    """auto/human: {task_id: {"D1": score, ...}}"""
    per_dim: dict[str, dict[str, list]] = defaultdict(lambda: {"auto": [], "human": []})
    for tid, hdims in human.items():
        adims = auto.get(tid)
        if not adims:
            continue
        for d in DIM_ORDER:
            if d in hdims and d in adims:
                per_dim[d]["auto"].append(float(adims[d]))
                per_dim[d]["human"].append(float(hdims[d]))

    out = {"n_paired": 0, "dims": {}, "overall": {}}
    all_auto: list[float] = []
    all_human: list[float] = []
    all_auto_i: list[int] = []
    all_human_i: list[int] = []
    for d in DIM_ORDER:
        if d not in per_dim or not per_dim[d]["auto"]:
            continue
        a, h = per_dim[d]["auto"], per_dim[d]["human"]
        all_auto += a
        all_human += h
        all_auto_i += [int(round(x)) for x in a]
        all_human_i += [int(round(x)) for x in h]
        out["dims"][d] = {
            "n": len(a),
            "mae": round(mae(a, h), 3),
            "spearman": round(spearman(a, h), 3),
            "qwk": round(qwk([int(round(x)) for x in a], [int(round(x)) for x in h]), 3),
            "auto_mean": round(sum(a) / len(a), 2),
            "human_mean": round(sum(h) / len(h), 2),
            "bias": round(sum(a) / len(a) - sum(h) / len(h), 2),  # >0 表示自动分偏高
        }
    out["n_paired"] = len(all_auto)
    if all_auto:
        out["overall"] = {
            "mae": round(mae(all_auto, all_human), 3),
            "spearman": round(spearman(all_auto, all_human), 3),
            "qwk": round(qwk(all_auto_i, all_human_i), 3),
            "bias": round(sum(all_auto) / len(all_auto) - sum(all_human) / len(all_human), 3),
        }
    return out


def load_auto(results: str | Path, system: str = "") -> dict[str, dict]:
    p = Path(results)
    files = sorted(p.glob("results_*.jsonl")) if p.is_dir() else [p]
    auto: dict[str, dict] = {}
    for f in files:
        for r in read_jsonl(f):
            if system and r.get("system") != system:
                continue
            dims = {s["dim"]: s["score"] for s in r.get("rubric", []) if s.get("score", 0) > 0}
            if dims:
                auto.setdefault(r["task_id"], {}).update(dims)
    return auto


def load_human(annotator: str | None = None) -> dict[str, dict]:
    labels = read_jsonl(version_dir() / "human_labels.jsonl")
    out: dict[str, dict] = {}
    for r in labels:
        if annotator and r.get("annotator") != annotator:
            continue
        if r.get("dims"):
            out.setdefault(r["task_id"], {}).update(r["dims"])
    return out


def inter_annotator(a: str, b: str) -> dict:
    """两组人工标注之间的一致性（作为自动分一致性的上限参照）。"""
    la = {r["task_id"]: r.get("dims", {}) for r in read_jsonl(version_dir() / "human_labels.jsonl")
          if r.get("annotator") == a}
    lb = {r["task_id"]: r.get("dims", {}) for r in read_jsonl(version_dir() / "human_labels.jsonl")
          if r.get("annotator") == b}
    return compare(la, lb)


def main() -> None:
    ap = argparse.ArgumentParser(description="一致性检验")
    ap.add_argument("--results", default="results")
    ap.add_argument("--system", default="")
    ap.add_argument("--annotator", default="")
    ap.add_argument("--inter", nargs=2, default=None,
                    help="比较两名标注者：--inter A B")
    args = ap.parse_args()

    if args.inter:
        res = inter_annotator(args.inter[0], args.inter[1])
        print("标注者间一致性：")
    else:
        res = compare(load_auto(args.results, args.system),
                      load_human(args.annotator or None))
        print("自动分 vs 人工标注一致性：")

    print(json.dumps(res, ensure_ascii=False, indent=2))
    ov = res.get("overall", {})
    if ov:
        print("\n判定（规划 E2 标准：QWK≥0.6 / Spearman≥0.7 / MAE≤0.8）")
        print(f"  QWK      {ov['qwk']:.3f}  {'✓' if ov['qwk'] >= 0.6 else '✗'}")
        print(f"  Spearman {ov['spearman']:.3f}  {'✓' if ov['spearman'] >= 0.7 else '✗'}")
        print(f"  MAE      {ov['mae']:.3f}  {'✓' if ov['mae'] <= 0.8 else '✗'}")


if __name__ == "__main__":
    main()
