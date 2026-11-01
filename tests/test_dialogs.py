"""B-13 (QA 21-22.10): אין יותר חלונות confirm()/alert() של הדפדפן.

הם נפתחים באנגלית, בלי RTL אמין, וחוסמים כל אוטומציה. במקומם `askYes`
(חלון של הכלי). הבדיקה סורקת את הקובץ ומריצה את הפונקציות ב-node.
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


def _code_lines():
    """שורות קוד בלי הערות, כדי שתיעוד שמזכיר את confirm() לא ייספר."""
    out = []
    in_block = False
    for line in SRC.split("\n"):
        t = line.strip()
        if in_block:
            if "*/" in t:
                in_block = False
            continue
        if t.startswith("/*"):
            if "*/" not in t:
                in_block = True
            continue
        if t.startswith("//"):
            continue
        out.append(line)
    return out


def test_no_browser_dialogs_are_left():
    bad = [l.strip() for l in _code_lines()
           if re.search(r"(?<![\w.])(confirm|alert|prompt)\(", l)]
    assert bad == [], bad


def test_every_ask_yes_caller_is_inside_an_async_function():
    # `await` בתוך פונקציה רגילה הוא שגיאת תחביר — node --check תופס, ופה
    # בודקים שכל שימוש ב-await askYes / confirmGlobal באמת מחכה
    for l in _code_lines():
        if re.search(r"(?<!await )confirmGlobal\(", l) and "function confirmGlobal" not in l:
            pytest.fail("confirmGlobal בלי await: " + l.strip())


@pytest.mark.skipif(not NODE, reason="node לא מותקן")
def _run(choice, done):
    fn = re.search(r"function askYes\(title, lines, yes, no, safe\)\{.*?\n\}\n", SRC, re.S).group(0)
    cg = re.search(r"async function confirmGlobal\(what\)\{.*?\n\}\n", SRC, re.S).group(0)
    js = ("let LAST=null;\n"
          "function askChoice(t,l,b){LAST=b; return Promise.resolve(%s);}\n"
          "function doneCount(){return %d;}\n"
          "function cnt(n,a,b){return n+' '+a;}\n" % (json.dumps(choice), done)
          + fn + cg +
          "(async()=>{const r=await confirmGlobal('שינוי'); console.log(JSON.stringify([r,LAST&&LAST.map(x=>[x.value,!!x.primary])]));})();")
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                                     encoding="utf-8", check=True).stdout)


@pytest.mark.skipif(not NODE, reason="node לא מותקן")
def test_yes_returns_true_and_cancel_returns_false():
    assert _run("yes", 2)[0] is True
    assert _run("no", 2)[0] is False
    assert _run(None, 2)[0] is False      # Esc / לחיצה בחוץ


@pytest.mark.skipif(not NODE, reason="node לא מותקן")
def test_no_dialog_when_nothing_is_approved():
    assert _run("no", 0) == [True, None]


@pytest.mark.skipif(not NODE, reason="node לא מותקן")
def test_destructive_question_makes_cancel_the_default_button():
    _, btns = _run("yes", 3)
    assert btns == [["yes", False], ["no", True]]
