"""B-19, B-20, B-21, B-22 (QA 21-22.10)."""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import server as SRV  # noqa: E402

SRC = open(os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html"),
           encoding="utf-8").read()
SERVER = open(os.path.join(os.path.dirname(__file__), "..", "src", "server.py"),
              encoding="utf-8").read()


# B-19
def test_deck_file_name_starts_with_the_project_name():
    assert SRV._deck_base("פרויקט בדיקה ב.dxf") == "פרויקט בדיקה ב"
    assert SRV._deck_base("1.dxf") == "1"


def test_deck_file_name_is_safe_for_windows():
    b = SRV._deck_base('a<b>:"c"/d\\e|f?g*.dxf')
    assert not re.search(r'[<>:"/\\|?*]', b)
    assert SRV._deck_base("...dxf") == "deck" or SRV._deck_base("...dxf")
    assert SRV._deck_base("") == "deck"
    assert len(SRV._deck_base("x" * 200 + ".dxf")) <= 50


def test_build_uses_the_project_name():
    assert 'SL.stamped(OUT_DIR, _deck_base(spec.drawing), ".pptx")' in SERVER


# B-20
def test_upload_errors_use_a_visible_notice():
    fn = re.search(r"async function uploadFile\(f\)\{.*?\n\}\n", SRC, re.S).group(0)
    assert fn.count("showNotice(") == 2


def test_notice_closes_by_click_and_by_timer():
    fn = re.search(r"function showNotice\(text\)\{.*?\n\}\n", SRC, re.S).group(0)
    assert "setTimeout" in fn and "onclick" in fn


# B-21
def test_name_fields_are_limited_to_60_chars_with_a_message():
    assert "const NAME_MAX = 60;" in SRC
    for anchor in ("limitName(inp);", "limitName(el);"):
        assert anchor in SRC
    assert SRC.count("limitName(") >= 4          # הגדרה + שלושה שדות
    assert "השם הוגבל ל-" in SRC


# B-22
def test_closing_the_tab_warns_when_changes_are_unsaved():
    m = re.search(r"addEventListener\('beforeunload'.*?\}\);", SRC, re.S).group(0)
    assert "SAVE.dirty" in m and "preventDefault" in m and "returnValue" in m
