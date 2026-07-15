"""Offline unit tests — no API key / network required.

Run:  python -m tests.test_offline   (or: pytest tests/test_offline.py)
Validates the deterministic building blocks: JSON extraction, citation parsing,
data models, and prompt construction.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:  # ensure UTF-8 output on Windows GBK consoles
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.hy3_client import _extract_json  # noqa: E402
from backend.models import ResearchRequest, TaskType  # noqa: E402
from backend import prompts  # noqa: E402
from backend.pipeline import _CITATION_RE  # noqa: E402


def test_extract_json_direct():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    text = 'here is the plan:\n```json\n{"a": [1, 2]}\n```\nthanks'
    assert _extract_json(text) == {"a": [1, 2]}


def test_extract_json_embedded():
    text = 'sure! {"goal": "x", "list": [1,2,3]} done'
    assert _extract_json(text)["goal"] == "x"


def test_citation_regex():
    content = "结论A [s1][s3]，结论B [s12]。"
    assert _CITATION_RE.findall(content) == ["s1", "s3", "s12"]


def test_models_defaults():
    req = ResearchRequest(query="长上下文压缩")
    assert req.task_type == TaskType.literature_review
    assert req.language.value == "zh"


def test_planner_prompt_shape():
    req = ResearchRequest(query="RAG 压缩", focus="更关注局限")
    msgs = prompts.planner_prompt(req)
    assert msgs[0]["role"] == "system"
    assert "RAG 压缩" in msgs[1]["content"]
    assert "更关注局限" in msgs[1]["content"]


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")
    return passed == len(tests)


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
