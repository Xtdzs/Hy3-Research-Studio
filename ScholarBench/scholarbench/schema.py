"""ScholarBench 核心数据契约（对应 SCHEMA.md）。

三套契约：
    Task        —— 一道评测题（公开）
    Answer      —— 被测系统的输出（SUT 产出）
    EvalResult  —— 一条评测结果（客观指标 + Rubric + 合成分）

本模块只依赖标准库，保证 `scholarbench` 可被独立复制使用。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# --- 任务族 ---------------------------------------------------------------
FAMILIES = {
    "T1": "文献综述生成",
    "T2": "研究开题与实验设计",
    "T3": "学术检索与相关性筛选",
    "T4": "论文深度问答",
    "T5": "引用核对与事实核查",
    "T6": "学术写作",
    "T7": "研究思路 Agent 多轮对话",
    "T8": "多步工具工作流",
}

# --- 原子能力 -------------------------------------------------------------
CAPABILITIES = {
    "C1": "检索召回",
    "C2": "证据压缩",
    "C3": "长文理解",
    "C4": "引用溯源",
    "C5": "结构化生成",
    "C6": "工具调用",
    "C7": "多轮对话",
    "C8": "安全合规",
}

# 每个任务族依赖的能力（用于生成 8 维能力画像）
FAMILY_CAPABILITIES: dict[str, list[str]] = {
    "T1": ["C1", "C2", "C5", "C8"],
    "T2": ["C2", "C5", "C8"],
    "T3": ["C1", "C6"],
    "T4": ["C3", "C4", "C8"],
    "T5": ["C4", "C8"],
    "T6": ["C3", "C5"],
    "T7": ["C1", "C6", "C7"],
    "T8": ["C6", "C7", "C8"],
}

# 任务族在总分中的权重（Σ = 1.0）
FAMILY_WEIGHTS: dict[str, float] = {
    "T1": 0.18, "T2": 0.12, "T3": 0.12, "T4": 0.16,
    "T5": 0.14, "T6": 0.10, "T7": 0.10, "T8": 0.08,
}

# 每个任务族客观指标与 Rubric 的混合系数 α（α 越大越依赖客观指标）
FAMILY_ALPHA: dict[str, float] = {
    "T1": 0.45, "T2": 0.35, "T3": 0.85, "T4": 0.70,
    "T5": 0.85, "T6": 0.45, "T7": 0.60, "T8": 0.70,
}

DIFFICULTIES = ("easy", "medium", "hard")


@dataclass
class Citation:
    """一条引用。marker 为正文中的引用标记，如 "[s3]"。"""
    marker: str = ""
    title: str = ""
    doi: str = ""
    year: int | None = None
    url: str = ""
    source: str = ""          # crossref / arxiv / unknown

    def key(self) -> str:
        return (self.doi or self.title or "").strip().lower()


@dataclass
class Task:
    """一道评测题。公开部分；判定所需答案锚点放在 keys_heldout 中。"""
    task_id: str
    family: str                       # T1..T8
    suite: str = ""                   # 如 T3_search
    difficulty: str = "medium"
    prompt: str = ""                  # 交给被测系统的输入
    capability: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)   # pdf_path / gold_pool_id / ...
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.capability:
            self.capability = FAMILY_CAPABILITIES.get(self.family, [])
        if not self.suite:
            self.suite = f"{self.family}_{'x'}"

    @property
    def alpha(self) -> float:
        return FAMILY_ALPHA.get(self.family, 0.5)

    @property
    def weight(self) -> float:
        return FAMILY_WEIGHTS.get(self.family, 0.0)

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Answer:
    """被测系统对一道题的输出。"""
    task_id: str
    system: str
    content: str = ""
    citations: list[Citation] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)   # tokens / wall / error ...

    @property
    def ok(self) -> bool:
        return not self.meta.get("error") and bool(self.content.strip())

    @classmethod
    def from_dict(cls, d: dict) -> "Answer":
        cites = [Citation(**c) if isinstance(c, dict) else Citation(title=str(c))
                 for c in d.get("citations", [])]
        return cls(
            task_id=d.get("task_id", ""),
            system=d.get("system", ""),
            content=d.get("content", ""),
            citations=cites,
            tool_calls=d.get("tool_calls", []) or [],
            meta=d.get("meta", {}) or {},
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class RubricScore:
    """Rubric 单维度评分。"""
    dim: str            # D1..D7
    score: float        # 1-5
    reason: str = ""
    quote: str = ""


@dataclass
class EvalResult:
    task_id: str = ""
    family: str = ""
    difficulty: str = "medium"
    system: str = ""

    objective: dict[str, float] = field(default_factory=dict)   # 客观指标
    objective_score: float = 0.0                                 # 0-100
    rubric: list[RubricScore] = field(default_factory=list)
    rubric_score: float = 0.0                                    # 0-100
    task_score: float = 0.0                                      # 0-100 合成

    errors: list[str] = field(default_factory=list)              # 失败归因标签
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rubric"] = [asdict(r) for r in self.rubric]
        return d


# --- IO helpers ------------------------------------------------------------
def read_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(json.loads(line))
    return out


def write_jsonl(path: str | Path, rows: list[dict]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def load_tasks(path: str | Path) -> list[Task]:
    return [Task.from_dict(d) for d in read_jsonl(path)]
