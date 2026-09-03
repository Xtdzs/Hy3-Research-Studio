"""OpenAI 兼容端点 adapter —— 测任意模型（裸模型基线 / 跨系统对照）。

用法：openai_compat:gpt-4o | openai_compat（读 .env 的 HY3_*）
环境变量：HY3_API_KEY / HY3_BASE_URL / HY3_MODEL
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..env import load_dotenv
from ..schema import Answer, Task
from .base import SUT, parse_reference_block

# 各任务族的最小系统提示：保证裸模型"看得懂任务"，但不提供额外能力
def _extract_verdict(content: str) -> str:
    """从 T5 输出中提取三分类 verdict（兼容 JSON 或裸词前缀）。"""
    if not content:
        return ""
    m = re.search(r"[\"'](?:verdict|result)[\"']\s*:\s*[\"'](\w+)[\"']", content)
    if m:
        v = m.group(1).strip().lower()
        return v if v in ("supported", "unrelated", "nonexistent") else ""
    head = content.strip().lower()
    for v in ("supported", "unrelated", "nonexistent"):
        if head.startswith(v):
            return v
    return ""


FAMILY_SYSTEM = {
    "T1": "你是学术研究助手。请就给定主题撰写结构完整的中文文献综述，关键结论用 [sN] 标注引用，并在文末给出参考文献列表。",
    "T2": "你是学术研究助手。请就给定主题撰写研究开题方案，包含研究假设（可证伪）、实验设计（数据集/指标/基线/预期结果）。",
    "T3": "你是学术检索助手。请输出与主题最相关的文献列表，每行一条：序号. 标题 (年份)。只输出列表。",
    "T4": "你是论文阅读助手。只依据给定论文全文作答，给出结论并引用原文依据。",
    "T5": "你是学术引用核查员。只输出 JSON：{\"verdict\": \"supported\"|\"unrelated\"|\"nonexistent\", \"reason\": \"≤40字\"}。",
    "T6": "你是学术写作助手。按任务要求完成写作，不引入无依据的事实。",
    "T7": "你是研究教练。基于你的知识回答，关键结论标注 [sN] 引用并给出参考文献。",
    "T8": "你是研究助手。按步骤完成任务并给出整合后的结构化结论，关键处标注 [sN] 引用。",
}


def _load_env() -> None:
    """加载 .env（搜索顺序见 scholarbench/env.py）。"""
    load_dotenv()


class OpenAICompatAdapter(SUT):
    name = "openai_compat"

    def __init__(self, model: str | None = None, timeout: float | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        _load_env()
        from openai import OpenAI  # noqa: PLC0415
        self.model = model or os.getenv("HY3_MODEL", "hy3")
        # 优先级：显式参数 > 环境变量 HY3_TIMEOUT > 默认 300s
        #（thinking 模型推理慢，120s 常不够；429 由 SDK 重试 + run.py 外层退避兜底）
        self.timeout = float(timeout or os.getenv("HY3_TIMEOUT") or 300.0)
        self.client = OpenAI(
            api_key=os.getenv("HY3_API_KEY", ""),
            base_url=os.getenv("HY3_BASE_URL", "https://tokenhub.tencentmaas.com/v1"),
            timeout=self.timeout,
        )
        # HY3_DISABLE_THINKING=1 时关闭思考链（hy3/hy4/deepseek 提速约 5x）。
        # glm 等"始终思考"模型发送该参数会 400，已在 generate 内自动降级。
        self.disable_thinking = os.getenv("HY3_DISABLE_THINKING", "0").lower() \
            in ("1", "true", "yes", "on")
        self.tokens = 0

    def generate(self, task: Task) -> Answer:
        def _run() -> Answer:
            messages = [{"role": "system",
                         "content": FAMILY_SYSTEM.get(task.family, "你是学术研究助手。")}]
            if task.family == "T4":
                text = task.context.get("paper_text", "")
                if not text:
                    p = Path(task.context.get("pdf_path", ""))
                    if p.exists():
                        try:
                            from pypdf import PdfReader  # noqa: PLC0415
                            text = "\n".join((pg.extract_text() or "")
                                             for pg in PdfReader(str(p)).pages)
                        except Exception:  # noqa: BLE001
                            text = ""
                messages[0]["content"] += "\n只依据论文全文作答。"
                messages.append({"role": "user",
                                 "content": f"论文全文：\n{text[:60000]}\n\n问题：{task.prompt}"})
            else:
                messages.append({"role": "user", "content": task.prompt})

            kw: dict = {
                "model": self.model,
                "messages": messages,
                "temperature": 0.0 if task.family == "T5" else 0.4,
            }
            if self.disable_thinking:
                kw["extra_body"] = {"thinking": {"type": "disabled"}}
            while True:
                try:
                    resp = self.client.chat.completions.create(**kw)
                    break
                except Exception as exc:  # noqa: BLE001
                    if kw.get("extra_body") and any(
                        k in str(exc) for k in ("始终思考", "不支持关闭")
                    ):
                        kw.pop("extra_body", None)  # glm 等强制思考模型：降级
                        continue
                    raise
            if resp.usage:
                self.tokens += resp.usage.total_tokens
            content = (resp.choices[0].message.content or "").strip()
            cites = parse_reference_block(content)
            meta: dict = {"tokens": self.tokens, "model": self.model}
            if task.family == "T5":
                verdict = _extract_verdict(content)
                if verdict:
                    meta["verdict"] = verdict
            return Answer(task_id=task.task_id,
                          system=f"{self.name}:{self.model}",
                          content=content, citations=cites, meta=meta)
        return self.timed(_run, task)

    def close(self) -> None:
        self.client = None
