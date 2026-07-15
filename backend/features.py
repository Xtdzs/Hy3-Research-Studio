"""Persistence for the "创造工坊" (Creator Workshop / Feature Studio) module.

Features are user/Hy3-defined mini-assistants. Each feature bundles a system
prompt so that opening it launches a fully independent workspace. Favorites are
a per-deployment ordered list of feature ids. Everything is persisted to a single
JSON file under ``data/`` so it survives restarts with no external database.

Per the product spec (创造工坊方案.md), a feature carries rich metadata so the
Marketplace / My Features / Templates / Favorites views and the feature detail
page can render category, version, visibility, rating, usage, fork count, etc.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any, Optional

from .config import DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)
FEATURES_FILE = DATA_DIR / "features.json"
_LOCK = threading.Lock()

# 与方案 §5.1 Marketplace 分类对齐
CATEGORIES = [
    "Research",
    "Medical",
    "Education",
    "Writing",
    "Coding",
    "Office",
    "Translation",
    "Data Analysis",
    "Knowledge Management",
    "Others",
]
CATEGORY_LABELS = {
    "Research": "科研",
    "Medical": "医学",
    "Education": "教育",
    "Writing": "写作",
    "Coding": "编程",
    "Office": "办公",
    "Translation": "翻译",
    "Data Analysis": "数据分析",
    "Knowledge Management": "知识管理",
    "Others": "其他",
}
SYSTEM_CREATOR = "system"


def _now() -> str:
    return datetime.utcnow().isoformat()


def _load() -> dict:
    try:
        if FEATURES_FILE.exists():
            return json.loads(FEATURES_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {"features": [], "favorites": []}


def _save(data: dict) -> None:
    try:
        FEATURES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[features] write failed: {exc}")


_SEED_FEATURES = [
    {
        "id": "f_tpl_research_workspace",
        "name": "Research Workspace",
        "emoji": "📚",
        "description": "科研工作区：左侧文献列表，中央 PDF/内容阅读，右侧笔记与引用管理，支持证据高亮、大纲提取、引用插入。",
        "prompt": "你是一个科研工作区助手。用户上传或粘贴论文后，请协助：1) 提取论文大纲与核心贡献；2) 高亮关键方法与数据；3) 回答关于论文细节的问题；4) 帮助记录阅读笔记与引用。",
        "tags": ["科研", "文献阅读", "论文"],
        "category": "Research",
        "version": "2.0.0",
        "creator": SYSTEM_CREATOR,
        "created_at": "2026-01-01T00:00:00",
        "is_official": True,
        "is_template": True,
        "rating": 4.9,
        "rating_count": 328,
        "use_count": 12540,
        "forks": 892,
        "layout_type": "research",
        "ui": {
            "type": "workspace",
            "layout": "three-column",
            "panels": {
                "left": {"type": "paper-list", "title": "文献库", "width": "280px"},
                "center": {"type": "pdf-reader", "title": "阅读区"},
                "right": {"type": "notes-citations", "title": "笔记 & 引用", "width": "320px"}
            },
            "tools": ["upload", "search", "highlight", "cite", "outline", "export-notes"],
            "theme": {"accent": "#38e1c4", "bg": "#0d1117"}
        },
        "workflow": ["upload-paper", "extract-outline", "analyze-content", "generate-notes", "export"],
        "starters": ["上传一篇论文开始阅读", "帮我提取这篇论文的创新点", "总结这节的实验结果", "生成文献笔记"]
    },
    {
        "id": "f_tpl_review_workspace",
        "name": "Review Workspace",
        "emoji": "🔍",
        "description": "审稿工作区：按照顶会标准从创新性、方法严谨性、实验充分性、写作质量多维度评分，自动生成分条审稿意见与总结。",
        "prompt": "你是一位顶级会议审稿人。用户提交论文后，请从以下维度评审：1) 创新性与贡献；2) 方法严谨性与技术正确性；3) 实验充分性与结果可信度；4) 写作质量与清晰度。每个维度给出 1-10 分、详细评语、具体问题列表，最后给出总体评价与接收建议（Accept/Weak Accept/Borderline/Weak Reject/Reject）。",
        "tags": ["审稿", "评审", "论文"],
        "category": "Research",
        "version": "2.0.0",
        "creator": SYSTEM_CREATOR,
        "created_at": "2026-01-01T00:00:00",
        "is_official": True,
        "is_template": True,
        "rating": 4.8,
        "rating_count": 256,
        "use_count": 8920,
        "forks": 671,
        "layout_type": "review",
        "ui": {
            "type": "workspace",
            "layout": "review-split",
            "panels": {
                "top": {"type": "paper-upload", "title": "提交论文"},
                "left": {"type": "scoring-rubric", "title": "评分维度", "width": "340px"},
                "right": {"type": "review-output", "title": "审稿意见"}
            },
            "components": ["score-card", "issue-list", "summary-box", "decision-selector", "export-review"],
            "tools": ["upload", "score", "comment", "summarize", "export"],
            "theme": {"accent": "#f78fb3", "bg": "#0d1117"}
        },
        "workflow": ["upload-paper", "assess-novelty", "check-method", "evaluate-experiments", "check-writing", "generate-review"],
        "starters": ["上传论文开始审稿", "从创新性角度分析", "检查这篇论文的实验是否充分", "生成完整审稿意见"]
    },
    {
        "id": "f_tpl_meeting_assistant",
        "name": "Meeting Assistant",
        "emoji": "🎙️",
        "description": "会议助手：上传录音或文字记录，自动转写、提取讨论要点、识别决策项、生成待办行动项（含负责人与截止日期）。",
        "prompt": "你是一位专业的会议记录助手。用户提供录音转写或会议文字后，请输出：1) 会议主题与参会人；2) 按时间线整理的讨论要点；3) 达成的决策与共识；4) 行动项列表（包含任务、负责人、截止日期）；5) 遗留问题与下次会议建议。",
        "tags": ["会议", "纪要", "办公"],
        "category": "Office",
        "version": "1.3.0",
        "creator": SYSTEM_CREATOR,
        "created_at": "2026-01-01T00:00:00",
        "is_official": True,
        "is_template": True,
        "rating": 4.6,
        "rating_count": 412,
        "use_count": 15680,
        "forks": 534,
        "layout_type": "meeting",
        "ui": {
            "type": "workspace",
            "layout": "meeting-split",
            "panels": {
                "left": {"type": "transcript-panel", "title": "转写记录", "width": "45%"},
                "right": {"type": "summary-actions", "title": "纪要 & 行动项"}
            },
            "components": ["audio-upload", "transcript-view", "key-points", "decisions-box", "action-table", "export-docx"],
            "tools": ["transcribe", "summarize", "extract-actions", "assign", "export"],
            "theme": {"accent": "#4f8cff", "bg": "#0d1117"}
        },
        "workflow": ["upload-audio", "transcribe", "extract-points", "identify-decisions", "list-actions", "export"],
        "starters": ["上传会议录音/文字稿", "提取这场会议的行动项", "总结讨论要点", "生成会议纪要文档"]
    },
    {
        "id": "f_tpl_medical_report",
        "name": "Medical Report",
        "emoji": "🏥",
        "description": "医学报告助手：录入患者主诉、现病史、查体、检查检验结果，AI 辅助生成初步诊断、鉴别诊断、诊疗计划与处方建议。",
        "prompt": "你是一位资深临床医生助手。用户输入患者信息后，请按标准病历格式输出：1) 主诉（CC）；2) 现病史（HPI）；3) 既往史/个人史/家族史；4) 体格检查；5) 辅助检查；6) 初步诊断（按可能性排序）；7) 鉴别诊断；8) 诊疗计划；9) 处方建议（如适用）。注意：输出仅供参考，不构成医疗建议。",
        "tags": ["医学", "病历", "诊断"],
        "category": "Medical",
        "version": "1.2.0",
        "creator": SYSTEM_CREATOR,
        "created_at": "2026-01-01T00:00:00",
        "is_official": True,
        "is_template": True,
        "rating": 4.5,
        "rating_count": 178,
        "use_count": 7230,
        "forks": 389,
        "layout_type": "medical",
        "ui": {
            "type": "workspace",
            "layout": "medical-form",
            "panels": {
                "left": {"type": "patient-form", "title": "患者信息", "width": "380px"},
                "right": {"type": "report-output", "title": "病历报告"}
            },
            "components": ["patient-info", "symptom-input", "exam-fields", "lab-results", "diagnosis-list", "plan-box", "prescription", "disclaimer"],
            "tools": ["history", "diagnose", "differential", "plan", "prescribe"],
            "theme": {"accent": "#ff6b6b", "bg": "#0d1117"}
        },
        "workflow": ["collect-info", "history-taking", "physical-exam", "review-labs", "differential-diagnosis", "treatment-plan"],
        "starters": ["开始录入新患者", "根据症状给出初步鉴别诊断", "生成完整病历", "推荐诊疗方案"]
    },
]


_SEED_META = {f["id"]: f for f in _SEED_FEATURES}


def _ensure_seed(data: dict) -> list[dict]:
    migrated = False
    if not data.get("features"):
        seeded = []
        for f in _SEED_FEATURES:
            g = dict(f)
            g.setdefault("design_level", "simple")
            g.setdefault("ui", {"type": "chat"})
            g.setdefault("starters", [])
            g.setdefault("is_template", True)
            seeded.append(g)
        data["features"] = seeded
        migrated = True
    else:
        # 历史数据中官方模板可能缺少 category/version 等元数据，迁移补齐
        for f in data["features"]:
            if f.get("creator") == SYSTEM_CREATOR and f.get("id") in _SEED_META:
                meta = _SEED_META[f["id"]]
                for k in ("category", "version"):
                    if not f.get(k):
                        f[k] = meta[k]
                        migrated = True
                f.setdefault("is_template", True)
    if migrated:
        _save(data)
    return data["features"]


def _normalize(feat: dict) -> dict:
    """补齐历史数据中缺失的元数据字段，保证 Marketplace / 详情页渲染一致。"""
    feat.setdefault("design_level", "simple")
    feat.setdefault("ui", {"type": "chat"})
    feat.setdefault("starters", [])
    feat.setdefault("category", "Others")
    feat.setdefault("version", "1.0.0")
    feat.setdefault("visibility", "public")
    feat.setdefault("cover", "")
    feat.setdefault("rating", 0.0)
    feat.setdefault("rating_count", 0)
    feat.setdefault("forks", 0)
    feat.setdefault("use_count", 0)
    feat.setdefault("is_template", feat.get("creator") == SYSTEM_CREATOR)
    feat.setdefault("updated_at", feat.get("created_at", _now()))
    return feat


def _decorate(feat: dict, favs: set[str]) -> dict:
    _normalize(feat)
    return {**feat, "favorited": feat["id"] in favs}


# 拖拽式「初步设计」的离线兜底布局：逻辑固定，仅顺序可由用户拖拽调整
def heuristic_layout(desc: str) -> list[dict]:
    return [
        {"type": "textarea", "key": "input", "label": "你的输入 / 需求", "placeholder": "在此描述或粘贴内容…"},
        {"type": "select", "key": "tone", "label": "输出风格", "options": ["严谨", "通俗", "简洁", "详细"]},
        {"type": "chat", "key": "chat", "label": "与功能对话"},
        {"type": "output", "key": "output", "label": "结果区"},
    ]


def list_features(q: Optional[str] = None, category: Optional[str] = None,
                  scope: Optional[str] = None) -> list[dict]:
    with _LOCK:
        data = _load()
        feats = _ensure_seed(data)
        favs = set(data.get("favorites", []))
    # scope: discover | mine | templates （favorites 走 list_favorites）
    if scope == "mine":
        feats = [f for f in feats if f.get("creator") != SYSTEM_CREATOR]
    elif scope == "templates":
        feats = [f for f in feats if f.get("is_template")]
    if category and category not in ("", "All"):
        feats = [f for f in feats if _normalize(f).get("category") == category]
    if q:
        q = q.lower()
        hay = lambda f: (f.get("name", "") + " " + f.get("description", "") + " " +
                         " ".join(f.get("tags", [])) + " " + f.get("category", "")).lower()
        feats = [f for f in feats if q in hay(f)]
    return [_decorate(f, favs) for f in feats]


def list_favorites() -> list[dict]:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        favs = data.get("favorites", [])
        feats = [f for f in data.get("features", []) if f["id"] in set(favs)]
        # keep favorites order
        order = {fid: i for i, fid in enumerate(favs)}
        feats.sort(key=lambda f: order.get(f["id"], 999))
    return [_decorate(f, set(favs)) for f in feats]


def get_feature(fid: str) -> Optional[dict]:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        f = next((f for f in data.get("features", []) if f["id"] == fid), None)
        if not f:
            return None
        return _decorate(f, set(data.get("favorites", [])))


def create_feature(payload: dict) -> dict:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        rec = {
            "id": "f_" + uuid.uuid4().hex[:10],
            "name": (payload.get("name") or "").strip() or "未命名功能",
            "emoji": (payload.get("emoji") or "").strip() or "🧩",
            "description": (payload.get("description") or "").strip(),
            "prompt": (payload.get("prompt") or "").strip(),
            "tags": payload.get("tags", []) or [],
            "creator": payload.get("creator", "user"),
            "category": payload.get("category") or "Others",
            "version": payload.get("version") or "1.0.0",
            "visibility": payload.get("visibility") or "public",
            "cover": payload.get("cover") or "",
            "rating": 0.0,
            "rating_count": 0,
            "forks": 0,
            "design_level": payload.get("design_level", "simple"),
            "ui": payload.get("ui") or {"type": "chat"},
            "starters": payload.get("starters", []) or [],
            "is_template": bool(payload.get("is_template", False)),
            "created_at": _now(),
            "updated_at": _now(),
        }
        data.setdefault("features", []).insert(0, rec)
        _save(data)
    return rec


def update_feature(fid: str, payload: dict) -> Optional[dict]:
    """编辑功能：支持改名、改提示词、分类、版本号、可见性、布局等（方案 §5.2）。"""
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        for f in data.get("features", []):
            if f["id"] == fid:
                for k in ("name", "emoji", "description", "prompt", "tags", "category",
                          "version", "visibility", "cover", "design_level", "ui", "starters"):
                    if k in payload and payload[k] is not None:
                        f[k] = payload[k]
                f["updated_at"] = _now()
                _save(data)
                return _decorate(f, set(data.get("favorites", [])))
        return None


def toggle_favorite(fid: str) -> bool:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        favs = data.setdefault("favorites", [])
        if fid in favs:
            favs.remove(fid)
            state = False
        else:
            favs.insert(0, fid)
            state = True
        _save(data)
    return state


def delete_feature(fid: str) -> bool:
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        data["features"] = [f for f in data.get("features", []) if f["id"] != fid]
        data["favorites"] = [x for x in data.get("favorites", []) if x != fid]
        _save(data)
    return True


def incr_use(fid: str) -> None:
    with _LOCK:
        data = _load()
        for f in data.get("features", []):
            if f["id"] == fid:
                f["use_count"] = f.get("use_count", 0) + 1
                break
        else:
            return
        _save(data)


def fork_feature(fid: str) -> Optional[dict]:
    """Fork / Remix：复制他人（或官方）功能为「我的」副本（方案 §11）。"""
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        src = next((f for f in data.get("features", []) if f["id"] == fid), None)
        if not src:
            return None
        # 原始功能 fork 数 +1
        src["forks"] = src.get("forks", 0) + 1
        new_id = "f_" + uuid.uuid4().hex[:10]
        copy = dict(src)
        copy.update({
            "id": new_id,
            "name": src["name"] + "（副本）",
            "creator": "user",
            "is_template": False,
            "forks": 0,
            "rating": 0.0,
            "rating_count": 0,
            "use_count": 0,
            "created_at": _now(),
            "updated_at": _now(),
        })
        data.setdefault("features", []).insert(0, copy)
        _save(data)
    return _decorate(copy, set(data.get("favorites", [])))


def rate_feature(fid: str, stars: int) -> Optional[dict]:
    """用户评分（1-5），写回平均分与评分人数（方案 §10）。"""
    stars = max(1, min(5, int(stars)))
    with _LOCK:
        data = _load()
        _ensure_seed(data)
        for f in data.get("features", []):
            if f["id"] == fid:
                n = f.get("rating_count", 0)
                prev = f.get("rating", 0.0)
                f["rating"] = round((prev * n + stars) / (n + 1), 2)
                f["rating_count"] = n + 1
                _save(data)
                return _decorate(f, set(data.get("favorites", [])))
        return None


def heuristic_feature(description: str) -> dict:
    """Offline fallback when Hy3 is not configured: derive a usable feature with smart layout detection."""
    desc = description.strip()
    layout_type = _infer_layout(desc)
    return {
        "name": desc[:24] if len(desc) <= 24 else desc[:22] + "…",
        "emoji": _layout_emoji(layout_type),
        "description": desc,
        "prompt": f"你是一个由用户自定义的专业助手。你的核心任务是：{desc}。请基于用户输入给出专业、准确、有帮助的回答，必要时分点说明。",
        "tags": ["自定义"],
        "category": _layout_category(layout_type),
        "layout_type": layout_type,
        "version": "1.0.0",
        "visibility": "public",
        "design_level": "simple",
        "ui": _layout_ui(layout_type),
        "workflow": _layout_workflow(layout_type),
        "starters": _layout_starters(layout_type, desc),
    }


def _infer_layout(desc: str) -> str:
    """根据描述关键词智能推断布局类型"""
    d = desc.lower()
    if any(k in d for k in ["论文", "文献", "pdf", "阅读", "research", "paper", "笔记"]):
        return "research"
    if any(k in d for k in ["审稿", "评审", "review", "评分", "评估"]):
        return "review"
    if any(k in d for k in ["实验", "experiment", "设计方案", "实验设计"]):
        return "experiment"
    if any(k in d for k in ["会议", "纪要", "meeting", "录音", "转写", "待办"]):
        return "meeting"
    if any(k in d for k in ["医学", "病历", "医疗", "诊断", "患者", "临床", "medical"]):
        return "medical"
    if any(k in d for k in ["代码", "编程", "code", "debug", "开发", "ide"]):
        return "coding"
    return "chat"


def _layout_emoji(layout_type: str) -> str:
    return {
        "research": "📚", "review": "🔍", "experiment": "🧪",
        "meeting": "🎙️", "medical": "🏥", "coding": "💻", "chat": "🧩",
    }.get(layout_type, "🧩")


def _layout_category(layout_type: str) -> str:
    return {
        "research": "Research", "review": "Research", "experiment": "Research",
        "meeting": "Office", "medical": "Medical", "coding": "Coding", "chat": "Others",
    }.get(layout_type, "Others")


def _layout_ui(layout_type: str) -> dict:
    layouts = {
        "research": {"type": "workspace", "layout": "three-column", "panels": {
            "left": {"type": "paper-list", "title": "文献库", "width": "280px"},
            "center": {"type": "pdf-reader", "title": "阅读区"},
            "right": {"type": "notes-citations", "title": "笔记 & 引用", "width": "320px"}
        }, "tools": ["upload", "search", "highlight", "cite", "outline", "export-notes"]},
        "review": {"type": "workspace", "layout": "review", "panels": {
            "top": {"type": "upload-header", "title": "论文上传"},
            "left": {"type": "paper-content", "title": "论文内容"},
            "right": {"type": "review-form", "title": "审稿评分表"}
        }, "tools": ["upload", "score", "evidence", "generate-report"]},
        "experiment": {"type": "workspace", "layout": "three-col-experiment", "panels": {
            "left": {"type": "hypothesis", "title": "假设 & 变量"},
            "center": {"type": "workflow", "title": "实验流程"},
            "right": {"type": "analysis", "title": "分析方案"}
        }, "tools": ["design", "gantt", "confounds", "export"]},
        "meeting": {"type": "workspace", "layout": "two-col-meeting", "panels": {
            "left": {"type": "transcript", "title": "转写记录"},
            "right": {"type": "summary", "title": "会议纪要"}
        }, "tools": ["upload-audio", "paste-text", "extract", "todos"]},
        "medical": {"type": "workspace", "layout": "two-col-medical", "panels": {
            "left": {"type": "patient-form", "title": "患者信息"},
            "right": {"type": "report", "title": "病历报告"}
        }, "tools": ["history", "exam", "tests", "diagnosis", "plan", "disclaimer"]},
        "coding": {"type": "workspace", "layout": "ide", "panels": {
            "sidebar": {"type": "file-tree", "title": "文件", "width": "240px"},
            "main": {"type": "editor", "title": "代码编辑器"},
            "bottom": {"type": "terminal", "title": "终端", "height": "200px"},
            "right": {"type": "ai-assistant", "title": "AI助手", "width": "320px"}
        }, "tools": ["run", "debug", "explain", "refactor", "test"]},
        "chat": {"type": "chat"},
    }
    return layouts.get(layout_type, layouts["chat"])


def _layout_workflow(layout_type: str) -> list[str]:
    workflows = {
        "research": ["upload-paper", "extract-outline", "analyze-content", "generate-notes", "export"],
        "review": ["upload-paper", "assess-novelty", "assess-method", "assess-experiments", "assess-writing", "generate-review"],
        "experiment": ["define-hypothesis", "identify-variables", "design-procedure", "plan-analysis", "check-confounds", "generate-plan"],
        "meeting": ["receive-transcript", "extract-points", "identify-decisions", "list-todos", "generate-summary"],
        "medical": ["collect-history", "physical-exam", "review-tests", "differential-diagnosis", "treatment-plan", "add-disclaimer"],
        "coding": ["analyze-code", "identify-issues", "suggest-fixes", "explain-logic", "generate-code"],
        "chat": ["understand-query", "analyze", "generate-response"],
    }
    return workflows.get(layout_type, workflows["chat"])


def _layout_starters(layout_type: str, desc: str) -> list[str]:
    defaults = {
        "research": ["上传一篇论文开始阅读", "帮我提取这篇论文的创新点", "总结这节的实验结果"],
        "review": ["上传一篇论文进行审稿", "从创新性维度评估这篇论文", "给出完整审稿意见"],
        "experiment": ["帮我设计一个实验方案", "分析这个实验的混淆因素", "生成实验时间表"],
        "meeting": ["粘贴一段会议记录", "提取会议中的决策事项", "列出待办行动项"],
        "medical": ["帮我生成一份病历", "分析可能的鉴别诊断", "给出诊疗计划建议"],
        "coding": ["帮我review这段代码", "解释这个函数的作用", "帮我修复这个bug"],
        "chat": [f"帮我处理：{desc[:20]}", "给我一个示例", "有什么注意事项？"],
    }
    return defaults.get(layout_type, defaults["chat"])


def heuristic_design(desc: str, transcript: str) -> dict:
    """Offline fallback for the 初步设计 level: returns a structured feature with layout."""
    return {
        "name": desc[:18] if len(desc) <= 18 else desc[:16] + "…",
        "emoji": "🧩",
        "description": desc,
        "prompt": f"你是一个由用户自定义的专业助手。你的核心任务是：{desc}。请结合用户提供的各项输入，给出专业、准确、有帮助的结果。",
        "tags": ["自定义", "拖拽设计"],
        "category": "Others",
        "version": "1.0.0",
        "visibility": "public",
        "design_level": "builder",
        "ui": {"type": "builder", "layout": heuristic_layout(desc)},
        "starters": [],
    }
