"""Research Workflow Pipeline.

Stages (each powered by Hy3):
  A. Planning            -> ResearchPlan
  B. Evidence Search     -> SourceDocument[]  (arXiv / S2 / uploads)
  C. Evidence Compression-> EvidencePacket[]  (the key differentiator)
  D. Report Generation   -> ReportSection[]   (section by section, streamed)
  E. Citation Grounding  -> [source_id] refs resolved per section

`run()` is a generator that yields (event, payload) so the API layer can stream
progress over SSE. Timings (TTFP / TTFE / TTFR / TTR) and token usage are tracked.
"""
from __future__ import annotations

import re
import time
from typing import Iterator

from .hy3_client import Hy3Client
from .models import (
    Depth,
    EvidencePacket,
    ExperimentDesign,
    EvidenceEdge,
    ResearchGap,
    ResearchHypothesis,
    ReportSection,
    ResearchPlan,
    ResearchTask,
    SourceDocument,
    SourceType,
    SubQuestion,
    TaskStatus,
)
from . import prompts
from .search import gather_sources
from .store import store

_CITATION_RE = re.compile(r"\[(s\d+)\]")

DEPTH_SOURCES = {Depth.quick: 4, Depth.standard: 6, Depth.max: 8}


class ResearchPipeline:
    def __init__(self, task: ResearchTask, client: Hy3Client) -> None:
        self.task = task
        self.client = client
        self.t0 = time.time()
        self.timings: dict[str, float] = {}

    def _elapsed(self) -> float:
        return round(time.time() - self.t0, 2)

    # -- main generator -------------------------------------------------------
    def run(self) -> Iterator[tuple[str, dict]]:
        try:
            yield from self._stage_plan()
            yield from self._stage_search()
            yield from self._stage_compress()
            yield from self._stage_hypotheses()
            yield from self._stage_evidence_graph()
            yield from self._stage_gaps()
            yield from self._stage_experiments()
            yield from self._stage_report()
            self.task.status = TaskStatus.done
            self.task.metrics = self._final_metrics()
            store.save_task(self.task)
            yield "done", {"metrics": self.task.metrics}
        except Exception as exc:  # noqa: BLE001
            self.task.status = TaskStatus.error
            self.task.error = str(exc)
            store.save_task(self.task)
            yield "error", {"message": str(exc)}

    # -- A. planning ----------------------------------------------------------
    def _stage_plan(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.planning
        yield "status", {"stage": "planning", "label": "研究规划中"}
        data = self.client.chat_json(
            prompts.planner_prompt(self.task.request), temperature=0.4
        )
        subqs = [
            SubQuestion(
                id=sq.get("id") or f"sq{i+1}",
                question=sq.get("question", ""),
                rationale=sq.get("rationale", ""),
                queries=[q for q in sq.get("queries", []) if q][:3],
            )
            for i, sq in enumerate(data.get("subquestions", []))
        ]
        plan = ResearchPlan(
            rewritten_goal=data.get("rewritten_goal", self.task.request.query),
            subquestions=subqs,
            report_outline=data.get("report_outline", []),
            key_dimensions=data.get("key_dimensions", []),
        )
        self.task.plan = plan
        self.timings["ttfp"] = self._elapsed()
        store.save_task(self.task)
        yield "plan", {"plan": plan.model_dump(), "ttfp": self.timings["ttfp"]}

    # -- B. search ------------------------------------------------------------
    def _stage_search(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.searching
        yield "status", {"stage": "searching", "label": "多源检索中"}
        assert self.task.plan

        use_paper = SourceType.paper in self.task.request.sources
        per_query = DEPTH_SOURCES[self.task.request.depth]
        # 引用文献数量目标：据此放大每子问题检索量，确保有足够来源可引用
        target = self.task.request.citation_count
        if target:
            n_sq = max(1, len(self.task.plan.subquestions))
            per_query = max(per_query, min(12, (target + n_sq - 1) // n_sq + 1))

        global_sources: dict[str, SourceDocument] = {}
        self._sq_source_ids: dict[str, list[str]] = {}
        counter = 0

        # uploaded docs + 用户从文库/文献检索选中的资料，对所有子问题可用
        preset_sources = self._load_uploads() + self._load_extras()
        for doc in preset_sources:
            counter += 1
            doc.source_id = f"s{counter}"
            global_sources[doc.source_id] = doc

        for sq in self.task.plan.subquestions:
            queries = sq.queries or [sq.question]
            docs = gather_sources(queries, use_paper=use_paper, per_query=per_query)
            ids: list[str] = [d.source_id for d in preset_sources]
            for doc in docs[: per_query + 2]:
                key = re.sub(r"[^a-z0-9]", "", doc.title.lower())[:60]
                existing = next(
                    (s for s in global_sources.values()
                     if re.sub(r"[^a-z0-9]", "", s.title.lower())[:60] == key),
                    None,
                )
                if existing:
                    ids.append(existing.source_id)
                    continue
                counter += 1
                doc.source_id = f"s{counter}"
                global_sources[doc.source_id] = doc
                ids.append(doc.source_id)
            self._sq_source_ids[sq.id] = ids
            yield "search_progress", {
                "subquestion_id": sq.id,
                "question": sq.question,
                "count": len(ids),
            }

        self.task.sources = list(global_sources.values())
        if "ttfe" not in self.timings:
            self.timings["ttfe"] = self._elapsed()
        store.save_task(self.task)
        yield "evidence_sources", {
            "sources": [s.model_dump() for s in self.task.sources],
            "ttfe": self.timings["ttfe"],
        }

    def _load_uploads(self) -> list[SourceDocument]:
        out: list[SourceDocument] = []
        for uid in self.task.request.upload_ids:
            doc = store.get_upload(uid)
            if not doc:
                continue
            out.append(
                SourceDocument(
                    source_id="",
                    title=doc.filename,
                    source_type=SourceType.upload,
                    abstract=doc.text[:800],
                    snippet=doc.text[:1500],
                )
            )
        return out

    def _load_extras(self) -> list[SourceDocument]:
        out: list[SourceDocument] = []
        for d in self.task.request.extra_sources:
            doc = d.model_copy()
            doc.source_id = ""
            if not doc.abstract and doc.snippet:
                doc.abstract = doc.snippet
            if not doc.snippet and doc.abstract:
                doc.snippet = doc.abstract[:600]
            out.append(doc)
        return out

    # -- C. compression -------------------------------------------------------
    def _stage_compress(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.compressing
        yield "status", {"stage": "compressing", "label": "证据压缩中"}
        assert self.task.plan

        source_by_id = {s.source_id: s for s in self.task.sources}
        packet_counter = 0
        raw_chars = 0
        packet_chars = 0

        for sq in self.task.plan.subquestions:
            sids = self._sq_source_ids.get(sq.id, [])
            docs = [source_by_id[i] for i in sids if i in source_by_id]
            if not docs:
                continue
            block_lines = []
            for d in docs:
                content = d.snippet or d.abstract
                raw_chars += len(content)
                block_lines.append(
                    f"[{d.source_id}] {d.title} ({d.venue or ''} {d.year or ''})\n{content}"
                )
            sources_block = "\n\n".join(block_lines)
            try:
                data = self.client.chat_json(
                    prompts.compressor_prompt(
                        sq.question, sources_block, self.task.request.language
                    ),
                    temperature=0.3,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[compress] {sq.id} failed: {exc}")
                continue
            for p in data.get("packets", []):
                packet_counter += 1
                valid_refs = [
                    r for r in p.get("support_source_ids", []) if r in source_by_id
                ]
                packet = EvidencePacket(
                    packet_id=f"p{packet_counter}",
                    subquestion_id=sq.id,
                    topic=p.get("topic", ""),
                    claim=p.get("claim", ""),
                    method=p.get("method", ""),
                    setting=p.get("setting", ""),
                    limitation=p.get("limitation", ""),
                    support_source_ids=valid_refs,
                    support_score=float(p.get("support_score", 0) or 0),
                )
                packet_chars += len(
                    packet.claim + packet.method + packet.setting + packet.limitation
                )
                self.task.packets.append(packet)
            yield "compress_progress", {
                "subquestion_id": sq.id,
                "packets": packet_counter,
            }

        ratio = round(raw_chars / packet_chars, 2) if packet_chars else 0.0
        self.task.metrics["compression"] = {
            "raw_chars": raw_chars,
            "packet_chars": packet_chars,
            "compression_ratio": ratio,
        }
        store.save_task(self.task)
        yield "evidence_packets", {
            "packets": [p.model_dump() for p in self.task.packets],
            "compression_ratio": ratio,
        }

    # -- C2. hypothesis generation --------------------------------------------
    def _stage_hypotheses(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.hypothesizing
        yield "status", {"stage": "hypothesizing", "label": "生成研究假设中"}
        if not self.task.packets:
            yield "hypotheses", {"items": []}
            return
        try:
            data = self.client.chat_json(
                prompts.hypotheses_prompt(
                    self.task.plan.rewritten_goal, self._packets_block(), self.task.request.language
                ),
                temperature=0.4,
            )
            items = data.get("hypotheses", [])[:5]
            for i, h in enumerate(items):
                self.task.hypotheses.append(ResearchHypothesis(
                    hypothesis_id=f"h{i+1}",
                    statement=h.get("statement", ""),
                    rationale=h.get("rationale", ""),
                    based_on=[b for b in h.get("based_on", []) if b][:6],
                    testability=h.get("testability", ""),
                    confidence=float(h.get("confidence", 0) or 0),
                ))
        except Exception as exc:  # noqa: BLE001
            print(f"[hypotheses] failed: {exc}")
        store.save_task(self.task)
        yield "hypotheses", {"items": [h.model_dump() for h in self.task.hypotheses]}

    # -- C3. evidence graph ----------------------------------------------------
    def _stage_evidence_graph(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.graphing
        yield "status", {"stage": "graphing", "label": "构建证据图谱中"}
        if len(self.task.packets) < 2:
            yield "evidence_graph", {"edges": []}
            return
        try:
            data = self.client.chat_json(
                prompts.evidence_graph_prompt(self._packets_block(), self.task.request.language),
                temperature=0.3,
            )
            valid = {p.packet_id for p in self.task.packets}
            for e in data.get("edges", []):
                f, t = e.get("from_packet"), e.get("to_packet")
                if f in valid and t in valid and f != t:
                    self.task.evidence_graph.append(EvidenceEdge(
                        from_packet=f, to_packet=t,
                        relation=e.get("relation", "support") or "support",
                        note=e.get("note", ""),
                    ))
        except Exception as exc:  # noqa: BLE001
            print(f"[evidence_graph] failed: {exc}")
        store.save_task(self.task)
        yield "evidence_graph", {"edges": [e.model_dump() for e in self.task.evidence_graph]}

    # -- C4. research gap finder ----------------------------------------------
    def _stage_gaps(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.gapping
        yield "status", {"stage": "gapping", "label": "挖掘研究空白中"}
        try:
            data = self.client.chat_json(
                prompts.gap_prompt(
                    self._packets_block(), self._hypotheses_block(), self.task.request.language
                ),
                temperature=0.4,
            )
            for i, g in enumerate(data.get("gaps", [])[:5]):
                self.task.gaps.append(ResearchGap(
                    gap_id=f"g{i+1}",
                    title=g.get("title", ""),
                    description=g.get("description", ""),
                    why=g.get("why", ""),
                    suggested_direction=g.get("suggested_direction", ""),
                    related_hypotheses=[x for x in g.get("related_hypotheses", []) if x][:4],
                ))
        except Exception as exc:  # noqa: BLE001
            print(f"[gaps] failed: {exc}")
        store.save_task(self.task)
        yield "gaps", {"items": [g.model_dump() for g in self.task.gaps]}

    # -- C5. experiment designer ----------------------------------------------
    def _stage_experiments(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.experimenting
        yield "status", {"stage": "experimenting", "label": "设计验证实验中"}
        try:
            data = self.client.chat_json(
                prompts.experiment_prompt(
                    self._hypotheses_block(), self._gaps_block(), self.task.request.language
                ),
                temperature=0.4,
            )
            for i, x in enumerate(data.get("experiments", [])[:4]):
                self.task.experiments.append(ExperimentDesign(
                    experiment_id=f"e{i+1}",
                    title=x.get("title", ""),
                    hypothesis_ref=x.get("hypothesis_ref", "") or "",
                    method=x.get("method", ""),
                    dataset=x.get("dataset", ""),
                    metrics=[m for m in x.get("metrics", []) if m][:6],
                    baseline=x.get("baseline", ""),
                    expected_outcome=x.get("expected_outcome", ""),
                ))
        except Exception as exc:  # noqa: BLE001
            print(f"[experiments] failed: {exc}")
        store.save_task(self.task)
        yield "experiments", {"items": [x.model_dump() for x in self.task.experiments]}

    def _hypotheses_block(self) -> str:
        if not self.task.hypotheses:
            return "（暂未生成研究假设）"
        return "\n".join(
            f"- [{h.hypothesis_id}] {h.statement}（置信度 {h.confidence}）" for h in self.task.hypotheses
        )

    def _gaps_block(self) -> str:
        if not self.task.gaps:
            return "（暂未识别研究空白）"
        return "\n".join(
            f"- [{g.gap_id}] {g.title}：{g.suggested_direction}" for g in self.task.gaps
        )

    # -- D + E. report generation & citation grounding ------------------------
    def _stage_report(self) -> Iterator[tuple[str, dict]]:
        self.task.status = TaskStatus.writing
        yield "status", {"stage": "writing", "label": "报告生成中"}
        assert self.task.plan

        packets_block = self._packets_block()
        insights_block = self._insights_block()
        prev_titles: list[str] = []
        outline = self.task.plan.report_outline or ["研究背景", "研究现状", "总结"]

        for idx, title in enumerate(outline):
            section_id = f"sec{idx+1}"
            yield "section_start", {"section_id": section_id, "title": title}
            messages = prompts.section_prompt(
                self.task.request,
                title,
                self.task.plan.rewritten_goal,
                packets_block,
                prev_titles,
                citation_target=self.task.request.citation_count,
                insights_block=insights_block,
            )
            content_parts: list[str] = []
            for delta in self.client.chat_stream(messages, temperature=0.5):
                content_parts.append(delta)
                yield "section_delta", {"section_id": section_id, "delta": delta}
            content = "".join(content_parts).strip()

            cited = sorted(set(_CITATION_RE.findall(content)),
                           key=lambda x: int(x[1:]))
            section = ReportSection(
                section_id=section_id,
                section_title=title,
                content=content,
                citation_source_ids=cited,
            )
            self.task.sections.append(section)
            prev_titles.append(title)

            if "ttfr" not in self.timings:
                self.timings["ttfr"] = self._elapsed()
            store.save_task(self.task)
            yield "section_done", {
                "section_id": section_id,
                "title": title,
                "content": content,
                "citations": cited,
                "ttfr": self.timings.get("ttfr"),
            }

    def _packets_block(self) -> str:
        lines = []
        for p in self.task.packets:
            refs = "".join(f"[{r}]" for r in p.support_source_ids)
            lines.append(
                f"- [{p.packet_id}] 主题：{p.topic} {refs}\n"
                f"  结论：{p.claim}\n"
                f"  方法：{p.method}\n"
                f"  局限：{p.limitation}"
            )
        return "\n".join(lines) if lines else "（暂无结构化证据，请基于研究目标谨慎撰写）"

    def _insights_block(self) -> str:
        parts = []
        if self.task.hypotheses:
            parts.append("【已生成的研究假设】\n" + self._hypotheses_block())
        if self.task.gaps:
            parts.append("【已识别的研究空白】\n" + self._gaps_block())
        return "\n\n".join(parts) if parts else "（暂无额外研究洞察）"

    # -- metrics --------------------------------------------------------------
    def _final_metrics(self) -> dict:
        self.timings["ttr"] = self._elapsed()
        metrics = dict(self.task.metrics)
        all_cites = set()
        for sec in self.task.sections:
            all_cites.update(sec.citation_source_ids)
        metrics.update(
            {
                "tokens": self.client.usage.snapshot(),
                "timings": self.timings,
                "num_sources": len(self.task.sources),
                "num_packets": len(self.task.packets),
                "num_sections": len(self.task.sections),
                "num_citations": len(all_cites),
                "citation_target": self.task.request.citation_count,
            }
        )
        return metrics
