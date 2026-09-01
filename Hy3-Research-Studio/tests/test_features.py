"""Functional & regression tests for the 创造工坊 (Feature Studio) module.

Run:  python -m tests.test_features
Covers: routing order (favorites must not be shadowed), list scopes, category
filter, search, get/create/fork/rate/update/favorite/delete, and the missing
`/use` endpoint. Data is isolated into a temp dir so the real data file is
never touched.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

try:  # ensure UTF-8 output on Windows GBK consoles
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import backend.features as feature_store  # noqa: E402

# --- isolate persistence into a temp dir before importing the app -------------
_TMP = Path(tempfile.mkdtemp(prefix="feat_test_"))
feature_store.DATA_DIR = _TMP
feature_store.FEATURES_FILE = _TMP / "features.json"

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)

SEED_IDS = [
    "f_tpl_research_workspace",
    "f_tpl_review_workspace",
    "f_tpl_meeting_assistant",
    "f_tpl_medical_report",
]


# --- helpers ------------------------------------------------------------------
def _get_json(url, **kw):
    r = client.get(url, **kw)
    return r.status_code, r.json()


def _post_json(url, body=None, **kw):
    r = client.post(url, json=body or {}, **kw)
    return r.status_code, r.json()


def _put_json(url, body=None, **kw):
    r = client.put(url, json=body or {}, **kw)
    return r.status_code, r.json()


# --- route ordering / discover ------------------------------------------------
def test_favorites_route_not_shadowed():
    # /api/features/favorites must NOT be captured by /api/features/{fid}
    code, data = _get_json("/api/features/favorites")
    assert code == 200, data
    assert "features" in data


def test_list_discover_returns_seeds():
    code, data = _get_json("/api/features?scope=discover")
    assert code == 200
    feats = data["features"]
    assert len(feats) == 4
    assert all(f["creator"] == "system" for f in feats)


def test_list_mine_empty_initially():
    code, data = _get_json("/api/features?scope=mine")
    assert code == 200
    assert data["features"] == []


def test_list_templates():
    code, data = _get_json("/api/features?scope=templates")
    assert code == 200
    assert len(data["features"]) == 4
    assert all(f.get("is_template") for f in data["features"])


def test_category_filter():
    code, data = _get_json("/api/features?scope=discover&category=Research")
    assert code == 200
    assert len(data["features"]) == 2
    assert all(f["category"] == "Research" for f in data["features"])


def test_search_query():
    code, data = _get_json("/api/features?scope=discover&q=meeting")
    assert code == 200
    names = [f["name"] for f in data["features"]]
    assert any("Meeting" in n for n in names)


# --- get / 404 ----------------------------------------------------------------
def test_get_feature_ok():
    code, data = _get_json(f"/api/features/{SEED_IDS[0]}")
    assert code == 200
    assert data["feature"]["id"] == SEED_IDS[0]


def test_get_feature_404():
    code, _ = _get_json("/api/features/does_not_exist")
    assert code == 404


# --- create / mine / delete ---------------------------------------------------
def test_create_and_mine():
    body = {"name": "我的测试功能", "description": "一个测试", "prompt": "你是测试助手",
            "category": "Coding", "creator": "user"}
    code, data = _post_json("/api/features", body)
    assert code == 200
    fid = data["feature"]["id"]
    assert data["feature"]["creator"] == "user"
    code2, data2 = _get_json("/api/features?scope=mine")
    assert code2 == 200
    assert any(f["id"] == fid for f in data2["features"])
    # cleanup
    client.delete(f"/api/features/{fid}")


def test_delete_feature():
    body = {"name": "待删除", "description": "x", "prompt": "p", "creator": "user"}
    _, data = _post_json("/api/features", body)
    fid = data["feature"]["id"]
    code, _ = client.delete(f"/api/features/{fid}").status_code, None
    r = client.get(f"/api/features/{fid}")
    assert r.status_code == 404


# --- fork ---------------------------------------------------------------------
def test_fork_increments_and_copies():
    before = _get_json(f"/api/features/{SEED_IDS[0]}")[1]["feature"]["forks"]
    code, data = _post_json(f"/api/features/{SEED_IDS[0]}/fork")
    assert code == 200
    new_f = data["feature"]
    assert new_f["creator"] == "user"
    assert "副本" in new_f["name"]
    assert new_f["forks"] == 0
    after = _get_json(f"/api/features/{SEED_IDS[0]}")[1]["feature"]["forks"]
    assert after == before + 1
    # forked copy appears in "mine"
    mine = _get_json("/api/features?scope=mine")[1]["features"]
    assert any(f["id"] == new_f["id"] for f in mine)
    client.delete(f"/api/features/{new_f['id']}")


def test_fork_missing():
    code, _ = _post_json("/api/features/nope/fork")
    assert code == 404


# --- rate ---------------------------------------------------------------------
def test_rate_average():
    body = {"name": "评分测试", "description": "x", "prompt": "p", "creator": "user"}
    _, data = _post_json("/api/features", body)
    fid = data["feature"]["id"]
    # rate 4 then 2 -> average 3.0, count 2
    _post_json(f"/api/features/{fid}/rate", {"stars": 4})
    code, d2 = _post_json(f"/api/features/{fid}/rate", {"stars": 2})
    assert code == 200
    assert d2["feature"]["rating_count"] == 2
    assert d2["feature"]["rating"] == 3.0
    client.delete(f"/api/features/{fid}")


# --- update -------------------------------------------------------------------
def test_rate_bad_input_safe():
    body = {"name": "评分健壮性", "description": "x", "prompt": "p", "creator": "user"}
    _, data = _post_json("/api/features", body)
    fid = data["feature"]["id"]
    # non-numeric stars must not 500; clamped to a valid 1..5 then averaged
    code, d = _post_json(f"/api/features/{fid}/rate", {"stars": "abc"})
    assert code == 200
    assert 1 <= d["feature"]["rating"] <= 5
    client.delete(f"/api/features/{fid}")


def test_update_feature():
    body = {"name": "编辑前", "description": "x", "prompt": "p", "creator": "user"}
    _, data = _post_json("/api/features", body)
    fid = data["feature"]["id"]
    code, d2 = _put_json(f"/api/features/{fid}", {"name": "编辑后", "category": "Writing"})
    assert code == 200
    assert d2["feature"]["name"] == "编辑后"
    assert d2["feature"]["category"] == "Writing"
    client.delete(f"/api/features/{fid}")


# --- favorite -----------------------------------------------------------------
def test_toggle_favorite():
    fid = SEED_IDS[1]
    code, d = _post_json("/api/features/favorite", {"id": fid})
    assert code == 200
    assert d["favorited"] is True
    favs = _get_json("/api/features/favorites")[1]["features"]
    assert any(f["id"] == fid for f in favs)
    # toggle off
    code2, d2 = _post_json("/api/features/favorite", {"id": fid})
    assert code2 == 200
    assert d2["favorited"] is False
    favs2 = _get_json("/api/features/favorites")[1]["features"]
    assert all(f["id"] != fid for f in favs2)


# --- generate (offline fallback, no network) ----------------------------------
def test_generate_offline_fallback():
    # force offline path so the test is deterministic & fast (is_configured is read-only)
    import backend.main as main_mod
    class _OfflineSettings:
        is_configured = False
        model = "offline"
        base_url = ""

    saved = main_mod.settings
    main_mod.settings = _OfflineSettings()
    try:
        code, data = _post_json("/api/features/generate", {"description": "帮我审稿"})
        assert code == 200
        f = data["feature"]
        assert f["name"]
        assert f["prompt"]
        assert f["category"]
    finally:
        main_mod.settings = saved


# --- /use endpoint (regression: used to 404) ----------------------------------
def test_use_endpoint_increments():
    fid = SEED_IDS[2]
    before = _get_json(f"/api/features/{fid}")[1]["feature"]["use_count"]
    code, _ = _post_json(f"/api/features/{fid}/use")
    assert code == 200, "expected /api/features/{id}/use to exist"
    after = _get_json(f"/api/features/{fid}")[1]["feature"]["use_count"]
    assert after == before + 1


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    passed = 0
    fails = []
    for t in tests:
        try:
            t()
            print(f"  \u2713 {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  \u2717 {t.__name__}: {e}")
            fails.append(t.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"  \u2717 {t.__name__} raised {type(e).__name__}: {e}")
            fails.append(t.__name__)
    print(f"\n{passed}/{len(tests)} passed")
    if fails:
        print("FAILED:", ", ".join(fails))
    return passed == len(tests)


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
