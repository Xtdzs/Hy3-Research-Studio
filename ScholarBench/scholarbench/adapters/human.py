"""Human adapter —— 人工作答，产出"人类基线"上界锚点。

Leaderboard 若只有模型互相比，读者无法判断"60 分算好还是差"。
用 human adapter 标注 20%-30% 样本，即可得到绝对参照系。

用法：human | human:annotator_A
交互方式：打印题目 → 终端多行输入（空行+回车结束）→ 追问引用条数。
非交互环境（stdin 非 tty）自动跳过并返回 error，不阻塞批量评测。
"""
from __future__ import annotations

import sys

from ..schema import Answer, Citation, Task
from .base import SUT


class HumanAdapter(SUT):
    name = "human"

    def __init__(self, annotator: str = "human", **kwargs) -> None:
        super().__init__(**kwargs)
        self.annotator = annotator
        self.name = f"human:{annotator}"

    def generate(self, task: Task) -> Answer:
        if not sys.stdin or not sys.stdin.isatty():
            return Answer(task_id=task.task_id, system=self.name, content="",
                          meta={"error": "non-interactive stdin，跳过人工作答"})
        print("\n" + "=" * 70)
        print(f"[{task.task_id}] ({task.family}/{task.difficulty}) {task.prompt}")
        print("-" * 70)
        print("请输入回答（单独一行输入 END 结束）：")
        lines = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if line.strip() == "END":
                break
            lines.append(line)
        content = "\n".join(lines).strip()
        if not content:
            return Answer(task_id=task.task_id, system=self.name, content="",
                          meta={"error": "empty human answer"})

        cites = []
        try:
            n = int(input("引用条数（回车=0）：").strip() or 0)
        except (EOFError, ValueError):
            n = 0
        for i in range(n):
            title = input(f"  引用{i+1} 标题：").strip()
            doi = input(f"  引用{i+1} DOI（可空）：").strip()
            cites.append(Citation(marker=f"[s{i+1}]", title=title, doi=doi))
        return Answer(task_id=task.task_id, system=self.name, content=content,
                      citations=cites, meta={"annotator": self.annotator})
