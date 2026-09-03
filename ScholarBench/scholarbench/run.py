"""ScholarBench 主评测入口。

    python -m scholarbench.run --split lite --systems studio
    python -m scholarbench.run --split lite --systems studio,openai_compat:gpt-4o --no-judge
    python -m scholarbench.run --families T5 --systems studio          # 只跑引用核对
    python -m scholarbench.run --split lite --systems studio --adversarial water

接入外部 Agent（我们提供接口，对方实现 HTTP / CLI 即可）：

    python -m scholarbench.run --systems http:http://localhost:8000/api/bench/generate
    python -m scholarbench.run --systems cli:"python my_agent.py"

长跑续跑（中断后重跑同一条命令即可，已成功的自动跳过）：

    python -m scholarbench.run --split lite --systems studio --retry-failed
    python -m scholarbench.run --split lite --systems studio --timeout 300 --retries 3

流程：加载任务 → 各系统生成回答 → （可选）扰动 → 客观指标 + Rubric 打分 → 聚合 → 落盘
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

from . import rate_limit
from .adapters import get_adapter
from .dataset import (load_adversarial, load_keys, load_split, suite_path,
                      version_dir)
from .metrics import Judge, aggregate, compute_objective, rubric_to_100
from .metrics.aggregate import leaderboard_rows, task_score
from .schema import (Answer, EvalResult, FAMILY_WEIGHTS, Task, read_jsonl,
                     write_jsonl)


class _Progress:
    """终端实时进度。

    - TTY 终端（直接跑命令行）：评分阶段用 ``\\r`` 覆盖刷新单行，不刷屏；
    - 非 TTY（IDE 捕获 / 重定向到日志）：每次评分完成打印一行，进度不丢失。
    """

    def __init__(self, total: int, live: bool | None = None) -> None:
        self.total = total
        self.generated = 0
        self.failed = 0
        self.scored = 0
        self.scores: dict[str, list[float]] = {}
        self._tty = sys.stdout.isatty() if live is None else live

    def add_generated(self, ok: bool) -> None:
        self.generated += 1
        if not ok:
            self.failed += 1

    def add_scored(self, family: str, score: float) -> None:
        self.scored += 1
        self.scores.setdefault(family, []).append(score)
        line = self._line()
        if self._tty:
            sys.stdout.write("\r" + line)
            sys.stdout.flush()
        else:
            print(line, flush=True)

    def _bench(self) -> float:
        num = sum(FAMILY_WEIGHTS.get(f, 0.0) * (sum(v) / len(v))
                  for f, v in self.scores.items())
        den = sum(FAMILY_WEIGHTS.get(f, 0.0) for f in self.scores)
        return num / den if den else 0.0

    def _line(self) -> str:
        pct = self.scored / self.total * 100 if self.total else 0
        return (f"  评分中 {self.scored}/{self.total} ({pct:.0f}%) · "
                f"失败 {self.failed} · 实时 BenchScore {self._bench():.1f}")

    def finish(self) -> None:
        """结束实时行（换行收尾），防止污染后续输出。"""
        if self._tty and self.scored:
            sys.stdout.write("\n")
            sys.stdout.flush()


class _Heartbeat:
    """长单条任务等待期间的心跳提示。

    外部端点 / 慢速生成常达数十秒，若期间无任何输出会显得"卡死"。
    任务启动 2 秒后仍未完成，则每秒用 ``\\r`` 刷新一次"已等待时长"。
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._tty = sys.stdout.isatty()
        self._t0 = time.time()
        self._stop = threading.Event()
        self._shown = False

    def __enter__(self) -> "_Heartbeat":
        if self._tty:
            threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self) -> None:
        pad = 0
        while not self._stop.wait(0.5):
            elapsed = time.time() - self._t0
            if elapsed >= 2.0:
                self._shown = True
                msg = (f"  ↻ 等待中 {self._label} 已用时 {elapsed:.0f}s "
                       "（Ctrl+C 中断后重跑同命令可续）")
                pad = max(pad, len(msg) + 8)
                sys.stdout.write("\r" + msg)
                sys.stdout.flush()
        if self._shown:  # 清掉心跳残留，避免与下一行粘连
            sys.stdout.write("\r" + " " * pad + "\r")
            sys.stdout.flush()

    def __exit__(self, *exc) -> None:
        self._stop.set()
        return None


def _resolve_tasks(args) -> list[Task]:
    if args.split == "adversarial":
        tasks = load_adversarial()
        if not tasks:
            tasks = load_split("lite")
    elif args.families:
        tasks = []
        fams: list[str] = []
        for f in args.families:
            fams += [x.strip() for x in f.split(",") if x.strip()]
        for f in fams:
            p = suite_path(f)
            if p.exists():
                from .schema import load_tasks
                tasks += load_tasks(p)
    else:
        tasks = load_split(args.split)
    if args.tasks:
        wanted = set(args.tasks)
        tasks = [t for t in tasks if t.task_id in wanted]
    if args.limit:
        tasks = tasks[: args.limit]
    return tasks


def _load_cached(path: Path) -> dict[str, dict]:
    return {r["task_id"]: r for r in read_jsonl(path)} if path.exists() else {}


def _perturb(answer, kind: str):
    from .adversarial import perturb
    return perturb(answer, kind)


def _gen_with_retry(sut, task: Task, retries: int) -> Answer:
    """单条生成 + 失败重试。

    - 每个请求前都过全局限速器（请求间隔 / 429 冷却由 --rate-interval 统一控制）；
    - 429 进入全局指数冷却（15s 起、上限 120s），由限速器阻塞下一个请求；
    - 超时类 3s 起步退避、上限 30s；其余临时失败 1s 起步、上限 8s。
    """
    last: Answer | None = None
    n = max(1, retries)
    for attempt in range(n):
        rate_limit.wait_before_request()
        ans = sut.generate(task)
        if ans.ok:
            return ans
        last = ans
        if attempt < n - 1:
            err = str(ans.meta.get("error") or "")
            if rate_limit.is_rate_error(err):
                cool = rate_limit.on_429()
                print(f"      ↻ 429 冷却 {task.task_id}（第 {attempt + 2}/{n} 次 · "
                      f"约 {cool:.0f}s 后自动续） {err[:80]}", flush=True)
                # 不在此 sleep：下一个请求前的 wait_before_request 会等到冷却结束
            elif any(k in err for k in ("timeout", "timed out", "超时",
                                         "APITimeout", "ReadTimeout")):
                delay = min(3 * (2 ** attempt), 30)
                print(f"      ↻ 重试 {task.task_id}（第 {attempt + 2}/{n} 次 · "
                      f"请求超时，{delay:.0f}s 后） {err[:80]}", flush=True)
                time.sleep(delay)
            else:
                delay = min(2 ** attempt, 8)
                print(f"      ↻ 重试 {task.task_id}（第 {attempt + 2}/{n} 次 · "
                      f"临时失败，{delay:.0f}s 后） {err[:80]}", flush=True)
                time.sleep(delay)
    return last  # type: ignore[return-value]


def evaluate(args) -> None:
    # 全局请求节拍：--rate-interval 控制两次请求最小间隔；
    # 429 冷却全局共享（生成与打分同一节拍）。同步给 Studio 后端进程内限速。
    rate_limit.configure(args.rate_interval)
    if args.rate_interval > 0:
        os.environ["HY3_REQUEST_INTERVAL"] = str(args.rate_interval)

    tasks = _resolve_tasks(args)
    if not tasks:
        print("没有可评测的任务。请先运行：python -m scholarbench build_dataset")
        return

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = load_keys()
    judge = None if args.no_judge else Judge(
        model=args.judge_model or None,
        cache_dir=out_dir / ".judge_cache",
        verbose=args.verbose,
        chunked=args.chunked,          # [DeepResearchEval] 长文分块评测
    )

    print(f"任务 {len(tasks)} 条 | 系统 {args.systems} | "
          f"{'仅客观指标' if args.no_judge else '客观 + Rubric'}")

    all_results: list[EvalResult] = []
    for spec in args.systems.split(","):
        spec = spec.strip()
        if not spec:
            continue
        print(f"\n=== 系统 {spec} ===")
        sut = get_adapter(spec, timeout=args.timeout or None)
        cache_path = out_dir / f"answers_{spec.replace(':', '_').replace('/', '_')}.jsonl"
        cached = _load_cached(cache_path)
        answers_out: list[dict] = []
        results: list[EvalResult] = []
        prog = _Progress(len(tasks))

        # ---- 生成阶段：已成功的直接复用（续跑），失败的可选重跑 ----
        answers_by_id: dict[str, Answer] = {}
        cached_ids: set[str] = set()
        pending: list[tuple[int, Task]] = []
        n_failed_cached = 0
        for i, task in enumerate(tasks, 1):
            tid = task.task_id
            rec = cached.get(tid)
            if rec and not args.regen:
                prev = _answer_from_dict(rec)
                if prev.ok or not args.retry_failed:
                    answers_by_id[tid] = prev
                    cached_ids.add(tid)
                    if not prev.ok:
                        n_failed_cached += 1
                    continue
            pending.append((i, task))

        if cached_ids:
            print(f"  续跑：复用已完成的 {len(cached_ids)} 条"
                  + (f"（其中 {n_failed_cached} 条上次失败，加 --retry-failed 可重跑）"
                     if n_failed_cached else "")
                  + f" · 待生成 {len(pending)} 条")
        if args.timeout:
            print(f"  单次生成超时上限：{args.timeout:.0f}s · 失败重试 {args.retries} 次")

        tty = sys.stdout.isatty()
        if args.parallel > 1 and pending:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            print(f"  并发生成 {len(pending)} 条（workers={args.parallel}）", flush=True)

            def _gen(t: Task):
                a = _gen_with_retry(sut, t, args.retries)
                a.system = a.system or spec
                return t.task_id, a

            done_n = 0
            with ThreadPoolExecutor(max_workers=args.parallel) as ex:
                futs = {ex.submit(_gen, t): t.task_id for _, t in pending}
                for fut in as_completed(futs):
                    tid, a = fut.result()
                    done_n += 1
                    answers_by_id[tid] = a
                    wall = float(a.meta.get("wall") or 0)
                    mark = "" if a.ok else f" [失败] {a.meta.get('error')}"
                    print(f"  [{done_n}/{len(tasks)}] {tid} 完成 · "
                          f"{len(a.content)} 字 · {wall:.0f}s{mark}", flush=True)
                    prog.add_generated(a.ok)
        else:
            for i, task in pending:
                head = f"[{i}/{len(tasks)}] {task.task_id} ({task.family}/{task.difficulty})"
                if tty:                         # TTY：悬行 + 心跳，完成后 \r 覆盖为一行
                    print(f"  {head} …", end="", flush=True)
                else:                           # 非 TTY：开始/完成各打一行，日志可读
                    print(f"  {head} …", flush=True)
                with _Heartbeat(head):          # 长任务等待期间显示已用时心跳
                    ans = _gen_with_retry(sut, task, args.retries)
                ans.system = ans.system or spec
                answers_by_id[task.task_id] = ans
                wall = float(ans.meta.get("wall") or 0)
                mark = "" if ans.ok else f" [失败] {ans.meta.get('error')}"
                line = f"  {head} 完成 · {len(ans.content)} 字 · {wall:.0f}s{mark}"
                print(("\r" if tty else "") + line)
                prog.add_generated(ans.ok)

        if prog.generated:
            print(f"  生成完成 {prog.generated}/{len(tasks)}（失败 {prog.failed}）")

        # ---- 评分阶段：统一处理 ----
        for i, task in enumerate(tasks, 1):
            tid = task.task_id
            ans = answers_by_id[tid]
            key = keys.get(tid, {})
            if tid not in cached_ids:
                answers_out.append(ans.to_dict())
            if args.adversarial:
                ans = _perturb(ans, args.adversarial)
            metrics, obj_score, tags = compute_objective(task, ans, key)
            rscores = [] if judge is None else judge.score(task, ans, key)
            rub_score = rubric_to_100(rscores, task.family) if rscores else 0.0
            alpha = 1.0 if judge is None else task.alpha
            res = EvalResult(
                task_id=tid, family=task.family, difficulty=task.difficulty,
                system=ans.system or spec,
                objective=metrics, objective_score=obj_score,
                rubric=rscores, rubric_score=rub_score,
                task_score=task_score(obj_score, rub_score, alpha),
                errors=tags,
                meta={"wall": ans.meta.get("wall"), "error": ans.meta.get("error", "")},
            )
            results.append(res)
            all_results.append(res)
            prog.add_scored(res.family, res.task_score)

        if answers_out:
            # 覆盖式合并：本轮新生成的 task_id 替换缓存中的旧记录，避免重复累积
            fresh_ids = {a["task_id"] for a in answers_out}
            kept = [r for r in (read_jsonl(cache_path) if cache_path.exists() else [])
                    if r.get("task_id") not in fresh_ids]
            write_jsonl(cache_path, kept + answers_out)
        write_jsonl(out_dir / f"results_{spec.replace(':', '_').replace('/', '_')}.jsonl",
                    [r.to_dict() for r in results])
        sut.close()

        agg = aggregate(results)
        for system, d in agg.items():
            prog.finish()
            print(f"  BenchScore = {d['bench_score']}  "
                  f"(样本 {d['n_samples']}，失败 {d['n_failed']})")

    # --- 汇总 ---------------------------------------------------------------
    write_jsonl(out_dir / "results.jsonl", [r.to_dict() for r in all_results])
    agg_all = aggregate(all_results)
    (out_dir / "aggregate.json").write_text(
        json.dumps(agg_all, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("Leaderboard")
    print("=" * 60)
    for row in leaderboard_rows(agg_all):
        print(f"  {row['bench_score']:>6.2f}  {row['system']}  "
              f"(easy {row['easy']} / med {row['medium']} / hard {row['hard']})")
    print(f"\n结果已写入 {out_dir}")


def _answer_from_dict(d: dict):
    from .schema import Answer
    a = Answer.from_dict(d)
    return a


def main() -> None:
    # Windows 控制台默认 GBK，先统一 UTF-8，避免进度行含中文/符号时报错
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="ScholarBench 评测运行器")
    ap.add_argument("--split", default="lite",
                    choices=["lite", "full", "hard", "adversarial"])
    ap.add_argument("--systems", default="studio")
    ap.add_argument("--families", nargs="*", help="按任务族过滤，如 T1 T5")
    ap.add_argument("--tasks", nargs="*", help="按 task_id 过滤，如 T5-001")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="results")
    ap.add_argument("--no-judge", action="store_true", help="只算客观指标，零 API 成本")
    ap.add_argument("--judge-model", default="")
    ap.add_argument("--parallel", type=int, default=1,
                    help="并发生成 worker 数（1=串行。TokenHub 网关容量有限，遇 429 建议串行）")
    ap.add_argument("--rate-interval", type=float, default=0.0,
                    help="两次模型请求的最小间隔秒数（0=不限）。配合串行可显著降低 429，"
                         "如 --parallel 1 --rate-interval 2；429 会自动进入 15s→120s 指数冷却")
    ap.add_argument("--chunked", action="store_true",
                    help="[DeepResearchEval] 长文（T1/T2/T6）分块逐段评分，逻辑/可读性更精确")
    ap.add_argument("--adversarial", default="",
                    choices=["", "water", "term", "fake", "format", "inject", "conflict"])
    ap.add_argument("--regen", action="store_true", help="忽略已有回答缓存（全部重跑）")
    ap.add_argument("--retry-failed", action="store_true",
                    help="续跑增强：只重跑上次失败/超时的任务，已成功的仍跳过")
    ap.add_argument("--retries", type=int, default=2,
                    help="单条任务生成失败时的重试次数（指数退避，默认 2）")
    ap.add_argument("--timeout", type=float, default=0.0,
                    help="单次生成超时上限（秒），对 HTTP / CLI / 裸模型生效；0 = 用 adapter 默认")
    ap.add_argument("--no-thinking", action="store_true",
                    help="关闭 thinking（hy3/hy4/deepseek 提速约 5x；glm 等强制思考模型自动忽略）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.no_thinking:
        os.environ.setdefault("HY3_DISABLE_THINKING", "1")

    t0 = time.time()
    evaluate(args)
    print(f"\n总耗时 {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
