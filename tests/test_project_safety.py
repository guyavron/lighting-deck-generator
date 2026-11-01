"""הגנה על עבודה שמורה (D-036).

בדיקת השמישות (13.10) איבדה מצגת של 111 שקופיות בשלוש דרכים שונות.
כל בדיקה כאן נועלת אחת מהן.
"""
import asyncio
import json
import os

import pytest


class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return json.loads(json.dumps(self._b))


@pytest.fixture
def srv(tmp_path, monkeypatch):
    import server as SRV
    monkeypatch.setattr(SRV, "PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(SRV, "HISTORY_DIR", str(tmp_path / "projects" / "history"))
    return SRV


def _put(srv, body):
    r = asyncio.run(srv.project_put(_Req(body)))
    if hasattr(r, "status_code"):
        return r.status_code, json.loads(r.body)
    return 200, r


def _state(n_slides, title="x"):
    return {"drawing": "d.dxf", "layers": [], "layer_styles": {},
            "areas": [{"name": "א", "slides": [{"title": title}] * n_slides}]}


def test_every_save_gets_a_new_version(srv):
    code, r = _put(srv, dict(_state(1), base_rev=0))
    assert code == 200 and r["rev"] == 1
    code, r = _put(srv, dict(_state(2), base_rev=1))
    assert r["rev"] == 2
    got = srv.project_get("d.dxf")
    assert got["rev"] == 2 and len(got["state"]["areas"][0]["slides"]) == 2


def test_a_save_from_a_stale_window_is_refused(srv):
    """נמדד: חלון B (גרסה ישנה) מחק שקופית שחלון A הוסיף."""
    _put(srv, dict(_state(1), base_rev=0))                 # rev 1
    _put(srv, dict(_state(2, "חלון A"), base_rev=1))       # A → rev 2
    code, r = _put(srv, dict(_state(1, "חלון B"), base_rev=1))
    assert code == 409 and r["conflict"] and r["rev"] == 2
    assert srv.project_get("d.dxf")["state"]["areas"][0]["slides"][0]["title"] == "חלון A"


def test_overwrite_on_purpose_keeps_the_other_version(srv):
    _put(srv, dict(_state(1), base_rev=0))
    _put(srv, dict(_state(2, "חלון A"), base_rev=1))
    code, r = _put(srv, dict(_state(1, "חלון B"), base_rev=1, force=True))
    assert code == 200
    v = srv._versions("d.dxf")
    assert any(x["slides"] == 2 for x in v)                # A נשמרה בגרסאות


def test_a_corrupt_file_is_reported_and_never_overwritten(srv):
    """נמדד: קובץ חתוך נפתח כפרויקט ריק, ושינוי שם דרס אותו."""
    _put(srv, dict(_state(5), base_rev=0))
    p = srv._project_path("d.dxf")
    raw = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(raw[:len(raw) // 2])
    got = srv.project_get("d.dxf")
    assert got["found"] and got["corrupt"]
    with pytest.raises(srv.HTTPException) as e:
        _put(srv, dict(_state(0), base_rev=0))
    assert e.value.status_code == 409
    assert open(p, encoding="utf-8").read() == raw[:len(raw) // 2]


def test_a_saved_version_can_be_restored_and_the_corrupt_file_is_kept(srv, monkeypatch):
    monkeypatch.setattr(srv, "_SNAPSHOT_EVERY", 0)
    _put(srv, dict(_state(5), base_rev=0))
    _put(srv, dict(_state(6), base_rev=1))                 # גרסה עם 5 נשמרת
    p = srv._project_path("d.dxf")
    open(p, "w", encoding="utf-8").write('{"areas": [')
    vid = srv._versions("d.dxf")[0]["id"]
    asyncio.run(srv.project_restore(_Req({"drawing": "d.dxf", "version": vid})))
    got = srv.project_get("d.dxf")
    assert len(got["state"]["areas"][0]["slides"]) == 5
    kept = os.listdir(srv._history_dir("d.dxf"))
    assert any(".corrupt" in f for f in kept)              # לא נמחק


def test_the_write_never_leaves_a_half_file(srv, monkeypatch):
    """כתיבה אטומית: אם הכתיבה נכשלת באמצע, הקובץ הקודם נשאר שלם."""
    _put(srv, dict(_state(3), base_rev=0))
    before = open(srv._project_path("d.dxf"), encoding="utf-8").read()

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _put(srv, dict(_state(9), base_rev=1))
    assert open(srv._project_path("d.dxf"), encoding="utf-8").read() == before


def test_versions_are_kept_at_most_every_ten_minutes(srv):
    for i in range(5):
        _put(srv, dict(_state(i + 1), base_rev=i))
    assert len(srv._versions("d.dxf")) == 1
