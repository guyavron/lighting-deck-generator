"""B-09, B-10, B-11 (QA 21-22.10): תיקוני ממשק קטנים.

B-11: "Failed to fetch" באנגלית הופך להוראה בעברית.
B-10: לחיצה כפולה על "שקופית חדשה" לא יוצרת שתי שקופיות.
B-09: פסי ההודעה צפים ולא דוחפים את התוכן (נבדק במבנה ה-CSS).
הפונקציות רצות ב-node כמו שהן כתובות ב-index.html.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

HTML = os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html")
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="node לא מותקן")
SRC = open(HTML, encoding="utf-8").read()


def _run(body):
    no = re.search(r"const NO_SERVER = [^\n]*\n", SRC).group(0)
    fn = re.search(r"function errText\(e\)\{.*?\n\}\n", SRC, re.S).group(0)
    tp = re.search(r"let _lastTap = 0;\nfunction tapOnce\(\)\{.*?\n\}\n", SRC, re.S).group(0)
    out = subprocess.run([NODE, "-e", no + fn + tp + body], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_failed_to_fetch_becomes_hebrew():
    t = _run("console.log(JSON.stringify(errText(new TypeError('Failed to fetch'))))")
    assert "Failed" not in t and "השרת לא עונה" in t


def test_other_browsers_network_wording_is_also_translated():
    for m in ("NetworkError when attempting to fetch resource.", "Load failed"):
        t = _run("console.log(JSON.stringify(errText(new Error(%s))))" % json.dumps(m))
        assert "השרת לא עונה" in t


def test_a_server_message_in_hebrew_passes_through():
    t = _run("console.log(JSON.stringify(errText(new Error('הקובץ פגום'))))")
    assert t == "הקובץ פגום"


def test_no_raw_e_message_is_left_on_screen():
    # כל הצגה של e.message למשתמש עוברת דרך errText
    left = [l for l in SRC.split("\n") if "e.message" in l and "errText" not in l
            and "const m =" not in l]
    assert left == [], left


def test_a_second_tap_within_a_moment_is_swallowed():
    r = _run("const a=tapOnce(), b=tapOnce(); console.log(JSON.stringify([a,b]))")
    assert r == [True, False]


def test_both_new_slide_buttons_use_the_guard():
    for key in ("data-addslide", "data-photoslide"):
        m = re.search(r"\[%s\]'\)\.onclick = \(\) => \{\n\s*if\(!tapOnce\(\)\) return;" % key, SRC)
        assert m, key


def test_message_bars_do_not_push_the_content():
    bar = re.search(r"#savebar\{[^}]*\}", SRC).group(0)
    assert "position:fixed" in bar
    hint = re.search(r"#modehintbox\{[^}]*\}", SRC).group(0)
    assert "height:0" in hint and "position:sticky" in hint
    assert "position:absolute" in re.search(r"#modehint\{[^}]*\}", SRC).group(0)
