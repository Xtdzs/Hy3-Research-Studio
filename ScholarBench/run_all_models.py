"""批量跨基座模型评测（同一套 Studio Agent 流水线，替换底层模型）。

--mode agent（默认）：每基座跑完整 studio 流水线 → 评估不同基座在系统中的效果
--mode bare：裸模型直接生成（对照）
用法：
    python run_all_models.py                      # agent，4 基座
    python run_all_models.py --limit 15           # 少量快速验证
    python run_all_models.py --mode bare --systems hy3 hy4-preview
断点续跑：results/<name>/aggregate.json 存在即跳过。
进度展示：终端实时显示生成/评分/失败/实时 BenchScore，且每完成一个系统
打印一次已收集到的跨模型排行榜。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent

AGENT_BASE = [
    ("studio_hy3", "hy3"),
    ("studio_glm", "glm-5.3-flash"),
    ("studio_ds", "deepseek-v4-flash-0731"),
]
BARE_SYSTEMS = [
    ("hy3", "openai_compat:hy3"),
    ("hy4-preview", "openai_compat:hy4-preview"),
    ("glm-5.3-flash", "openai_compat:glm-5.3-flash"),
    ("deepseek-v4-flash", "openai_compat:deepseek-v4-flash-0731"),
]


def _studio_env(model: str) -> dict:
    env = dict(os.environ)
    env["HY3_MODEL"] = model
    # 评测检索源：仅 arXiv（其他源限流不稳定，评测期固定单源保证可控）
    env["DEFAULT_SOURCES"] = "arxiv"
    # 评测超时：25s 未响应即失败并继续，避免单个挂起阻塞整批
    env["HY3_TIMEOUT"] = "25"
    env_file = ROOT.parent / "Hy3-Research-Studio" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("HY3_API_KEY="):
                env["HY3_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("HY3_BASE_URL="):
                env["HY3_BASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return env


def done(name: str, out_root: Path) -> bool:
    """系统是否已完成：aggregate.json 存在且含有效样本数。
    注意答案缓存文件名为 answers_<spec>.jsonl（spec 为 studio 等），
    不能按目录名猜测，故直接校验 aggregate 内容。
    """
    agg = out_root / name / "aggregate.json"
    if not agg.exists():
        return False
    try:
        data = json.loads(agg.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not data:
        return False
    first = data[name] if name in data else next(iter(data.values()), {})
    return int(first.get("n_samples", 0) or 0) > 0


def live_leaderboard(out_root: Path) -> None:
    """打印当前已收集到的跨模型排行榜（每次系统完成后刷新）。"""
    rows = []
    for d in sorted(out_root.iterdir()):
        p = d / "aggregate.json"
        if not d.is_dir() or not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.name in data:
            score = float(data[d.name].get("bench_score", 0.0) or 0.0)
        elif data:
            score = float(next(iter(data.values())).get("bench_score", 0.0) or 0.0)
        else:
            continue
        rows.append((d.name, score))
    if not rows:
        return
    rows.sort(key=lambda x: -x[1])
    print("  [当前排行榜] " + "  |  ".join(
        f"{n} {s:.1f}" for n, s in rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="agent", choices=["agent", "bare"])
    ap.add_argument("--families", default="T3,T5,T6,T7,T8")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tasks", nargs="*", help="指定 task_id（如 --tasks T5-001 T5-009 T5-021）")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--regen", action="store_true", help="忽略已有结果强制重跑")
    ap.add_argument("--parallel", type=int, default=3, help="并发生成 worker 数")
    ap.add_argument("--systems", nargs="*")
    ap.add_argument("--out-root", default="results",
                    help="结果输出根目录。快速评测建议用独立目录（如 --out-root results_lite），"
                         "避免 --limit/--tasks 覆盖正式结果")
    args = ap.parse_args()

    if args.mode == "agent":
        systems = [(f"studio_{s}", s) for s in args.systems] if args.systems else AGENT_BASE
    else:
        systems = [(s.split(":")[-1], f"openai_compat:{s}") for s in args.systems] \
            if args.systems else BARE_SYSTEMS

    out_root = ROOT / args.out_root
    out_root.mkdir(exist_ok=True)
    print(f"模式: {args.mode} | 族: {args.families} | limit: {args.limit or 'all'} | "
          f"系统: {len(systems)} | 输出: {args.out_root}")
    live_leaderboard(out_root)

    for name, model in systems:
        if done(name, out_root) and not args.regen:
            print(f"[skip] {name}（已有结果）")
            continue
        print(f"\n========== {name} (基座: {model}) ==========")
        spec = model if args.mode == "bare" else "studio"
        cmd = [sys.executable, "-m", "scholarbench.run",
               "--families", args.families, "--systems", spec,
               "--out", str(out_root / name)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.tasks:
            cmd += ["--tasks", *args.tasks]
        if args.regen:
            cmd.append("--regen")          # 透传：忽略底层 run.py 的答案缓存
        cmd += ["--parallel", str(args.parallel)]
        if not args.judge:
            cmd.append("--no-judge")
        env = _studio_env(model) if args.mode == "agent" else None
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT, env=env)
        print(f"  [{name}] 完成 {time.time() - t0:.0f}s, rc={r.returncode}")
        live_leaderboard(out_root)

    print("\n全部完成。汇总：python -m scholarbench report_leaderboard --auto --root results")


if __name__ == "__main__":
    main()
