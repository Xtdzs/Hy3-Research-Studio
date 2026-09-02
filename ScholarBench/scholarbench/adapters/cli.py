"""CLI adapter —— 接任意命令行 Agent（不限语言，只要能读 stdin / 写 stdout）。

我们提供的接入契约：

    stdin : 一行 Task JSON   {"task_id":"T5-001","family":"T5","prompt":"...","context":{...}}
    stdout: 最后一行 Answer JSON
            {"content": "...", "citations":[{...}], "tool_calls":[{...}], "meta":{...}}

只有 **最后一行** 会被解析为 JSON，前面的日志/进度输出会被忽略，
因此你的程序可以照常往 stdout 打日志。非零退出码记为失败（可 --retry-failed 重跑）。

配置（环境变量）：
    SB_AGENT_TIMEOUT   单次调用超时（秒），默认 600

用法：
    cli:python my_agent.py
    cli:"node agent.js --bench"
"""
from __future__ import annotations

import json
import os
import subprocess

from ..schema import Answer, Citation, Task
from .base import SUT


class CLIAdapter(SUT):
    name = "cli"

    def __init__(self, command: str = "", timeout: float | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if not command:
            raise ValueError("cli adapter 需要命令：cli:python my_agent.py")
        self.command = command
        # 优先级：显式参数 > 环境变量 > 默认值
        self.timeout = float(timeout or os.getenv("SB_AGENT_TIMEOUT") or 600.0)

    def generate(self, task: Task) -> Answer:
        def _run() -> Answer:
            proc = subprocess.run(
                self.command, shell=True,
                input=json.dumps(task.to_dict(), ensure_ascii=False),
                capture_output=True, text=True, timeout=self.timeout,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                return Answer(task_id=task.task_id, system=self.name, content="",
                              meta={"error": f"exit={proc.returncode}: {proc.stderr[:300]}"})
            lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            if not lines:
                return Answer(task_id=task.task_id, system=self.name, content="",
                              meta={"error": "stdout 为空：未输出 Answer JSON"})
            try:
                data = json.loads(lines[-1])
            except json.JSONDecodeError as exc:
                return Answer(task_id=task.task_id, system=self.name, content="",
                              meta={"error": f"末行不是合法 JSON: {exc}; 原文: {lines[-1][:120]}"})
            cites = [Citation(**c) for c in data.get("citations", []) if isinstance(c, dict)]
            return Answer(task_id=task.task_id, system=self.name,
                          content=data.get("content", ""), citations=cites,
                          tool_calls=data.get("tool_calls", []) or [],
                          meta=data.get("meta", {}) or {})
        return self.timed(_run, task)
