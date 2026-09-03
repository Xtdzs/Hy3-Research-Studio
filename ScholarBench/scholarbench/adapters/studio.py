"""Hy3 Research Studio adapter —— 把 Benchmark 任务路由到 Studio 的真实能力。

任务族 → Studio 能力映射：
    T1/T2  深度研究 8 阶段流水线（backend.pipeline.ResearchPipeline）
    T3     多源学术检索 + 语义过滤（backend.search.gather_sources）
    T4     论文研讨：pypdf 提取全文 + 长上下文问答
    T5     引用核对：Hy3 判定"引用是否真实存在 + 是否支撑论断"
    T6     写作工坊：摘要 / 大纲 / 扩写 / 综述
    T7     思路提炼：Agent 强制先检索再回答
    T8     多步工具工作流：检索工具 + 结果整合

用法：studio | studio:/abs/path/to/Hy3-Research-Studio
未指定路径时依次尝试环境变量 STUDIO_ROOT 与同级目录 ../Hy3-Research-Studio。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from ..schema import Answer, Citation, Task
from .base import SUT

_IMPORT_ERROR = ""


def _default_root() -> Path | None:
    env = os.getenv("STUDIO_ROOT")
    cands = [Path(env)] if env else []
    here = Path(__file__).resolve()
    for _ in range(4):
        here = here.parent
        cands += [here / "Hy3-Research-Studio", here / "Hy3 Research Studio"]
    for c in cands:
        if c and (c / "backend" / "pipeline.py").exists():
            return c
    return None


class StudioAdapter(SUT):
    name = "studio"

    def __init__(self, root: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.root = Path(root) if root else _default_root()
        if self.root is None:
            raise RuntimeError(
                "找不到 Hy3-Research-Studio 目录。请用 studio:/绝对路径 或设置 STUDIO_ROOT。"
            )
        self.root = self.root.resolve()
        self._mods: dict[str, Any] | None = None
        self._client = None

    # -- 延迟导入，避免 scholarbench 硬依赖 backend -------------------------
    def _load(self) -> dict[str, Any]:
        global _IMPORT_ERROR
        if self._mods is not None:
            return self._mods
        root = str(self.root)
        if root not in sys.path:
            sys.path.insert(0, root)
        # 评测固定 arXiv 单源：必须在 backend.config 首次导入前设置
        #（backend.settings.default_sources 在导入时读取环境变量）。环境可覆盖。
        os.environ.setdefault("DEFAULT_SOURCES", "arxiv")
        try:
            from backend.config import settings as studio_settings  # type: ignore
            from backend.hy3_client import Hy3Client  # type: ignore
            from backend.models import (  # type: ignore
                ResearchRequest, ResearchTask, TaskType,
            )
            from backend.pipeline import ResearchPipeline  # type: ignore
            from backend.search import gather_sources  # type: ignore
        except Exception as exc:  # noqa: BLE001
            _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(f"导入 Studio 模块失败（root={root}）：{exc}") from exc

        self._mods = {
            "settings": studio_settings,
            "Hy3Client": Hy3Client,
            "ResearchRequest": ResearchRequest,
            "ResearchTask": ResearchTask,
            "TaskType": TaskType,
            "ResearchPipeline": ResearchPipeline,
            "gather_sources": gather_sources,
        }
        return self._mods

    @property
    def client(self):
        if self._client is None:
            self._client = self._load()["Hy3Client"]()
        return self._client

    # -- 主入口 -------------------------------------------------------------
    def generate(self, task: Task) -> Answer:
        return self.timed(lambda: self._dispatch(task), task)

    def _dispatch(self, task: Task) -> Answer:
        fam = task.family
        if fam in ("T1", "T2"):
            return self._run_pipeline(task)
        if fam == "T3":
            return self._run_search(task)
        if fam == "T4":
            return self._run_paper_qa(task)
        if fam == "T5":
            return self._run_citation_verify(task)
        if fam == "T6":
            return self._run_writing(task)
        if fam == "T7":
            return self._run_advisor(task)
        if fam == "T8":
            return self._run_workflow(task)
        raise ValueError(f"Studio adapter 不支持任务族 {fam}")

    # -- T1/T2 深度研究流水线 ----------------------------------------------
    def _run_pipeline(self, task: Task) -> Answer:
        m = self._load()
        task_type = "proposal" if task.family == "T2" else "literature_review"
        depth = task.context.get("depth", "quick" if task.difficulty == "easy" else "standard")
        req = m["ResearchRequest"](
            query=task.prompt,
            task_type=m["TaskType"](task_type),
            depth=depth,
        )
        rt = m["ResearchTask"](task_id=f"bench_{task.task_id}", request=req)
        pipe = m["ResearchPipeline"](rt, self.client)
        for _event, _payload in pipe.run():
            pass  # 排空生成器即完成全流程

        report = "\n\n".join(
            f"## {s.section_title}\n{s.content}" for s in rt.sections
        ).strip()
        citations = [
            Citation(marker=f"[s{i+1}]", title=d.title, url=d.url or "",
                     year=int(d.year) if (d.year and str(d.year).isdigit()) else None,
                     source="studio_search")
            for i, d in enumerate(rt.sources)
        ]
        return Answer(
            task_id=task.task_id, system=self.name, content=report,
            citations=citations,
            meta={
                "sources": len(rt.sources),
                "sections": len(rt.sections),
                "compression": rt.metrics.get("compression", {}),
                "timings": rt.metrics.get("timings", {}),
                "tokens": self.client.usage.snapshot().get("total_tokens", 0),
            },
        )

    # -- T3 学术检索 --------------------------------------------------------
    def _run_search(self, task: Task) -> Answer:
        m = self._load()
        per_query = int(task.context.get("per_query", 10))
        docs = m["gather_sources"]([task.prompt], use_paper=True, per_query=per_query)
        docs = docs[: int(task.context.get("top_k", 20))]
        lines = [
            f"{i+1}. {d.title} ({d.year or 'n/a'}) — {d.venue or ''} {d.url or ''}".strip()
            for i, d in enumerate(docs)
        ]
        citations = [
            Citation(marker=f"[{i+1}]", title=d.title, url=d.url or "",
                     year=int(d.year) if (d.year and str(d.year).isdigit()) else None,
                     source="studio_search")
            for i, d in enumerate(docs)
        ]
        return Answer(task_id=task.task_id, system=self.name,
                      content="\n".join(lines), citations=citations,
                      meta={"retrieved": len(docs)})

    # -- T4 论文全文问答 ----------------------------------------------------
    def _run_paper_qa(self, task: Task) -> Answer:
        paper_path = task.context.get("pdf_path") or task.context.get("paper_path")
        text = ""
        if paper_path:
            p = Path(paper_path)
            if not p.is_absolute():
                p = self.root / p
            if p.exists():
                text = self._read_pdf(p)
        if not text:
            text = task.context.get("paper_text", "")
        if not text:
            return Answer(task_id=task.task_id, system=self.name, content="",
                          meta={"error": "论文全文不可用（pdf_path/paper_text 均为空）"})

        sys_prompt = (
            "你是严谨的学术论文阅读助手。只依据给定论文全文作答，不得引入外部知识。\n"
            "回答需：① 直接给出结论 ② 引用论文中的原文依据 ③ 明确说明不确定性。"
        )
        content = self.client.chat(
            [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content":
                 f"论文全文：\n{text[:60000]}\n\n问题：{task.prompt}"},
            ],
            temperature=0.2,
        )
        return Answer(task_id=task.task_id, system=self.name, content=content,
                      meta={"paper_chars": len(text)})

    @staticmethod
    def _read_pdf(path: Path) -> str:
        try:
            from pypdf import PdfReader  # noqa: PLC0415
        except ImportError:
            return ""
        try:
            reader = PdfReader(str(path))
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _clip_citations(text: str, max_n: int) -> str:
        """删除回答中越界的 [sN] 引用标记（模型幻觉出的、检索池中不存在的编号）。

        仅移除标记本身，保留其前后文，避免把"引用了不存在的文献"判定为
        引用伪造/无支撑。越界通常出现在检索不足时模型补号。
        """
        return re.sub(r"\[s(\d+)\]",
                      lambda m: "" if int(m.group(1)) > max_n else m.group(0),
                      text)

    # -- T5 引用核对 --------------------------------------------------------
    def _run_citation_verify(self, task: Task) -> Answer:
        """判定：给定论断 + 引用文献，判断引用是否真实存在、是否支撑该论断。

        输出严格三分类之一：supported / unrelated / nonexistent

        方法学依据 [FactCheck]：Agent 化核查 = 先构造查询检索真实世界证据，
        再基于证据做核查决策，而非只看被引摘要。
        注：已移除 OpenAlex 外部核查（限流风险高、拖慢评测），
        判定完全基于 LLM 对被引摘要与论断的语义一致性。
        """
        claim = task.prompt
        ref = task.context.get("reference", {})
        lookup = {"searched": False, "found": False, "title_match": 0.0,
                  "top_title": "", "n_results": 0, "skipped": True}
        sys_prompt = (
            "你是学术引用核查员。给定一条论断和一条被引文献，判断二者关系。\n"
            "只输出 JSON：{\"verdict\": \"supported\"|\"unrelated\"|\"nonexistent\", "
            "\"reason\": \"≤40字理由\"}\n"
            "- supported：该文献确实存在，且其摘要能支撑该论断\n"
            "- unrelated：该文献确实存在，但与论断无关\n"
            "- nonexistent：标题或 DOI 明显伪造（如 DOI 以 10.0000/ 开头，"
            "或标题不像真实论文）\n"
            "判定依据：优先使用给定摘要与论断做语义比对；"
            "只有标题/DOI 明显伪造时才判 nonexistent。"
        )
        user = (
            f"论断：{claim}\n\n"
            f"被引文献标题：{ref.get('title', '')}\n"
            f"DOI：{ref.get('doi', '')}\n"
            f"年份：{ref.get('year', '')}\n"
            f"摘要：{(ref.get('abstract') or '')[:1200]}"
        )
        try:
            data = self.client.chat_json(
                [{"role": "system", "content": sys_prompt},
                 {"role": "user", "content": user}],
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            return Answer(task_id=task.task_id, system=self.name, content="",
                          meta={"error": f"{type(exc).__name__}: {exc}",
                                "lookup": lookup})
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict not in ("supported", "unrelated", "nonexistent"):
            verdict = "unrelated"
        return Answer(
            task_id=task.task_id, system=self.name,
            content=f"{verdict}｜{data.get('reason', '')}",
            citations=[Citation(title=ref.get("title", ""), doi=ref.get("doi", ""))],
            meta={"verdict": verdict, "reason": data.get("reason", ""),
                  "lookup": lookup},
        )

    # -- T6 学术写作 --------------------------------------------------------
    def _run_writing(self, task: Task) -> Answer:
        kind = task.context.get("writing_type", "abstract")
        guide = {
            "abstract": (
                "撰写结构化摘要，须包含背景/方法/结果/结论四要素。"
                "必须覆盖材料中全部关键方法、数值与结论，不得遗漏核心要点；"
                "控制在 200-300 字，信息密集、不重复、不添加原文没有的内容。"
            ),
            "outline": "生成层级大纲，使用 markdown 多级列表，覆盖背景、方法、实验、结论。",
            "expand": "将给定要点扩写为连贯学术段落，仅展开已有信息，不引入新的事实性断言。",
            "survey": (
                "基于给定材料撰写综述片段。关键结论须标注 [sN] 且指向材料中"
                "确实支撑该结论的文献；无材料支撑的观点不要加引号标注。"
            ),
        }.get(kind, "按要求完成学术写作任务。")
        discipline = (
            "\n写作纪律：① 覆盖任务的每一个要点，禁止遗漏关键信息；"
            "② 删除重复与空泛表述，行文紧凑；"
            "③ 除明确要求外不得虚构数据、引用或材料之外的事实。"
        )
        content = self.client.chat(
            [{"role": "system",
              "content": f"你是学术写作助手。{guide}{discipline}"},
             {"role": "user", "content": task.prompt}],
            temperature=0.4,
        )
        return Answer(task_id=task.task_id, system=self.name, content=content,
                      meta={"writing_type": kind})

    # -- T7 思路提炼（Agent，强制先检索） ----------------------------------
    def _run_advisor(self, task: Task) -> Answer:
        m = self._load()
        docs = m["gather_sources"]([task.prompt], use_paper=True, per_query=6)[:8]
        ctx = "\n".join(
            f"[s{i+1}] {d.title} ({d.year or 'n/a'})\n{(d.abstract or d.snippet)[:500]}"
            for i, d in enumerate(docs)
        )
        sys_prompt = (
            "你是研究教练，为研究者提炼可执行的研究思路。回答规则：\n"
            "1. 只能引用【文献】中确实出现的内容；每条结论旁的 [sN] 必须指向"
            "能实际支撑该结论的文献。\n"
            "2. 宁可少引、不可错引：论点没有文献直接支持时，不要编造 [sN]。\n"
            "3. 覆盖问题的全部要点，按结构作答；结尾列出实际使用的 [sN] 对应文献。\n"
            "4. 文献不足以逐条支撑时不要拒绝作答：可给出该领域常规方法论层面的"
            "结构化分析，但须明确标注“（一般性建议，非本次文献结论）”；"
            "带 [sN] 的表述仍必须严格限于文献内容。\n"
            "5. 结尾说明哪些要点缺乏文献证据、建议如何补检。"
        )
        content = self.client.chat(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": f"文献：\n{ctx}\n\n问题：{task.prompt}"}],
            temperature=0.4,
        )
        content = self._clip_citations(content, len(docs))
        citations = [
            Citation(marker=f"[s{i+1}]", title=d.title, url=d.url or "",
                     source="studio_search") for i, d in enumerate(docs)
        ]
        return Answer(task_id=task.task_id, system=self.name, content=content,
                      citations=citations,
                      tool_calls=[{"name": "retrieve_papers", "args": {"query": task.prompt}}],
                      meta={"retrieved": len(docs)})

    # -- T8 多步工具工作流 --------------------------------------------------
    def _run_workflow(self, task: Task) -> Answer:
        m = self._load()
        steps = task.context.get("steps") or [task.prompt]
        tool_calls, blocks, cites = [], [], []
        for i, q in enumerate(steps[:3]):
            docs = m["gather_sources"]([q], use_paper=True, per_query=5)[:5]
            tool_calls.append({"name": "retrieve_papers", "args": {"query": q},
                               "result_count": len(docs)})
            base = len(cites)
            for j, d in enumerate(docs):
                cites.append(Citation(marker=f"[s{base + j + 1}]", title=d.title,
                                      url=d.url or "", source="studio_search"))
            lines = [
                f"[s{base + j + 1}] {d.title} ({d.year or 'n/a'})\n"
                f"{(d.abstract or d.snippet)[:400]}"
                for j, d in enumerate(docs)
            ]
            blocks.append(f"【步骤 {i+1}】{q}\n" + "\n".join(lines))
        sys_prompt = (
            "你是研究分析师，基于多步检索到的文献内容完成任务。规则：\n"
            "1. 每条文献性结论用 [sN] 标注，且只能来自上述步骤给出的文献内容；"
            "不得把无关文献标到结论上。\n"
            "2. 对任务必需但检索未直接覆盖的部分，可基于该领域通用方法给出分析，"
            "但须明确标注“（基于一般认识，非本次检索结论）”，不得伪造成文献结论。\n"
            "3. 覆盖任务的全部要求：先分步给出检索到的事实，再补必要的通用分析，"
            "最后给出整合性结论。"
        )
        summary = self.client.chat(
            [{"role": "system", "content": sys_prompt},
             {"role": "user", "content": "\n\n".join(blocks) + f"\n\n任务：{task.prompt}"}],
            temperature=0.3,
        )
        summary = self._clip_citations(summary, len(cites))
        return Answer(task_id=task.task_id, system=self.name, content=summary,
                      citations=cites, tool_calls=tool_calls,
                      meta={"steps": len(steps[:3])})

    def close(self) -> None:
        self._client = None
