"""外部 Agent 接入示例 —— 命令行版（不限语言：Node / Go / Rust / Shell 皆可）。

评测：

    python -m scholarbench.run --systems "cli:python examples/agent_cli_stub.py" --split lite

协议：

    stdin : 一行 Task JSON
    stdout: 任意日志（会被忽略）+ **最后一行** Answer JSON

只要你的程序能满足"读一行 JSON、打印一行 JSON"，就能接入，无需任何 SDK。
"""
from __future__ import annotations

import json
import sys
from typing import Any


def dispatch(task: dict[str, Any]) -> dict[str, Any]:
    """把题目分派给你的 Agent。**请替换成你自己的实现**。"""
    family = task.get("family", "")
    prompt = task.get("prompt", "")

    if family == "T3":
        return {"content": "1. Attention Is All You Need (2017)\n2. BERT (2019)"}
    if family == "T5":
        return {"content": '{"verdict": "supported", "reason": "摘要直接支撑该论断"}'}
    return {"content": f"（你的 Agent 输出）针对：{prompt}"}


def main() -> None:
    raw = sys.stdin.read().strip()
    task = json.loads(raw)
    out = dispatch(task)
    out.setdefault("content", "")
    out.setdefault("citations", [])
    out.setdefault("tool_calls", [])
    out.setdefault("meta", {})
    out["meta"]["agent"] = "my-cli-agent/1.0"
    # 关键：Answer JSON 必须是最后一行
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
