"""מטמון מקומי לפי תוכן, וזיכרון מאגר רק ממה שיצא במצגת (D-038)."""
import csv
import io
import shutil

import ezdxf
import pytest

import plan_render as PR


def _dxf(path):
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (10, 0))
    doc.saveas(path)


def test_a_copy_of_the_same_drawing_shares_the_cache(tmp_path, monkeypatch):
    """עותק של שרטוט, או אותו שרטוט בשם אחר, אינו מוקלט מחדש."""
    monkeypatch.setattr(PR, "CACHE_DIR", str(tmp_path / "cache"))
    a, b = tmp_path / "a.dxf", tmp_path / "עותק.dxf"
    _dxf(a)
    shutil.copy(a, b)
    assert PR._content_key(str(a)) == PR._content_key(str(b))
    PR.record_cached(str(a))
    calls = []
    monkeypatch.setattr(PR, "record", lambda p: calls.append(p))
    PR.record_cached(str(b))
    assert calls == []                          # נטען מהמטמון


def test_a_changed_drawing_gets_its_own_cache(tmp_path):
    a, b = tmp_path / "a.dxf", tmp_path / "b.dxf"
    _dxf(a)
    _dxf(b)
    with open(b, "a") as fh:
        fh.write("999\nrevision\n")
    assert PR._content_key(str(a)) != PR._content_key(str(b))


def test_the_cache_is_not_inside_the_project(monkeypatch):
    """בתיקייה המשותפת הוא צבר 1.2GB שהסתנכרנו לענן."""
    monkeypatch.delenv("LIGHTING_CACHE_DIR", raising=False)
    d = PR._default_cache_dir().replace("\\", "/")
    assert "/out/" not in d
    monkeypatch.setenv("LIGHTING_CACHE_DIR", "X:/elsewhere")
    assert PR._default_cache_dir() == "X:/elsewhere"


def test_only_exported_photos_are_remembered_and_only_once(tmp_path, monkeypatch):
    import library as LIB
    import server as SRV
    monkeypatch.setattr(LIB, "CHOICES", str(tmp_path / "choices.csv"))
    sl = SRV.SlideSpec(photos=["p1", "p2"], photo_category="שקועים")
    spec = SRV.BuildSpec(drawing="d.dxf", areas=[
        SRV.AreaSpec(name="א", x0=0, y0=0, x1=1, y1=1, slides=[sl, sl])])
    assert SRV._remember_exported_photos(spec) == 2
    assert SRV._remember_exported_photos(spec) == 0   # הפקה חוזרת
    with io.open(LIB.CHOICES, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["asset_id"], r["source"]) for r in rows] == [("p1", "export"), ("p2", "export")]
