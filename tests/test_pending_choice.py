"""B-07 (QA 21-22.10): שחזור מהדפדפן לא מחליף גרסה חדשה בישנה.

עותק אחד בדפדפן לכל שרטוט, משותף לכל הלשוניות. לשונית ישנה שנחסמה
בהתנגשות המשיכה לכתוב אליו 9 שקופיות, ובפתיחה הבאה "אישור" (הכפתור הבולט
בחלון הדפדפן) החליף 15 שקופיות ב-9. עכשיו ברירת המחדל נקבעת לפי מי חדש
יותר: אם השרת התקדם מאז שהעותק התחיל — השרת; אם לא — הדפדפן.
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


def _plan(browser_slides, server_slides, base_rev, server_rev):
    src = open(HTML, encoding="utf-8").read()
    m = re.search(r"function pendingPlan\(p, server, serverRev\)\{.*?\n\}\n", src, re.S)
    assert m, "pendingPlan חסרה"
    mk = lambda n: {"areas": [{"slides": [{} for _ in range(n)]}]}
    js = (m.group(0) +
          "const p={state:%s, base_rev:%d};\n" % (json.dumps(mk(browser_slides)), base_rev) +
          "console.log(JSON.stringify(pendingPlan(p, %s, %d)));\n"
          % (json.dumps(mk(server_slides)), server_rev))
    out = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                         encoding="utf-8", check=True).stdout
    return json.loads(out)


def test_when_the_server_moved_on_the_server_is_the_default():
    r = _plan(9, 15, base_rev=3, server_rev=5)          # המקרה מהדוח
    assert r["primary"] == "server" and r["newer"] is True
    assert (r["n"], r["m"]) == (9, 15)


def test_when_the_server_did_not_move_the_browser_is_the_default():
    r = _plan(15, 12, base_rev=5, server_rev=5)         # השרת קרס באמצע שמירה
    assert r["primary"] == "browser" and r["newer"] is False


def test_the_counts_are_slides_not_areas():
    assert _plan(2, 7, 1, 1)["m"] == 7
