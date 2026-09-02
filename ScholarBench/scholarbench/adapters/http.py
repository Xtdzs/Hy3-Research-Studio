"""HTTP adapter —— 接任意外部 Agent / 已部署系统（跨团队、跨语言、跨机器）。

我们提供的接入契约（你只要实现这一个端点就能被评测）：

    POST <endpoint>
    Headers: Content-Type: application/json
             Authorization: Bearer <token>      （可选，配了 SB_AGENT_TOKEN 才发）
    Body : {"task": <Task dict>}
    Resp : {"content": str,                      必填，正文（Markdown 亦可）
            "citations": [{"marker","title","doi","year","url","source"}],  可选
            "tool_calls": [{"name","args","result"}],                      可选
            "meta": {...}}                                                  可选

评分时按 task.family 走对应客观指标：T3 看召回、T5 看三分类、T6 看 ROUGE-L、
T7/T8 看关键点与工具链。返回空 content 或超时即判失败（可 --retry-failed 重跑）。

配置（环境变量）：
    SB_AGENT_TOKEN     Bearer token，用于给对方端点鉴权
    SB_AGENT_TIMEOUT   单次请求超时（秒），默认 300
    SB_AGENT_HEADERS   额外请求头，JSON 字符串，如 '{"X-Team":"foo"}'

用法：
    http:http://localhost:8000/api/bench/generate
"""
from __future__ import annotations

import json
import os

from ..schema import Answer, Citation, Task
from .base import SUT

DEFAULT_TIMEOUT = float(os.getenv("SB_AGENT_TIMEOUT", "300"))


def _extra_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    raw = os.getenv("SB_AGENT_HEADERS", "")
    if raw:
        try:
            headers.update({str(k): str(v)
                            for k, v in json.loads(raw).items() if k})
        except Exception:  # noqa: BLE001
            pass
    token = os.getenv("SB_AGENT_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class HTTPAdapter(SUT):
    name = "http"

    def __init__(self, endpoint: str = "", timeout: float | None = None,
                 token: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        if not endpoint:
            raise ValueError("http adapter 需要 endpoint：http:http://host/path")
        self.endpoint = endpoint
        # 优先级：显式参数 > 环境变量 > 默认值
        self.timeout = float(timeout or os.getenv("SB_AGENT_TIMEOUT") or DEFAULT_TIMEOUT)
        self.token = token or os.getenv("SB_AGENT_TOKEN", "")

    def generate(self, task: Task) -> Answer:
        def _run() -> Answer:
            import urllib.error  # noqa: PLC0415
            import urllib.request  # noqa: PLC0415

            payload = json.dumps({"task": task.to_dict()}, ensure_ascii=False).encode()
            headers = {"Content-Type": "application/json; charset=utf-8"}
            headers.update(_extra_headers())
            if self.token and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {self.token}"
            req = urllib.request.Request(self.endpoint, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:  # 保留服务端返回的错误正文
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")[:200]
                except Exception:  # noqa: BLE001
                    body = ""
                raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
            if not isinstance(data, dict):
                raise RuntimeError(f"响应不是 JSON 对象：{str(data)[:120]}")
            cites = [Citation(**c) for c in data.get("citations", []) if isinstance(c, dict)]
            meta = data.get("meta", {}) or {}
            if data.get("error"):
                meta["error"] = str(data["error"])[:200]
            return Answer(task_id=task.task_id, system=self.name,
                          content=data.get("content", ""), citations=cites,
                          tool_calls=data.get("tool_calls", []) or [],
                          meta=meta)
        return self.timed(_run, task)
