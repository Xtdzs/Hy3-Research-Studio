"""系统适配层（SUT: System Under Test）。

对外契约极其简单：

    class SUT:
        name: str
        def generate(self, task: Task) -> Answer

任何人只要实现这个接口（约 50 行）就能把自己的系统接入 ScholarBench。
"""
from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from typing import Iterable

from ..schema import Answer, Citation, Task

_CITE_PATTERNS = [
    re.compile(r"\[s(\d+)\]", re.I),      # [s1]
    re.compile(r"\[r(\d+)\]", re.I),      # [r1]
    re.compile(r"\[(\d+)\]"),             # [1]
]


class SUT(ABC):
    """被测系统抽象基类。"""

    name: str = "base"

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    @abstractmethod
    def generate(self, task: Task) -> Answer:
        """对单道题生成回答。实现方必须捕获异常并写入 meta['error']。"""

    # -- 可选：批量（默认串行） -------------------------------------------
    def generate_batch(self, tasks: Iterable[Task]) -> list[Answer]:
        return [self.generate(t) for t in tasks]

    def close(self) -> None:  # noqa: B027
        """释放资源（可选）。"""

    # -- 工具方法 ----------------------------------------------------------
    @staticmethod
    def timed(fn, task: Task) -> Answer:
        """包一层计时；异常统一降级为 meta['error']，不中断全量评测。"""
        t0 = time.time()
        try:
            ans = fn()
        except Exception as exc:  # noqa: BLE001
            ans = Answer(task_id=task.task_id, system="", content="",
                         meta={"error": f"{type(exc).__name__}: {exc}"})
        ans.meta.setdefault("wall", round(time.time() - t0, 2))
        return ans


def extract_citation_markers(text: str) -> list[str]:
    """抽取正文中出现的引用标记（不去重），如 [s1] [3]。"""
    marks: list[str] = []
    for pat in _CITE_PATTERNS:
        marks.extend(m.group(0) for m in pat.finditer(text or ""))
    return marks


def parse_reference_block(text: str) -> list[Citation]:
    """从文末参考文献块解析引用。兼容以下常见形态：

    [s1] Title. DOI:10.xxx/yyy
    [1] Title (2023). https://...
    - Title — 10.xxx/yyy
    """
    cites: list[Citation] = []
    if not text:
        return cites
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^\[(?:s|r)?(\d+)\]\s*(.+)$", line, re.I)
        if not m:
            continue
        idx, body = m.group(1), m.group(2)
        doi_m = re.search(r"(10\.\d{4,9}/[^\s,;)\]]+)", body)
        year_m = re.search(r"\b(19|20)(\d{2})\b", body)
        title = re.split(r"\.\s|—|–|\s{2,}", body.strip())[0].strip(" .")
        cites.append(Citation(
            marker=f"[{idx}]",
            title=title[:300],
            doi=doi_m.group(1) if doi_m else "",
            year=int(year_m.group(0)) if year_m else None,
        ))
    return cites


def normalize_answer(text: str) -> str:
    """文本归一化，用于 F1 / 匹配类指标。"""
    s = (text or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\u4e00-\u9fff ]", "", s)
    return s


def token_f1(pred: str, gold: str) -> float:
    """基于归一化的 token F1（中英文混合可用）。"""
    p = normalize_answer(pred).split()
    g = normalize_answer(gold).split()
    if not p or not g:
        return float(bool(p) and bool(g))
    from collections import Counter
    cp, cg = Counter(p), Counter(g)
    overlap = sum((cp & cg).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(p)
    recall = overlap / len(g)
    return round(2 * precision * recall / (precision + recall), 4)
