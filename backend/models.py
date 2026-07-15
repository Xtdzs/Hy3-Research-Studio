"""Pydantic data models mirroring the objects described in the design doc."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TaskType(str, Enum):
    literature_review = "literature_review"   # 文献综述
    tech_survey = "tech_survey"               # 技术调研
    proposal = "proposal"                     # 开题汇报
    plan_report = "plan_report"               # 项目方案 / 申报


class Language(str, Enum):
    zh = "zh"
    en = "en"


class Style(str, Enum):
    academic = "academic"     # 学术综述
    advisor = "advisor"       # 导师汇报
    technical = "technical"   # 技术方案
    concise = "concise"       # 简洁版


class Depth(str, Enum):
    quick = "quick"
    standard = "standard"
    max = "max"


class SourceType(str, Enum):
    paper = "paper"
    web = "web"
    upload = "upload"
    note = "note"


# --- request payloads --------------------------------------------------------
class ResearchRequest(BaseModel):
    query: str = Field(..., description="研究主题 / 问题")
    task_type: TaskType = TaskType.literature_review
    language: Language = Language.zh
    style: Style = Style.academic
    depth: Depth = Depth.standard
    sources: list[SourceType] = Field(default_factory=lambda: [SourceType.paper])
    focus: Optional[str] = Field(None, description="用户关注点，如更关注评测/局限")
    citation_count: Optional[int] = Field(
        None, ge=0, description="期望引用的文献数量；0 / 不填表示由系统自动决定"
    )
    upload_ids: list[str] = Field(default_factory=list)
    extra_sources: list[SourceDocument] = Field(
        default_factory=list,
        description="来自文库/文献检索页选中的资料，直接作为研究上下文",
    )


class RefineRequest(BaseModel):
    task_id: str
    section_id: str
    action: str  # expand | shorten | restyle | add_citation | rebuttal
    style: Optional[Style] = None


class ToolRequest(BaseModel):
    tool: str  # abstract | outline | paragraph
    topic: str
    language: Language = Language.zh
    sources: list[SourceDocument] = Field(default_factory=list)


class SmartSearchRequest(BaseModel):
    topic: str = Field(..., description="用户的检索方向 / 意图")
    language: Language = Language.zh
    steps: int = Field(3, ge=1, le=6, description="多步检索的检索式数量")
    per_query: int = Field(6, ge=3, le=20, description="每条检索式抓取篇数")


class PaperChatRequest(BaseModel):
    paper_id: str = Field(..., description="已上传论文的 id")
    message: str = Field(..., description="用户当前的提问")
    history: list[dict[str, str]] = Field(
        default_factory=list, description="历史对话 [{role, content}]"
    )
    language: Language = Language.zh


# --- domain objects ----------------------------------------------------------
class SubQuestion(BaseModel):
    id: str
    question: str
    rationale: str = ""
    queries: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    rewritten_goal: str
    subquestions: list[SubQuestion]
    report_outline: list[str]
    key_dimensions: list[str] = Field(default_factory=list)


class SourceDocument(BaseModel):
    source_id: str
    title: str
    source_type: SourceType
    url: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    year: Optional[str] = None
    venue: Optional[str] = None
    abstract: str = ""
    snippet: str = ""


class EvidencePacket(BaseModel):
    packet_id: str
    subquestion_id: str
    topic: str = ""
    claim: str = ""
    method: str = ""
    setting: str = ""
    limitation: str = ""
    support_source_ids: list[str] = Field(default_factory=list)
    support_score: float = 0.0


class ResearchHypothesis(BaseModel):
    hypothesis_id: str
    statement: str = ""            # 假设陈述
    rationale: str = ""            # 为什么有证据支撑
    based_on: list[str] = Field(default_factory=list)   # 支撑的 packet_id / source_id
    testability: str = ""          # 可验证性说明
    confidence: float = 0.0        # 0~1，基于证据充分度


class EvidenceEdge(BaseModel):
    from_packet: str
    to_packet: str
    relation: str = "support"      # support | contradict | extend | specialize
    note: str = ""


class ResearchGap(BaseModel):
    gap_id: str
    title: str = ""
    description: str = ""
    why: str = ""                  # 基于哪些证据的局限/矛盾
    suggested_direction: str = ""
    related_hypotheses: list[str] = Field(default_factory=list)


class ExperimentDesign(BaseModel):
    experiment_id: str
    title: str = ""
    hypothesis_ref: str = ""       # 关联的 hypothesis_id
    method: str = ""
    dataset: str = ""
    metrics: list[str] = Field(default_factory=list)
    baseline: str = ""
    expected_outcome: str = ""


class ReportSection(BaseModel):
    section_id: str
    section_title: str
    content: str = ""
    linked_packet_ids: list[str] = Field(default_factory=list)
    citation_source_ids: list[str] = Field(default_factory=list)


class TaskStatus(str, Enum):
    created = "created"
    planning = "planning"
    searching = "searching"
    compressing = "compressing"
    hypothesizing = "hypothesizing"
    graphing = "graphing"
    gapping = "gapping"
    experimenting = "experimenting"
    writing = "writing"
    done = "done"
    error = "error"


class ResearchTask(BaseModel):
    task_id: str
    request: ResearchRequest
    status: TaskStatus = TaskStatus.created
    created_at: datetime = Field(default_factory=datetime.utcnow)
    plan: Optional[ResearchPlan] = None
    sources: list[SourceDocument] = Field(default_factory=list)
    packets: list[EvidencePacket] = Field(default_factory=list)
    hypotheses: list[ResearchHypothesis] = Field(default_factory=list)
    evidence_graph: list[EvidenceEdge] = Field(default_factory=list)
    gaps: list[ResearchGap] = Field(default_factory=list)
    experiments: list[ExperimentDesign] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    error: Optional[str] = None
