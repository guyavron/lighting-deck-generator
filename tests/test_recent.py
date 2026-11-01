"""B-12 (QA 21-22.10): אחרי רענון חוזרים לשרטוט האחרון, ומצגות שהופקו
נשארות זמינות ברשימה גם אם הקישור נעלם מהמסך."""
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import server as SRV  # noqa: E402

HTML = os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html")
SRC = open(HTML, encoding="utf-8").read()


def test_recent_decks_newest_first_and_ignores_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(SRV, "OUT_DIR", str(tmp_path))
    for i, name in enumerate(["a.pptx", "b.pptx", "c.pptx.partial", "notes.txt"]):
        f = tmp_path / name
        f.write_bytes(b"x" * 10)
        os.utime(f, (time.time() - 100 + i, time.time() - 100 + i))
    names = [d["file"] for d in SRV.recent_decks()["decks"]]
    assert names == ["b.pptx", "a.pptx"]


def test_recent_decks_limit_and_missing_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(SRV, "OUT_DIR", str(tmp_path))
    for i in range(8):
        (tmp_path / ("d%d.pptx" % i)).write_bytes(b"x")
    assert len(SRV.recent_decks(limit=3)["decks"]) == 3
    monkeypatch.setattr(SRV, "OUT_DIR", str(tmp_path / "nope"))
    assert SRV.recent_decks()["decks"] == []


def test_page_remembers_and_reopens_the_last_drawing():
    assert "localStorage.setItem('lighting-last', S.name)" in SRC
    m = re.search(r"listDrawings\(\)\.then\(\(\) => \{.*?\}\)\.catch", SRC, re.S).group(0)
    assert "lighting-last" in m and "$('#load').click()" in m
    # רק אם הקובץ עדיין קיים ברשימה
    assert "options" in m


def test_recent_list_never_overwrites_a_build_result():
    fn = re.search(r"async function showRecentDecks\(\)\{.*?\n\}\n", SRC, re.S).group(0)
    assert fn.count("box.innerHTML.trim()") >= 2
