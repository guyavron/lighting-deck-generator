"""B-05 (QA 21-22.10): הכותרת האוטומטית שהלקוח רואה לא מכילה קוד גולמי
ולא "נבחרו ידנית".

הכותרת מורכבת בדפדפן (`lightingLabel`), ולכן הבדיקה מריצה את הפונקציה
עצמה ב-node, עם תלויות מדומות. בלי node הבדיקה מדלגת (כמו בדיקת התחביר).
"""
import json
import os
import re
import shutil
import subprocess

import pytest

HTML = os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html")
NODE = shutil.which("node")


def _label(codes, picks=False, names=None):
    src = open(HTML, encoding="utf-8").read()
    fn = re.search(r"function lightingLabel\(a, sl\)\{.*?\n\}\n", src, re.S).group(0)
    hn = re.search(r"function hebName\(code\)\{[^\n]*\n", src).group(0)
    fixtures = [{"i": i, "code": c} for i, c in enumerate(codes)]
    js = (
        "const S={codeNames:%s};\n" % json.dumps(names or {}, ensure_ascii=False) +
        "const FX=%s;\n" % json.dumps(fixtures) +
        "function litIndices(a,sl){return new Set(FX.map(f=>f.i));}\n"
        "function ovFixturesIn(a){return FX;}\n" + hn + fn +
        "console.log(JSON.stringify(lightingLabel({}, {picks:%s})));\n"
        % ("[1,2]" if picks else "[]"))
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


NAMES = {"SH": "שקועים", "SP": "ספוטים", "WA": "קיר"}
pytestmark = pytest.mark.skipif(not NODE, reason="node לא מותקן")


def test_an_unknown_code_is_left_out_and_more_is_added_is_added():
    assert _label(["SH", "SH", "zb"], names=NAMES) == "שקועים ועוד"


def test_the_raw_code_never_reaches_the_title():
    assert "zb" not in _label(["zb", "SP", "SH"], names=NAMES)
    assert "AURA" not in _label(["AURA 1", "SH"], names=NAMES)


def test_only_unknown_codes_give_a_plain_title():
    assert _label(["zb", "AURA 1"], names=NAMES) == "גופי תאורה"


def test_known_names_work_as_before():
    assert _label(["SH", "SP"], names=NAMES) == "שקועים + ספוטים"
    assert _label(["SH", "SP", "WA"], names=NAMES) == "שקועים + ספוטים ועוד"
    assert _label(["SH"], names=NAMES) == "שקועים"


def test_manual_picks_do_not_add_internal_words_to_the_title():
    assert _label(["SH", "SP"], picks=True, names=NAMES) == "שקועים + ספוטים"
