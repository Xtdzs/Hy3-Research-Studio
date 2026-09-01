"""批量跨模型评测（断点续跑）。

系统集：
  1. studio               —— Hy3 Research Studio 应用流水线（hy3）
  2. openai_compat:hy3    —— 裸 Hy3（与 studio 对比"应用 vs 裸模型"）
  3. openai_compat:hy4-preview
  4. openai_compat:glm-5.3-flash
  5. openai_compat:deepseek-v4-flash-0731

用法：python run_all_models.py [--families T3,T5,T6,T7,T8] [--judge]
已完成的系统（results/<name>/aggregate.json 存在）自动跳过。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent

SYSTEMS = [
    ("studio", "studio"),
    ("hy3", "openai_compat:hy3"),
    ("hy4-preview", "openai_compat:hy4-preview"),
    ("glm-5.3-flash", "openai_compat:glm-5.3-flash"),
    ("deepseek-v4-flash", "openai_compat:deepseek-v4-flash-0731"),
]


def done(name: str, out_root: Path) -> bool:
    agg = out_root / name / "aggregate.json"
    if not agg.exists():
        return False
    ans = out_root / name / f"answers_{name}.jsonl"
    if not ans.exists() or ans.stat().st_size == 0:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", default="T3,T5,T6,T7,T8")
    ap.add_argument("--judge", action="store_true", help="开启 Rubric judge（默认仅客观）")
    ap.add_argument("--systems", nargs="*", help="覆盖系统集，如 studio hy4-preview")
    args = ap.parse_args()

    systems = SYSTEMS
    if args.systems:
        systems = []
        for s in args.systems:
            if s == "studio" or ":" in s:      # 已有完整 spec
                spec = s
            else:
                spec = f"openai_compat:{s}"
            systems.append((s.split(":")[-1], spec))

    out_root = ROOT / "results"
    out_root.mkdir(exist_ok=True)
    print(f"任务族: {args.families} | judge: {args.judge} | 系统: {len(systems)}")

    for name, spec in systems:
        if done(name, out_root):
            print(f"[skip] {name}（已有结果）")
            continue
        print(f"\n========== {name} ({spec}) ==========")
        cmd = [sys.executable, "-m", "scholarbench.run",
               "--families", args.families, "--systems", spec,
               "--out", str(out_root / name)]
        if not args.judge:
            cmd.append("--no-judge")
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT)
        print(f"  [{name}] 完成，耗时 {time.time() - t0:.0f}s, rc={r.returncode}")

    print("\n全部完成。汇总：python -m scholarbench report_leaderboard --auto --root results")


if __name__ == "__main__":
    main()
