"""End-to-end evaluation harness (方案 §12).

Compares three systems on the same tasks and reports the metrics from the design
doc: total tokens, wall-clock timings (TTFP/TTFE/TTFR/TTR), compression ratio,
and evidence coverage (Recall@key_points, judged by Hy3 itself).

Systems:
  - baseline_A  : Direct Chat  (one-shot "write me a survey", no retrieval)
  - baseline_B  : Search + Single-pass report (retrieval, NO compression/grounding)
  - studio      : full Hy3 Research Studio pipeline

Usage:
    # from project root, with HY3_API_KEY configured (.env or env var)
    python -m tests.evaluate                # run all tasks
    python -m tests.evaluate --tasks A1 B1  # subset
    python -m tests.evaluate --quick        # only baseline_B vs studio, 2 tasks
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

try:  # ensure UTF-8 output on Windows GBK consoles
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.hy3_client import Hy3Client  # noqa: E402
from backend.models import ResearchRequest, ResearchTask, TaskType  # noqa: E402
from backend.pipeline import ResearchPipeline  # noqa: E402
from backend.search import gather_sources  # noqa: E402

TASKS_FILE = Path(__file__).parent / "benchmark_tasks.json"


# --- system runners ----------------------------------------------------------
def run_studio(task_cfg: dict) -> dict:
    client = Hy3Client()
    req = ResearchRequest(
        query=task_cfg["query"],
        task_type=TaskType(task_cfg["task_type"]),
        depth="standard",
    )
    task = ResearchTask(task_id="eval_" + task_cfg["id"], request=req)
    pipe = ResearchPipeline(task, client)
    t0 = time.time()
    for _event, _payload in pipe.run():  # drain the generator
        pass
    report = "\n\n".join(f"## {s.section_title}\n{s.content}" for s in task.sections)
    return {
        "report": report,
        "tokens": client.usage.total_tokens,
        "wall": round(time.time() - t0, 1),
        "timings": task.metrics.get("timings", {}),
        "compression": task.metrics.get("compression", {}),
        "sources": len(task.sources),
    }


def run_baseline_A(task_cfg: dict) -> dict:
    """Direct Chat: single one-shot generation, no retrieval (方案 Baseline A)."""
    client = Hy3Client()
    t0 = time.time()
    report = client.chat(
        [
            {"role": "system", "content": "你是研究助手，请撰写结构完整的中文研究综述。"},
            {"role": "user", "content": f"请就以下主题写一篇结构完整的文献综述，包含背景、方法分类、评测、局限与研究空白：\n{task_cfg['query']}"},
        ],
        temperature=0.5,
    )
    return {"report": report, "tokens": client.usage.total_tokens,
            "wall": round(time.time() - t0, 1), "sources": 0}


def run_baseline_B(task_cfg: dict) -> dict:
    """Search + single-pass: retrieve, dump ALL raw abstracts into one prompt."""
    client = Hy3Client()
    t0 = time.time()
    docs = gather_sources([task_cfg["query"]], use_paper=True, per_query=12)[:12]
    block = "\n\n".join(
        f"[s{i+1}] {d.title}\n{d.abstract[:600]}" for i, d in enumerate(docs)
    )
    report = client.chat(
        [
            {"role": "system", "content": "你是研究助手，基于给定资料撰写综述，关键结论用 [sN] 标注引用。"},
            {"role": "user", "content": f"主题：{task_cfg['query']}\n\n资料：\n{block}\n\n请写一篇结构完整的综述。"},
        ],
        temperature=0.5,
    )
    return {"report": report, "tokens": client.usage.total_tokens,
            "wall": round(time.time() - t0, 1), "sources": len(docs)}


# --- evidence coverage judge (Recall@key_points) -----------------------------
def judge_coverage(report: str, key_points: list[str]) -> float:
    client = Hy3Client()
    kp = "\n".join(f"{i+1}. {p}" for i, p in enumerate(key_points))
    try:
        data = client.chat_json(
            [
                {"role": "system", "content": "你是严格的评审。判断报告是否覆盖每个关键点，只输出 JSON。"},
                {"role": "user", "content":
                 f"报告：\n{report[:6000]}\n\n关键点：\n{kp}\n\n"
                 f"请输出：{{\"covered\": [true/false, ...]}}，长度等于关键点数。"},
            ],
            temperature=0.0,
        )
        flags = data.get("covered", [])
        if not flags:
            return 0.0
        return round(sum(1 for f in flags if f) / len(key_points), 3)
    except Exception as exc:  # noqa: BLE001
        print(f"  [judge] failed: {exc}")
        return -1.0


# --- main --------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="*", help="task ids subset")
    ap.add_argument("--quick", action="store_true", help="only B vs studio, first 2 tasks")
    args = ap.parse_args()

    cfg = json.loads(TASKS_FILE.read_text(encoding="utf-8"))
    tasks = cfg["tasks"]
    if args.tasks:
        tasks = [t for t in tasks if t["id"] in args.tasks]
    if args.quick:
        tasks = tasks[:2]

    systems = {"baseline_A": run_baseline_A, "baseline_B": run_baseline_B, "studio": run_studio}
    if args.quick:
        systems.pop("baseline_A")

    rows = []
    for t in tasks:
        print(f"\n=== 任务 {t['id']}: {t['query']} ===")
        for name, runner in systems.items():
            print(f"  运行 {name} …")
            try:
                res = runner(t)
                cov = judge_coverage(res["report"], t["key_points"])
                rows.append({"task": t["id"], "system": name, "tokens": res["tokens"],
                             "wall": res["wall"], "coverage": cov,
                             "compression": res.get("compression", {}).get("compression_ratio", "-"),
                             "sources": res.get("sources", 0)})
                print(f"    tokens={res['tokens']} wall={res['wall']}s coverage={cov}")
            except Exception as exc:  # noqa: BLE001
                print(f"    ✗ {name} 失败: {exc}")

    _report(rows)


def _report(rows: list[dict]) -> None:
    if not rows:
        print("无结果")
        return
    # aggregate per system
    by_sys: dict[str, list[dict]] = {}
    for r in rows:
        by_sys.setdefault(r["system"], []).append(r)

    lines = ["# 评测结果", "", "## 各任务明细", "",
             "| 任务 | 系统 | 总Token | 耗时(s) | 来源数 | 压缩比 | 覆盖率 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['task']} | {r['system']} | {r['tokens']} | {r['wall']} | "
                     f"{r['sources']} | {r['compression']} | {r['coverage']} |")

    lines += ["", "## 系统平均", "",
              "| 系统 | 平均Token | 平均耗时(s) | 平均覆盖率 |",
              "| --- | --- | --- | --- |"]
    base_tok = None
    for name, rs in by_sys.items():
        avg_tok = round(statistics.mean(x["tokens"] for x in rs))
        avg_wall = round(statistics.mean(x["wall"] for x in rs), 1)
        covs = [x["coverage"] for x in rs if x["coverage"] >= 0]
        avg_cov = round(statistics.mean(covs), 3) if covs else "-"
        if name == "baseline_A":
            base_tok = avg_tok
        lines.append(f"| {name} | {avg_tok} | {avg_wall} | {avg_cov} |")

    if base_tok:
        lines += ["", "## 相对 Direct Chat 的 Token 变化", ""]
        for name, rs in by_sys.items():
            avg_tok = statistics.mean(x["tokens"] for x in rs)
            pct = round(100 * avg_tok / base_tok)
            lines.append(f"- {name}: {pct}% of Direct Chat")

    out = "\n".join(lines)
    (Path(__file__).parent / "results.md").write_text(out, encoding="utf-8")
    print("\n" + out)
    print("\n结果已写入 tests/results.md")


if __name__ == "__main__":
    main()
