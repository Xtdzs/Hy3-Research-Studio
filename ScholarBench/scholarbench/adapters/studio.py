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

    # -- T5 引用核对 --------------------------------------------------------
    def _run_citation_verify(self, task: Task) -> Answer:
        """判定：给定论断 + 引用文献，判断引用是否真实存在、是否支撑该论断。

        输出严格三分类之一：supported / unrelated / nonexistent

        方法学依据 [FactCheck]：Agent 化核查 = 先构造查询检索真实世界证据，
        再基于证据做核查决策，而非只看被引摘要。这里先查 OpenAlex 验证文献
        是否存在，把外部核查结果注入判定上下文；外部检索失败时降级为纯判断。
        """
        claim = task.prompt
        ref = task.context.get("reference", {})
        lookup = self._lookup_openalex(ref)
        sys_prompt = (
            "你是学术引用核查员。给定一条论断和一条被引文献，判断二者关系。\n"
            "只输出 JSON：{\"verdict\": \"supported\"|\"unrelated\"|\"nonexistent\", "
            "\"reason\": \"≤40字理由\"}\n"
            "- supported：文献真实存在，且其摘要/结论能支撑该论断\n"
            "- unrelated：文献可能存在，但与该论断无关\n"
            "- nonexistent：文献标题/DOI 疑似伪造，或明显不存在\n"
            "外部检索无任何命中记录时，优先判为 nonexistent。"
        )
        user = (
            f"论断：{claim}\n\n"
            f"被引文献标题：{ref.get('title', '')}\n"
            f"DOI：{ref.get('doi', '')}\n"
            f"年份：{ref.get('year', '')}\n"
            f"摘要：{(ref.get('abstract') or '')[:1200]}\n\n"
            f"外部核查（OpenAlex）结果：{json.dumps(lookup, ensure_ascii=False)}"
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

    @staticmethod
    def _lookup_openalex(ref: dict, timeout: float = 12.0) -> dict:
        """[FactCheck] 外部证据：查询 OpenAlex 判断被引标题是否存在。

        返回 {"searched", "found", "title_match", "top_title", "n_results", "doi_hit"}。
        与 Studio 端 `/api/citation/verify` 的 lookup 保持一致。
        """
        import json as _json  # noqa: PLC0415
        import urllib.error  # noqa: PLC0415
        import urllib.parse
        import urllib.request

        def _tok(t: str) -> set:
            return set(re.sub(r"[^\w\u4e00-\u9fff ]", " ", (t or "").lower()).split())

        title = (ref.get("title") or "").strip()
        if not title:
            return {"searched": False, "found": False, "title_match": 0.0,
                    "top_title": "", "n_results": 0}
        params = urllib.parse.urlencode({
            "search": title[:200],
            "per_page": 3,
            "select": "title,doi,publication_year",
        })
        req = urllib.request.Request(
            f"https://api.openalex.org/works?{params}",
            headers={"User-Agent": "ScholarBench/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if not results:
                return {"searched": True, "found": False, "title_match": 0.0,
                        "top_title": "", "n_results": 0}
            top = results[0]
            rt = _tok(title)
            match = max(len(rt & _tok(r.get("title") or "")) / max(1, len(rt))
                        for r in results)
            return {"searched": True,
                    "found": bool((top.get("title") or "").strip()),
                    "title_match": round(match, 4),
                    "top_title": (top.get("title") or "")[:200],
                    "n_results": len(results),
                    "doi_hit": bool(ref.get("doi")) and (
                        (top.get("doi") or "").replace("https://doi.org/", "")
                        == str(ref.get("doi")).replace("https://doi.org/", ""))}
        except (urllib.error.URLError, OSError, _json.JSONDecodeError) as exc:
            return {"searched": False, "found": False, "title_match": 0.0,
                    "top_title": "", "n_results": 0, "error": str(exc)[:80]}

    # -- T6 学术写作 --------------------------------------------------------
    def _run_writing(self, task: Task) -> Answer:
        kind = task.context.get("writing_type", "abstract")
        guide = {
            "abstract": "撰写结构化摘要（背景/方法/结果/结论），200-300 字，不添加原文没有的信息。",
            "outline": "生成层级大纲，使用 markdown 多级列表，覆盖背景、方法、实验、结论。",
            "expand": "将给定要点扩写为连贯学术段落，不引入新的事实性断言。",
            "survey": "基于给定材料撰写综述片段，关键结论标注 [sN] 引用。",
        }.get(kind, "按要求完成学术写作任务。")
        content = self.client.chat(
            [{"role": "system", "content": f"你是学术写作助手。{guide}"},
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
        content = self.client.chat(
            [{"role": "system", "content":
              "你是研究教练。必须基于给定文献回答，关键结论标注 [sN]；"
              "文献不足时明确指出，不得编造。"},
             {"role": "user", "content": f"文献：\n{ctx}\n\n问题：{task.prompt}"}],
            temperature=0.4,
        )
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
            for d in docs:
                cites.append(Citation(marker=f"[s{len(cites)+1}]", title=d.title,
                                      url=d.url or "", source="studio_search"))
            blocks.append(
                f"【步骤 {i+1}】{q}\n" + "\n".join(
                    f"[s{len(cites)-len(docs)+j+1}] {d.title}" for j, d in enumerate(docs)
                )
            )
        summary = self.client.chat(
            [{"role": "system", "content":
              "基于多步检索结果，整合为结构化结论，关键处标注 [sN] 引用。"},
             {"role": "user", "content": "\n\n".join(blocks) + f"\n\n任务：{task.prompt}"}],
            temperature=0.3,
        )
        return Answer(task_id=task.task_id, system=self.name, content=summary,
                      citations=cites, tool_calls=tool_calls,
                      meta={"steps": len(steps[:3])})

    def close(self) -> None:
        self._client = None
