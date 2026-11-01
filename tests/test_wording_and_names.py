"""B-14, B-15, B-16, B-17 (QA 21-22.10): שמות וניסוחים לעובד.

הפונקציות רצות ב-node כמו שהן כתובות ב-index.html.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

HTML = os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html")
SRC = open(HTML, encoding="utf-8").read()
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node לא מותקן")


def _grab(pattern):
    return re.search(pattern, SRC, re.S).group(0)


def _node(prelude, expr):
    js = prelude + "console.log(JSON.stringify(%s));" % expr
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                     encoding="utf-8", check=True).stdout)


def _label(code, names):
    pre = ("const S={codeNames:%s};\n" % json.dumps(names, ensure_ascii=False)
           + _grab(r"function hebName\(code\)\{[^\n]*\n")
           + _grab(r"function codeLabel\(code\)\{[^\n]*\n"))
    return _node(pre, "codeLabel(%s)" % json.dumps(code))


def _next(names, prefix="אזור"):
    pre = ("const S={areas:%s};\n" % json.dumps([{"name": n} for n in names], ensure_ascii=False)
           + _grab(r"function nextAreaName\(prefix\)\{.*?\n\}\n"))
    return _node(pre, "nextAreaName(%s)" % json.dumps(prefix, ensure_ascii=False))


# B-14
def test_a_known_code_shows_its_hebrew_name_and_the_code():
    assert _label("SH", {"SH": "שקועים"}) == "שקועים (SH)"


def test_lowercase_code_still_finds_the_name():
    assert _label("sh", {"SH": "שקועים"}) == "שקועים (sh)"


def test_an_unknown_code_is_shown_as_is():
    assert _label("zb", {"SH": "שקועים"}) == "zb"


def test_the_reduce_by_fixture_type_list_uses_the_label():
    assert "${codeLabel(c)}" in SRC


# B-15
def test_step1_wording_has_no_jargon():
    assert "חריגים הוסרו" not in SRC
    assert "קודים ללא שם קטגוריה" not in SRC
    assert "עדיין לא מכיר" in SRC


def test_status_line_is_refreshed_when_the_area_count_changes():
    fn = _grab(r"function updateSummary\(\)\{.*?\n\}\n")
    assert "S.statusBase" in fn and "S.statusAreas" in fn


# B-16
def test_numbering_runs_forward_after_a_deletion():
    assert _next(["אזור 2"]) == "אזור 3"          # "אזור 1" נמחק — לא חוזרים אליו
    assert _next(["אזור 1", "אזור 3"]) == "אזור 4"


def test_numbering_starts_at_one_and_ignores_other_names():
    assert _next([]) == "אזור 1"
    assert _next(["סלון", "אזור א"]) == "אזור 1"
    assert _next(["אזור 1"], "תת-אזור") == "תת-אזור 1"


def test_area_name_gets_selected_on_focus_and_empty_name_is_announced():
    assert "el.onfocus = () => setTimeout(() => el.select(), 0)" in SRC
    assert "השם היה ריק" in SRC


# B-17
def test_adding_an_area_closes_the_old_undo_bar():
    fn = _grab(r"function addArea\(.*?\n\}\n")
    assert "hideUndo()" in fn


def test_the_undo_button_says_what_it_undoes():
    assert 'data-undo>בטל מחיקה</button>' in SRC
