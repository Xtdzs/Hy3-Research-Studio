"""Mock adapter：返回确定性 canned 回答，用于离线冒烟与 CI。

不调用任何 API，也不依赖 Studio。用于验证「数据集 → 指标 → 报告」链路是否通畅。

    python -m scholarbench.run --split lite --systems mock --no-judge
"""
from __future__ import annotations

from ..schema import Answer, Citation, Task
from .base import SUT

_CANNED = {
    "T1": ("## 背景\n本综述讨论该方向的发展脉络。\n\n## 方法\n方法可分为摘要式压缩、"
           "分层记忆与查询感知压缩三类，其中查询感知压缩在保真度与压缩比之间取得更好平衡。\n\n"
           "## 评测\n常用指标包括关键点召回率与压缩比。\n\n## 局限\n现有工作缺少统一的"
           "评测基准，幻觉风险仍未被充分度量。\n\n## 结论\n该方向仍有明显研究空白。\n\n"
           "参考文献\n[s1] Long Context Compression with Query-Aware Selection. DOI:10.1000/aaa\n"
           "[s2] Hierarchical Memory for Long Documents. DOI:10.1000/bbb"),
    "T2": ("## 研究假设\n若在低资源语言上标注数据少于 1000 条，则参数高效微调不优于"
           "上下文学习。\n\n## 数据集\n使用 XTREME 子集。\n\n## 指标\n准确率与 F1。\n\n"
           "## 基线\n全量微调与少样本提示。\n\n## 预期结果\n在多数语言上两者无显著差异。"),
    "T3": ("1. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (2020)\n"
           "2. Dense Passage Retrieval for Open-Domain QA (2020)\n"
           "3. Lost in the Middle: How Language Models Use Long Contexts (2023)\n"
           "4. Chain-of-Thought Prompting Elicits Reasoning (2022)\n"
           "5. Self-Consistency Improves Chain of Thought Reasoning (2022)"),
    "T4": ("该论文提出的核心机制是自注意力（Scaled Dot-Product Attention）与多头注意力，"
           "相比循环结构可并行化，路径长度为常数，因此更易建模长距离依赖。"),
    "T5": "supported",
    "T6": ("背景：长上下文推理成本高。方法：提出查询感知压缩。结果：上下文压缩至 1/5，"
           "关键点召回保持 92%。结论：可在降低成本的同时保住关键信息。"),
    "T7": ("建议先从数据来源入手：OpenAlex 与 Semantic Scholar 都提供免费引文接口。"
           "下一步可以先做一个 500 篇的小规模图，验证布局与交互。"),
    "T8": ("## 检索结果整合\n压缩方法主要包括摘要式压缩与查询感知压缩；"
           "评测基准方面，现有工作缺少统一协议。"),
}


class MockAdapter(SUT):
    name = "mock"

    def __init__(self, fail: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.fail = fail      # 传入 task_id 前缀可强制失败，用于测试降级路径

    def generate(self, task: Task) -> Answer:
        def _run() -> Answer:
            if self.fail and task.task_id.startswith(self.fail):
                return Answer(task_id=task.task_id, system=self.name, content="",
                              meta={"error": "mock forced failure"})
            content = _CANNED.get(task.family, "（mock 回答）")
            cites: list[Citation] = []
            if task.family == "T3":
                cites = [Citation(marker=f"[{i+1}]", title=ln.split(" (")[0][3:],
                                  year=2020, source="mock")
                         for i, ln in enumerate(content.splitlines())]
            elif task.family in ("T1", "T2"):
                cites = [Citation(marker="[s1]",
                                  title="Long Context Compression with Query-Aware Selection",
                                  doi="10.1000/aaa", year=2023, source="mock"),
                         Citation(marker="[s2]", title="Hierarchical Memory for Long Documents",
                                  doi="10.1000/bbb", year=2022, source="mock")]
            meta: dict = {"mock": True}
            if task.family == "T5":
                meta["verdict"] = "supported"
            if task.family == "T7":
                return Answer(task_id=task.task_id, system=self.name, content=content,
                              citations=cites,
                              tool_calls=[{"name": "retrieve_papers",
                                           "args": {"query": task.prompt}}], meta=meta)
            if task.family == "T8":
                steps = task.context.get("steps", [task.prompt])
                return Answer(task_id=task.task_id, system=self.name, content=content,
                              citations=cites,
                              tool_calls=[{"name": "retrieve_papers",
                                           "args": {"query": q}} for q in steps], meta=meta)
            return Answer(task_id=task.task_id, system=self.name, content=content,
                          citations=cites, meta=meta)
        return self.timed(_run, task)
