"""数据集加载：任务文件 + split 定义 + held-out 答案锚点。

目录约定（相对 DATA_ROOT = ScholarBench/data）：
    data/v0.1/T1_survey.jsonl ...
    data/v0.1/adversarial.jsonl
    data/splits/{lite,full,hard}.json      # {"T1": ["T1-001", ...], ...}
    data/keys_heldout/<family>.json        # {"T1-001": {...}, ...}  ← 不公开
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import FAMILIES, Task, load_tasks, read_jsonl

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
VERSION = "v0.1"

SUITE_FILES = {
    "T1": "T1_survey.jsonl",
    "T2": "T2_proposal.jsonl",
    "T3": "T3_search.jsonl",
    "T4": "T4_paperqa.jsonl",
    "T5": "T5_citation.jsonl",
    "T6": "T6_writing.jsonl",
    "T7": "T7_advisor.jsonl",
    "T8": "T8_workflow.jsonl",
}


def version_dir(version: str = VERSION) -> Path:
    return DATA_ROOT / version


def suite_path(family: str, version: str = VERSION) -> Path:
    return version_dir(version) / SUITE_FILES[family]


def existing_families(version: str = VERSION) -> list[str]:
    return [f for f in SUITE_FILES if suite_path(f, version).exists()]


def load_family(family: str, version: str = VERSION) -> list[Task]:
    p = suite_path(family, version)
    return load_tasks(p) if p.exists() else []


def load_all(families: Iterable[str] | None = None, version: str = VERSION) -> list[Task]:
    fams = list(families) if families else existing_families(version)
    tasks: list[Task] = []
    for f in fams:
        tasks += load_family(f, version)
    return tasks


def load_adversarial(version: str = VERSION) -> list[Task]:
    p = version_dir(version) / "adversarial.jsonl"
    return load_tasks(p) if p.exists() else []


# --- splits ----------------------------------------------------------------
def load_split(name: str, version: str = VERSION) -> list[Task]:
    """按 split 定义加载（lite / full / hard）。split 文件缺失时按 lite 规则自动取样。"""
    all_tasks = load_all(version=version)
    spath = DATA_ROOT / "splits" / f"{name}.json"
    if not spath.exists():
        return _auto_split(all_tasks, name)
    wanted = json.loads(spath.read_text(encoding="utf-8"))
    ids = set()
    for v in wanted.values():
        ids.update(v if isinstance(v, list) else [])
    picked = [t for t in all_tasks if t.task_id in ids]
    return picked or _auto_split(all_tasks, name)


def _auto_split(tasks: list[Task], name: str) -> list[Task]:
    by_fam: dict[str, list[Task]] = {}
    for t in tasks:
        by_fam.setdefault(t.family, []).append(t)
    per = {"lite": 8, "hard": 6}.get(name, 10 ** 6)
    out: list[Task] = []
    for fam in sorted(by_fam):
        group = by_fam[fam]
        if name == "hard":
            group = [t for t in group if t.difficulty == "hard"] or group
        out += group[:per]
    return out


# --- held-out 答案锚点 -----------------------------------------------------
def load_keys(families: Iterable[str] | None = None, version: str = VERSION) -> dict:
    keys: dict = {}
    fams = list(families) if families else list(SUITE_FILES)
    for f in fams:
        p = version_dir(version) / "keys_heldout" / f"{f}.json"
        if p.exists():
            keys.update(json.loads(p.read_text(encoding="utf-8")))
        p2 = version_dir(version) / f"{f}_keys.json"
        if p2.exists():
            keys.update(json.loads(p2.read_text(encoding="utf-8")))
    return keys


def dataset_stats(version: str = VERSION) -> dict:
    stats = {"version": version, "families": {}}
    total = 0
    for f, fname in SUITE_FILES.items():
        tasks = load_family(f, version)
        if not tasks:
            continue
        diff = {}
        for t in tasks:
            diff[t.difficulty] = diff.get(t.difficulty, 0) + 1
        stats["families"][f"{f} {FAMILIES[f]}"] = {"count": len(tasks), "difficulty": diff}
        total += len(tasks)
    stats["total"] = total
    adv = load_adversarial(version)
    stats["adversarial"] = len(adv)
    return stats
