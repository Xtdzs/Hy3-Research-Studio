"""Persistence + in-memory caches for tasks, uploads, library and settings.

Tasks / library / settings are persisted to JSON files under ``data/`` so the
app keeps working across restarts without any external database. The store
interface stays intentionally tiny so it can be swapped for a real DB later.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Optional

from .config import DATA_DIR
from .models import ResearchTask

DATA_DIR.mkdir(parents=True, exist_ok=True)
TASKS_FILE = DATA_DIR / "tasks.json"
LIB_FILE = DATA_DIR / "library.json"
FOLDER_FILE = DATA_DIR / "folders.json"
SET_FILE = DATA_DIR / "settings.json"
STUDIO_HISTORY_FILE = DATA_DIR / "studio_history.json"
PAPER_HISTORY_FILE = DATA_DIR / "paper_history.json"
ADVISOR_HISTORY_FILE = DATA_DIR / "advisor_history.json"
TASK_CAP = 100


def _load_json(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return default


def _save_json(path, data) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        print(f"[store] failed to write {path}: {exc}")


@dataclass
class UploadedDoc:
    upload_id: str
    filename: str
    text: str


@dataclass
class PaperDoc:
    paper_id: str
    filename: str
    text: str


class MemoryStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ResearchTask] = {}
        self._uploads: dict[str, UploadedDoc] = {}
        self._papers: dict[str, PaperDoc] = {}
        self._search_history: list[dict] = []
        self._sugg_cache: tuple = (None, None)  # (key, payload)
        self._library: list[dict] = _load_json(LIB_FILE, [])
        self._folders: list[dict] = _load_json(FOLDER_FILE, [])
        self._settings: dict = _load_json(SET_FILE, {})
        self._studio_history: list[dict] = _load_json(STUDIO_HISTORY_FILE, [])
        self._paper_history: list[dict] = _load_json(PAPER_HISTORY_FILE, [])
        self._advisor_history: list[dict] = _load_json(ADVISOR_HISTORY_FILE, [])
        # restore persisted tasks
        for t in _load_json(TASKS_FILE, []):
            try:
                self._tasks[t["task_id"]] = ResearchTask(**t)
            except Exception:  # noqa: BLE001
                continue
        self._lock = threading.Lock()

    # --- tasks --------------------------------------------------------------
    def save_task(self, task: ResearchTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            arr = [
                t.model_dump(mode="json")
                for t in sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True)
            ][:TASK_CAP]
            _save_json(TASKS_FILE, arr)

    def get_task(self, task_id: str) -> Optional[ResearchTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[ResearchTask]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    # --- uploads ------------------------------------------------------------
    def save_upload(self, doc: UploadedDoc) -> None:
        with self._lock:
            self._uploads[doc.upload_id] = doc

    def get_upload(self, upload_id: str) -> Optional[UploadedDoc]:
        return self._uploads.get(upload_id)

    # --- library ------------------------------------------------------------
    def list_library(self) -> list[dict]:
        return self._library

    def add_library(self, item: dict) -> None:
        with self._lock:
            self._library = [x for x in self._library if x.get("saved_id") != item.get("saved_id")]
            self._library.insert(0, item)
            _save_json(LIB_FILE, self._library)

    def remove_library(self, saved_id: str) -> None:
        with self._lock:
            self._library = [x for x in self._library if x.get("saved_id") != saved_id]
            _save_json(LIB_FILE, self._library)

    # --- library folders --------------------------------------------------
    def list_folders(self) -> list[dict]:
        return self._folders

    def add_folder(self, name: str, parent_id: str = "") -> Optional[dict]:
        name = (name or "").strip()
        if not name:
            return None
        parent_id = parent_id or ""
        # parent 必须存在（或为根），避免产生悬空/环路
        if parent_id and not any(f.get("id") == parent_id for f in self._folders):
            parent_id = ""
        with self._lock:
            existing = next(
                (f for f in self._folders
                 if f.get("name") == name and (f.get("parent_id", "") or "") == parent_id),
                None,
            )
            if existing:
                return existing
            fid = "f_" + hashlib.md5((name.lower() + "|" + parent_id).encode()).hexdigest()[:10]
            rec = {"id": fid, "name": name, "parent_id": parent_id}
            self._folders.append(rec)
            _save_json(FOLDER_FILE, self._folders)
            return rec

    def rename_folder(self, fid: str, name: str) -> bool:
        name = (name or "").strip()
        if not name:
            return False
        with self._lock:
            for f in self._folders:
                if f.get("id") == fid:
                    f["name"] = name
                    _save_json(FOLDER_FILE, self._folders)
                    return True
        return False

    def remove_folder(self, fid: str) -> bool:
        with self._lock:
            by_id = {f.get("id"): f for f in self._folders}
            if fid not in by_id:
                return False
            # 收集整棵子树（含子文件夹）
            to_remove = set()
            stack = [fid]
            while stack:
                cur = stack.pop()
                to_remove.add(cur)
                for f in self._folders:
                    if (f.get("parent_id", "") or "") == cur and f.get("id") not in to_remove:
                        stack.append(f.get("id"))
            before = len(self._folders)
            self._folders = [f for f in self._folders if f.get("id") not in to_remove]
            changed = len(self._folders) != before
            if changed:
                # 子树内所有文献移回「未分类」
                self._library = [
                    {**x, "folder": ""} if x.get("folder") in to_remove else x
                    for x in self._library
                ]
                _save_json(FOLDER_FILE, self._folders)
                _save_json(LIB_FILE, self._library)
            return changed

    def move_library(self, ids: list, folder: str) -> int:
        ids = set(ids or [])
        n = 0
        with self._lock:
            for x in self._library:
                if x.get("saved_id") in ids:
                    x["folder"] = folder or ""
                    n += 1
            if n:
                _save_json(LIB_FILE, self._library)
        return n

    # --- settings -----------------------------------------------------------
    def get_settings(self) -> dict:
        return self._settings

    def save_settings(self, settings_obj: dict) -> None:
        with self._lock:
            self._settings = settings_obj
            _save_json(SET_FILE, settings_obj)

    # --- papers (PDF discussion) --------------------------------------------
    def save_paper(self, doc: PaperDoc) -> None:
        with self._lock:
            self._papers[doc.paper_id] = doc

    def get_paper(self, paper_id: str) -> Optional[PaperDoc]:
        return self._papers.get(paper_id)

    # --- search history (for "猜你想搜") ------------------------------------
    def add_search_history(self, query: str, kind: str) -> None:
        query = (query or "").strip()
        if not query:
            return
        with self._lock:
            self._search_history.append({
                "query": query,
                "kind": kind,  # research | search | smart
                "ts": datetime.datetime.utcnow().isoformat(),
            })
            # keep last 200
            if len(self._search_history) > 200:
                self._search_history = self._search_history[-200:]

    def get_search_history(self) -> list[dict]:
        return list(reversed(self._search_history))

    # --- suggestions cache ---------------------------------------------------
    def cache_suggestions(self, key: str, payload: dict) -> None:
        with self._lock:
            self._sugg_cache = (key, payload)

    def get_cached_suggestions(self, key: str) -> Optional[dict]:
        with self._lock:
            return self._sugg_cache[1] if self._sugg_cache[0] == key else None

    # --- writing-studio history ----------------------------------------------
    def add_studio_history(self, topic: str, tool: str, snippet: str) -> None:
        with self._lock:
            self._studio_history.insert(0, {
                "topic": topic,
                "tool": tool,
                "snippet": (snippet or "")[:400],
                "ts": datetime.datetime.utcnow().isoformat(),
            })
            self._studio_history = self._studio_history[:200]
            _save_json(STUDIO_HISTORY_FILE, self._studio_history)

    # --- paper discussion history --------------------------------------------
    def add_paper_history(self, paper_id: str, filename: str, transcript: list[dict]) -> None:
        with self._lock:
            # 每个论文只保留最新一条会话记录
            self._paper_history = [h for h in self._paper_history if h.get("paper_id") != paper_id]
            self._paper_history.insert(0, {
                "paper_id": paper_id,
                "filename": filename,
                "transcript": (transcript or [])[-24:],  # 保留最近 24 轮
                "ts": datetime.datetime.utcnow().isoformat(),
            })
            self._paper_history = self._paper_history[:100]
            _save_json(PAPER_HISTORY_FILE, self._paper_history)

    def get_paper_history(self, paper_id: str) -> Optional[dict]:
        return next((h for h in self._paper_history if h.get("paper_id") == paper_id), None)

    def delete_paper_history(self, paper_id: str) -> bool:
        with self._lock:
            before = len(self._paper_history)
            self._paper_history = [h for h in self._paper_history if h.get("paper_id") != paper_id]
            changed = len(self._paper_history) != before
            if changed:
                _save_json(PAPER_HISTORY_FILE, self._paper_history)
            return changed

    # --- idea-refiner (思路提炼) history ------------------------------------
    def add_advisor_history(self, advisor_id: str, topic: str, transcript: list[dict]) -> None:
        advisor_id = (advisor_id or "").strip()
        if not advisor_id:
            return
        with self._lock:
            # 同一会话只保留最新一条（支持从历史点回继续推演）
            self._advisor_history = [h for h in self._advisor_history if h.get("advisor_id") != advisor_id]
            self._advisor_history.insert(0, {
                "advisor_id": advisor_id,
                "topic": (topic or "思路提炼")[:200],
                "transcript": (transcript or [])[-40:],
                "ts": datetime.datetime.utcnow().isoformat(),
            })
            self._advisor_history = self._advisor_history[:100]
            _save_json(ADVISOR_HISTORY_FILE, self._advisor_history)

    # --- unified history delete (批量删除研究历史) ----------------------------
    def delete_unified_history(self, items: list) -> int:
        """按 {kind, id, ts, query, paper_id, tool} 标识删除若干条历史记录。
        匹配字段因模块而异：research 用 id(task_id)；search/smart 用 kind+query+ts；
        studio 用 tool+ts；paper 用 paper_id。返回实际删除条数。"""
        removed = 0
        with self._lock:
            for item in (items or []):
                kind = item.get("kind")
                if kind == "research":
                    tid = item.get("id")
                    if tid and tid in self._tasks:
                        del self._tasks[tid]
                        removed += 1
                elif kind in ("search", "smart"):
                    before = len(self._search_history)
                    self._search_history = [
                        h for h in self._search_history
                        if not (h.get("kind") == kind and h.get("ts") == item.get("ts")
                                and h.get("query") == item.get("query"))
                    ]
                    removed += before - len(self._search_history)
                elif kind == "studio":
                    before = len(self._studio_history)
                    self._studio_history = [
                        h for h in self._studio_history
                        if not (h.get("ts") == item.get("ts") and h.get("tool") == item.get("tool"))
                    ]
                    removed += before - len(self._studio_history)
                elif kind == "paper":
                    pid = item.get("paper_id") or item.get("id")
                    if pid:
                        before = len(self._paper_history)
                        self._paper_history = [h for h in self._paper_history if h.get("paper_id") != pid]
                        removed += before - len(self._paper_history)
                elif kind == "advisor":
                    aid = item.get("advisor_id") or item.get("id")
                    if aid:
                        before = len(self._advisor_history)
                        self._advisor_history = [h for h in self._advisor_history if h.get("advisor_id") != aid]
                        removed += before - len(self._advisor_history)
            # 持久化被改动的存储
            if any(it.get("kind") == "research" for it in (items or [])):
                arr = [t.model_dump(mode="json") for t in
                       sorted(self._tasks.values(), key=lambda x: x.created_at, reverse=True)][:TASK_CAP]
                _save_json(TASKS_FILE, arr)
            if any(it.get("kind") == "studio" for it in (items or [])):
                _save_json(STUDIO_HISTORY_FILE, self._studio_history)
            if any(it.get("kind") == "paper" for it in (items or [])):
                _save_json(PAPER_HISTORY_FILE, self._paper_history)
            if any(it.get("kind") == "advisor" for it in (items or [])):
                _save_json(ADVISOR_HISTORY_FILE, self._advisor_history)
        return removed

    # --- unified history across the 4 modules --------------------------------
    _TASK_TYPE_LABELS = {
        "literature_review": "文献综述",
        "tech_survey": "技术调研",
        "proposal": "开题汇报",
        "plan_report": "项目方案",
    }
    _SEARCH_LABELS = {"search": "文献检索", "smart": "智能检索", "research": "深度研究"}

    def list_unified_history(self) -> list[dict]:
        items: list[dict] = []
        for t in self.list_tasks():
            items.append({
                "kind": "research",
                "id": t.task_id,
                "title": t.request.query,
                "sub": f"{self._TASK_TYPE_LABELS.get(t.request.task_type, t.request.task_type)} · {t.status} · {len(t.sections)} 章",
                "ts": t.created_at.isoformat() if isinstance(t.created_at, datetime.datetime) else str(t.created_at),
            })
        # 文献检索 / 智能检索（research 类型已在 tasks 中体现，避免重复）
        for h in self._search_history:
            if h.get("kind") == "research":
                continue
            items.append({
                "kind": h["kind"],
                "id": None,
                "title": h["query"],
                "sub": self._SEARCH_LABELS.get(h["kind"], h["kind"]),
                "ts": h["ts"],
                "query": h["query"],
            })
        for h in self._studio_history:
            items.append({
                "kind": "studio", "id": None, "title": h["topic"],
                "sub": f"写作助手 · {h['tool']}",
                "ts": h["ts"], "snippet": h["snippet"], "tool": h["tool"],
            })
        for h in self._paper_history:
            items.append({
                "kind": "paper", "id": None, "title": h["filename"],
                "sub": f"论文研讨 · {len(h['transcript'])} 轮",
                "ts": h["ts"], "paper_id": h["paper_id"], "transcript": h["transcript"],
            })
        for h in self._advisor_history:
            turns = len([t for t in h.get("transcript", []) if t.get("role") == "user"])
            items.append({
                "kind": "advisor", "id": None, "title": h["topic"],
                "sub": f"思路提炼 · {turns} 轮",
                "ts": h["ts"], "advisor_id": h["advisor_id"], "transcript": h["transcript"],
            })
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items


store = MemoryStore()
