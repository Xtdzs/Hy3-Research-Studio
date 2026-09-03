"""批量跨系统评测：不同基座 / 不同 Agent 放在同一套题上横向对比。

三种模式：
    --mode agent  （默认）同一套 Studio Agent 流水线，只替换底层基座
    --mode bare   裸模型直接生成（无检索、无工具，作为对照下界）
    --mode custom 接任意外部 Agent（HTTP / CLI / OpenAI 兼容端点），跨团队、跨语言

用法：
    python run_all_models.py                          # agent，3 基座
    python run_all_models.py --limit 15               # 少量快速验证
    python run_all_models.py --mode bare --systems hy3 hy4-preview
    python run_all_models.py --mode custom \
        --systems http:http://localhost:8000/api/bench/generate cli:"python my_agent.py"

稳定性与长跑：
    --timeout 300        单次生成超时上限（默认 300s，长任务可调到 600）
    --retries 3          单条失败自动重试（指数退避）
    --no-thinking        关闭思考链（hy3/hy4/deepseek 提速约 5x；glm 等强制思考自动忽略）
    --rate-interval 2    两次模型请求最小间隔秒数（配合默认串行大幅降低 429）
    --retry-failed       续跑增强：只重跑上次失败/超时的题，已成功的跳过

断点续跑：中断后重跑同一条命令即可；每个系统的答案缓存按 task_id 复用，
每完成一个系统打印一次已收集到的跨模型排行榜。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent

# 多基座对照名单。注：hy3 是 Hy3 应用流水线的默认基座，
# 其正式结果即 Leaderboard 中的 `studio` 行，此处不再重复对照。
AGENT_BASE = [
    ("studio_hy4", "hy4-preview"),
    ("studio_glm", "glm-5.3-flash"),
    ("studio_ds", "deepseek-v4-flash-0731"),
]
BARE_SYSTEMS = [
    ("hy3", "openai_compat:hy3"),
    ("hy4-preview", "openai_compat:hy4-preview"),
    ("glm-5.3-flash", "openai_compat:glm-5.3-flash"),
    ("deepseek-v4-flash", "openai_compat:deepseek-v4-flash-0731"),
]


def _safe_name(spec: str) -> str:
    """把任意 spec 转成可做目录名的标识（http://host:8000/x → http_host_8000_x）。"""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", spec).strip("_")[:60] or "system"


def _studio_env(model: str = "", timeout: float = 0.0,
                no_thinking: bool = False, rate_interval: float = 0.0) -> dict:
    env = dict(os.environ)
    if model:
        env["HY3_MODEL"] = model
    if no_thinking:
        env["HY3_DISABLE_THINKING"] = "1"
    if rate_interval > 0:
        env["HY3_REQUEST_INTERVAL"] = str(rate_interval)
    # 评测检索源：Crossref + arXiv 双源。曾强制 arxiv-only，但实测 arXiv 对
    # 多道 T3 题返回 0 命中（如 "retrieval augmented generation survey"），
    # Crossref 稳定命中——单源会大面积空结果，故改回双源互补。
    env["DEFAULT_SOURCES"] = "crossref,arxiv"
    # 超时：默认 300s（thinking 模型推理慢，单请求可达 1-3 分钟；429 另有长退避）
    if timeout:
        env["HY3_TIMEOUT"] = str(timeout)
        env["SB_AGENT_TIMEOUT"] = str(timeout)
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
    ap.add_argument("--mode", default="agent", choices=["agent", "bare", "custom"])
    ap.add_argument("--families", default="T3,T5,T6,T7,T8")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--tasks", nargs="*", help="指定 task_id（如 --tasks T5-001 T5-009 T5-021）")
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--regen", action="store_true", help="忽略已有结果强制重跑")
    ap.add_argument("--parallel", type=int, default=1,
                    help="并发生成 worker 数（1=串行，推荐；TokenHub 网关容量有限，"
                         "并行 >3 极易触发 429）")
    ap.add_argument("--rate-interval", type=float, default=0.0,
                    help="两次模型请求的最小间隔秒数（0=不限）。串行 + 小间隔最稳，"
                         "如 --parallel 1 --rate-interval 2；429 会自动进入指数冷却")
    ap.add_argument("--systems", nargs="*")
    ap.add_argument("--timeout", type=float, default=300.0,
                    help="单次生成超时上限（秒，默认 300）。thinking 模型/外部端点慢就调大，"
                         "如 --timeout 600")
    ap.add_argument("--retries", type=int, default=2,
                    help="单条任务生成失败的重试次数（指数退避，默认 2）")
    ap.add_argument("--retry-failed", action="store_true",
                    help="续跑增强：只重跑上次失败/超时的题，已成功的复用缓存")
    ap.add_argument("--no-thinking", action="store_true",
                    help="关闭思考链（hy3/hy4/deepseek 提速约 5x、省 token；"
                         "glm 等始终思考的模型会自动忽略该设置）")
    ap.add_argument("--out-root", default="results",
                    help="结果输出根目录。快速评测建议用独立目录（如 --out-root results_lite），"
                         "避免 --limit/--tasks 覆盖正式结果")
    args = ap.parse_args()

    if args.mode == "agent":
        systems = [(f"studio_{s}", s) for s in args.systems] if args.systems else AGENT_BASE
    elif args.mode == "custom":
        if not args.systems:
            ap.error("--mode custom 需要 --systems，如 "
                     "'http:http://localhost:8000/api/bench/generate' 或 'cli:python my_agent.py'")
        systems = [(_safe_name(s), s) for s in args.systems]
    else:
        systems = [(s.split(":")[-1], f"openai_compat:{s}") for s in args.systems] \
            if args.systems else BARE_SYSTEMS

    out_root = ROOT / args.out_root
    out_root.mkdir(exist_ok=True)
    print(f"模式: {args.mode} | 族: {args.families} | limit: {args.limit or 'all'} | "
          f"系统: {len(systems)} | 超时: {args.timeout:.0f}s | 输出: {args.out_root}")
    live_leaderboard(out_root)

    for name, model in systems:
        if done(name, out_root) and not args.regen:
            print(f"[skip] {name}（已有结果，加 --regen 强制重跑）")
            continue
        label = "基座" if args.mode == "agent" else "系统"
        print(f"\n========== {name} ({label}: {model}) ==========")
        spec = model if args.mode in ("bare", "custom") else "studio"
        cmd = [sys.executable, "-m", "scholarbench.run",
               "--families", args.families, "--systems", spec,
               "--out", str(out_root / name),
               "--timeout", str(args.timeout),
               "--retries", str(args.retries)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        if args.tasks:
            cmd += ["--tasks", *args.tasks]
        if args.regen:
            cmd.append("--regen")          # 透传：忽略底层 run.py 的答案缓存
        if args.retry_failed:
            cmd.append("--retry-failed")   # 透传：只补跑上次失败的题
        cmd += ["--parallel", str(args.parallel)]
        if args.rate_interval > 0:
            cmd += ["--rate-interval", str(args.rate_interval)]  # 透传：全局限速
        if args.no_thinking:
            cmd.append("--no-thinking")       # 透传：关闭思考链
        if not args.judge:
            cmd.append("--no-judge")
        if args.mode in ("agent", "custom"):
            env = _studio_env(model if args.mode == "agent" else "",
                              args.timeout, args.no_thinking, args.rate_interval)
        elif args.no_thinking or args.rate_interval > 0:
            env = dict(os.environ)
            if args.no_thinking:
                env["HY3_DISABLE_THINKING"] = "1"
            if args.rate_interval > 0:
                env["HY3_REQUEST_INTERVAL"] = str(args.rate_interval)
        else:
            env = None
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT, env=env)
        print(f"  [{name}] 完成 {time.time() - t0:.0f}s, rc={r.returncode}")
        live_leaderboard(out_root)

    print(f"\n全部完成。汇总：python -m scholarbench report_leaderboard "
          f"--auto --root {args.out_root}")


if __name__ == "__main__":
    main()
