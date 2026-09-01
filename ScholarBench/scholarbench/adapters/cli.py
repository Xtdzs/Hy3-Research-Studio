"""CLI adapter —— 测任意命令行程序。

协议：task 以 JSON 走 stdin，程序需向 stdout 打印 answer JSON。
    {"task_id": ..., "content": ..., "citations": [...], "tool_calls": [...], "meta": {...}}

用法：cli:python my_agent.py
"""
from __future__ import annotations

import json
import subprocess

from ..schema import Answer, Citation, Task
from .base import SUT


class CLIAdapter(SUT):
    name = "cli"

    def __init__(self, command: str = "", timeout: float = 600.0, **kwargs) -> None:
        super().__init__(**kwargs)
        if not command:
            raise ValueError("cli adapter 需要命令：cli:python my_agent.py")
        self.command = command
        self.timeout = timeout

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
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            cites = [Citation(**c) for c in data.get("citations", []) if isinstance(c, dict)]
            return Answer(task_id=task.task_id, system=self.name,
                          content=data.get("content", ""), citations=cites,
                          tool_calls=data.get("tool_calls", []) or [],
                          meta=data.get("meta", {}) or {})
        return self.timed(_run, task)
