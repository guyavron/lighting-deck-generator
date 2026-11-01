"""חיווי טעינה: השרת מדווח באיזה שלב הטעינה, ואם זו הפעם הראשונה."""
import ezdxf

import plan_render as PR
import server as SRV


def test_progress_reports_the_step_and_clears_when_done():
    name = "progress-test.dxf"
    assert SRV.load_progress(name) == {"active": False}
    SRV._step(name, 1, first=True)
    SRV._step(name, 2, n_fixtures=354)
    p = SRV.load_progress(name)
    assert p["active"] and p["step"] == 2 and p["first"] is True
    assert p["n_fixtures"] == 354 and p["elapsed"] >= 0
    SRV._progress.pop(name)
    assert SRV.load_progress(name) == {"active": False}


def test_a_failed_load_does_not_leave_progress_behind(monkeypatch, tmp_path):
    monkeypatch.setattr(SRV, "DXF_DIR", str(tmp_path))
    (tmp_path / "broken.dxf").write_text("not a drawing")
    try:
        SRV.load_drawing("broken.dxf")
    except Exception:
        pass
    assert SRV.load_progress("broken.dxf") == {"active": False}


def test_first_load_is_known_before_recording(monkeypatch, tmp_path):
    monkeypatch.setattr(PR, "CACHE_DIR", str(tmp_path / "cache"))
    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (10, 10))
    path = str(tmp_path / "d.dxf")
    doc.saveas(path)
    assert not PR.is_recorded(path)
    PR.record_cached(path)
    assert PR.is_recorded(path)
