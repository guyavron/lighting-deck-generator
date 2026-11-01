"""העלאה חוזרת של אותו שרטוט אינה פותחת פרויקט ריק.

מצב הפרויקט נשמר לפי שם הקובץ. כל העלאה חוזרת יצרה עותק בשם חדש,
ולכן פרויקט חדש וריק — 17 עותקים זהים של `111 (2).dxf` נמצאו ב-DXF/,
והעבודה הייתה מפוזרת ביניהם.
"""
import asyncio
import io
import json
import os

from fastapi import UploadFile


def _client(tmp_path, monkeypatch):
    import server as SRV
    monkeypatch.setattr(SRV, "DXF_DIR", str(tmp_path / "DXF"))
    monkeypatch.setattr(SRV, "PROJECTS_DIR", str(tmp_path / "projects"))
    return SRV, SRV


def _dxf(tag=b"x"):
    """DXF מינימלי אבל שלם: פותח ב-SECTION ונגמר ב-EOF (B-04)."""
    return (b"999\n" + tag + b"\n0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n")


def _up(srv, name, data):
    f = UploadFile(file=io.BytesIO(data), filename=name)
    return asyncio.run(srv.upload(f))


def test_same_file_twice_reuses_the_first(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    a = _up(c, "plan.dxf", _dxf(b"x" * 100))
    b = _up(c, "plan.dxf", _dxf(b"x" * 100))
    assert a == {"name": "plan.dxf", "mb": 0.0, "existing": False}
    assert b["name"] == "plan.dxf" and b["existing"]
    assert os.listdir(tmp_path / "DXF") == ["plan.dxf"]


def test_same_content_under_another_name_is_recognised(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    _up(c, "plan.dxf", _dxf(b"same bytes"))
    assert _up(c, "renamed.dxf", _dxf(b"same bytes"))["name"] == "plan.dxf"


def test_different_content_same_name_gets_a_new_copy(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    _up(c, "plan.dxf", _dxf(b"version one"))
    b = _up(c, "plan.dxf", _dxf(b"version two"))
    assert b["name"] != "plan.dxf" and not b["existing"]
    assert len(os.listdir(tmp_path / "DXF")) == 2


def test_among_old_duplicates_the_latest_work_wins(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    d = tmp_path / "DXF"
    d.mkdir()
    for n in ("a.dxf", "b.dxf", "c.dxf"):
        (d / n).write_bytes(_dxf(b"dup"))
    os.makedirs(SRV.PROJECTS_DIR)
    for n, t in (("a.dxf", 100), ("b.dxf", 300), ("c.dxf", 200)):
        p = SRV._project_path(n)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"drawing": n}, fh)
        os.utime(p, (t, t))
    assert _up(c, "a.dxf", _dxf(b"dup"))["name"] == "b.dxf"


# ── B-04: קובץ שאינו DXF או DXF חתוך לא נשמר ──

import pytest
from fastapi import HTTPException


def test_a_text_file_named_dxf_is_refused_and_not_saved(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as e:
        _up(c, "notes.dxf", b"hello this is not a dxf")
    assert e.value.status_code == 400
    assert "DXF" in e.value.detail and "אוטוקאד" in e.value.detail
    assert not (tmp_path / "DXF").exists() or os.listdir(tmp_path / "DXF") == []


def test_a_truncated_dxf_is_refused_and_not_saved(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    cut = _dxf(b"y" * 5000)[:-9]            # נחתך לפני EOF
    with pytest.raises(HTTPException) as e:
        _up(c, "cut.dxf", cut)
    assert e.value.status_code == 400
    assert not (tmp_path / "DXF").exists() or os.listdir(tmp_path / "DXF") == []


def test_a_dxf_that_opens_with_a_comment_is_accepted(tmp_path, monkeypatch):
    # בקובץ אמיתי אחד יש 999 לפני ה-SECTION הראשון
    SRV, c = _client(tmp_path, monkeypatch)
    assert _up(c, "ok.dxf", _dxf(b"QA copy"))["name"] == "ok.dxf"


def test_a_real_dxf_with_windows_line_endings_is_accepted(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    data = b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n  0\r\nENDSEC\r\n  0\r\nEOF\r\n"
    assert _up(c, "win.dxf", data)["name"] == "win.dxf"


def test_loading_a_broken_file_gives_a_hebrew_message_not_a_500(tmp_path, monkeypatch):
    SRV, c = _client(tmp_path, monkeypatch)
    os.makedirs(SRV.DXF_DIR)
    open(os.path.join(SRV.DXF_DIR, "bad.dxf"), "wb").write(b"not a drawing at all")

    def boom(name, path):
        raise ValueError("Invalid DXF structure")
    monkeypatch.setattr(SRV, "_load_drawing", boom)
    monkeypatch.setattr(SRV, "_cache", {})
    with pytest.raises(HTTPException) as e:
        SRV.load_drawing("bad.dxf")
    assert e.value.status_code == 400
    assert "אוטוקאד" in e.value.detail
