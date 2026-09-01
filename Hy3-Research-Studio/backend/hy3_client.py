"""Thin wrapper around the Hy3 OpenAI-compatible Chat Completions API.

Responsibilities:
- centralise the client construction
- expose sync `chat` and `chat_json` helpers
- accumulate token usage so the pipeline can report cost metrics
- provide robust JSON extraction (models sometimes wrap JSON in prose / ```json)
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from .config import settings


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, prompt: int, completion: int) -> None:
        with self._lock:
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.total_tokens += prompt + completion
            self.calls += 1

    def snapshot(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
        }


class Hy3Client:
    def __init__(self) -> None:
        if not settings.is_configured:
            raise RuntimeError(
                "HY3_API_KEY 未配置。请在 .env 或环境变量中设置 HY3_API_KEY。"
            )
        self._client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.request_timeout,
        )
        self.usage = TokenUsage()

    # -- core -----------------------------------------------------------------
    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> str:
        resp = self._client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if resp.usage:
            self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return (resp.choices[0].message.content or "").strip()

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ):
        """Yield content deltas. Token usage is estimated when not provided."""
        stream = self._client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        collected = 0
        for chunk in stream:
            if chunk.usage:
                self.usage.add(
                    chunk.usage.prompt_tokens, chunk.usage.completion_tokens
                )
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                collected += 1
                yield delta.content

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> Any:
        """Call the model and parse the response as JSON, tolerating wrappers."""
        content = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        return _extract_json(content)

    def chat_message(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        force_tool_name: str | None = None,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ):
        """非流式调用，返回原始 ``Message`` 对象（可能携带 ``tool_calls``）。

        用于 agent 的工具调用：``force_tool_name`` 非空时强制模型先调用该工具
        （保证『先检索、再回答』）；为 ``None`` 时 ``tool_choice="auto"`` 由模型自主决定。
        """
        kwargs: dict = {
            "model": settings.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
            if force_tool_name:
                kwargs["tool_choice"] = {"type": "function", "function": {"name": force_tool_name}}
            else:
                kwargs["tool_choice"] = "auto"
        resp = self._client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        if resp.usage:
            self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return msg


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        raise ValueError("模型返回空内容")

    # 1) direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) fenced ```json ... ```
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3) first { ... } or [ ... ] balanced block
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"无法从模型输出解析 JSON: {text[:200]}")
