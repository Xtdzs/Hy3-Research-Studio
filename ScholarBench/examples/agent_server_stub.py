"""外部 Agent 接入示例 —— 把你的 Agent 暴露成一个 HTTP 端点即可被评测。

启动：

    pip install fastapi uvicorn
    uvicorn examples.agent_server_stub:app --port 8000

评测（另一终端）：

    python -m scholarbench.run \\
        --systems http:http://localhost:8000/api/bench/generate \\
        --split lite --timeout 300

协议（跨语言通用，用任何框架/语言实现都可以）：

    POST /api/bench/generate
    Headers: Content-Type: application/json
    Body : {"task": {"task_id","family","prompt","context", ...}}
    Resp : {"content": "...",                 # 必填：正文（Markdown 亦可）
            "citations": [{"marker","title","doi","year","url","source"}],  # 可选
            "tool_calls": [{"name","args","result"}],                        # 可选
            "meta": {...}}                                                   # 可选

评分口径：按 task.family 走对应客观指标 —— T3 看检索召回、T5 看三分类准确率、
T6 看 ROUGE-L、T7/T8 看关键点覆盖与工具链完整度。空 content 或超时判失败。
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="My Agent · ScholarBench Endpoint")


class GenerateRequest(BaseModel):
    task: dict[str, Any] = Field(default_factory=dict)


def _dispatch(task: dict[str, Any]) -> dict[str, Any]:
    """把题目分派给你的 Agent。这里只是占位逻辑，**请替换成你自己的实现**。"""
    family = task.get("family", "")
    prompt = task.get("prompt", "")

    if family == "T3":
        # TODO: 调你的检索模块，返回文献列表（每行一条：`序号. 标题 (年份)`）
        content = "1. Attention Is All You Need (2017)\n2. BERT (2019)"
        tool_calls = [{"name": "search", "args": {"query": prompt},
                       "result": "2 hits"}]
        return {"content": content, "tool_calls": tool_calls}

    if family == "T5":
        # TODO: 调你的引用核查模块，返回三分类
        return {"content": '{"verdict": "supported", "reason": "摘要直接支撑该论断"}'}

    if family in ("T1", "T2", "T6", "T7", "T8"):
        # TODO: 调你的生成/Agent 流水线；结论处用 [sN] 标注引用
        return {
            "content": f"## 回答\n（此处为你的 Agent 输出）\n\n针对：{prompt}\n\n结论 [s1]。",
            "citations": [{"marker": "[s1]", "title": "Your Cited Paper",
                           "doi": "", "year": 2024, "url": "", "source": "arxiv"}],
        }

    if family == "T4":
        # 论文全文问答：context.pdf_path 指向本地 PDF
        return {"content": "（依据论文全文作答）"}

    return {"content": ""}


@app.post("/api/bench/generate")
def generate(req: GenerateRequest) -> dict[str, Any]:
    task = req.task or {}
    out = _dispatch(task)
    out.setdefault("content", "")
    out.setdefault("citations", [])
    out.setdefault("tool_calls", [])
    out.setdefault("meta", {})
    out["meta"]["agent"] = "my-agent/1.0"
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
