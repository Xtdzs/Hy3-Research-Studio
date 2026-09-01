"""Adapter 注册表。

spec 语法：
    studio                      Hy3 Research Studio（内部调用）
    studio:/abs/path/to/studio  指定 Studio 根目录
    openai_compat:model_name    任意 OpenAI 兼容端点（读 .env 的 HY3_* 变量）
    http:http://host/eval       POST {"task": ...} -> {"content": ...}
    cli:python my_bot.py        调用命令行，task 走 stdin JSON，answer 走 stdout JSON
    human                       人工作答（人类基线上界锚点）
"""
from __future__ import annotations

from .base import SUT


def get_adapter(spec: str) -> SUT:
    kind, _, arg = spec.partition(":")
    kind = kind.strip()
    arg = arg.strip()

    if kind == "studio":
        from .studio import StudioAdapter
        return StudioAdapter(root=arg or None)
    if kind == "openai_compat":
        from .openai_compat import OpenAICompatAdapter
        return OpenAICompatAdapter(model=arg or None)
    if kind == "http":
        from .http import HTTPAdapter
        return HTTPAdapter(endpoint=arg)
    if kind == "cli":
        from .cli import CLIAdapter
        return CLIAdapter(command=arg)
    if kind == "human":
        from .human import HumanAdapter
        return HumanAdapter(annotator=arg or "human")
    if kind == "mock":
        from .mock import MockAdapter
        return MockAdapter(fail=arg)

    raise ValueError(
        f"未知 adapter: {kind}"
        "（可选：studio / openai_compat / http / cli / human / mock）"
    )


__all__ = ["get_adapter", "SUT"]
