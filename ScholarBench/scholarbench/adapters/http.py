"""HTTP adapter —— 测任意已部署的 Web 应用（含别的团队的系统）。

协议：
    POST <endpoint>
    body : {"task": <Task dict>}
    resp : {"content": str, "citations": [{"marker","title","doi","year","url"}],
            "tool_calls": [...], "meta": {...}}

用法：http:http://localhost:8000/api/bench/generate
"""
from __future__ import annotations

import json

from ..schema import Answer, Citation, Task
from .base import SUT


class HTTPAdapter(SUT):
    name = "http"

    def __init__(self, endpoint: str = "", timeout: float = 300.0, **kwargs) -> None:
        super().__init__(**kwargs)
        if not endpoint:
            raise ValueError("http adapter 需要 endpoint：http:http://host/path")
        self.endpoint = endpoint
        self.timeout = timeout

    def generate(self, task: Task) -> Answer:
        def _run() -> Answer:
            import urllib.request  # noqa: PLC0415
            payload = json.dumps({"task": task.to_dict()}, ensure_ascii=False).encode()
            req = urllib.request.Request(
                self.endpoint, data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            cites = [Citation(**c) for c in data.get("citations", []) if isinstance(c, dict)]
            return Answer(task_id=task.task_id, system=self.name,
                          content=data.get("content", ""), citations=cites,
                          tool_calls=data.get("tool_calls", []) or [],
                          meta=data.get("meta", {}) or {})
        return self.timed(_run, task)
