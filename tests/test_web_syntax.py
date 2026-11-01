"""הסקריפט של הממשק תקין תחבירית.

נתפס ב-13.10: שבירת שורה אמיתית נכנסה למחרוזת, וכל הממשק לא עלה —
רשימת השרטוטים ריקה, בלי שום הודעה. הבדיקות בפייתון לא ראו את זה,
כי הן לא מריצות את הדף. node בודק תחביר בלי להריץ.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "src", "web", "index.html")


@pytest.mark.skipif(not shutil.which("node"), reason="node אינו מותקן")
def test_the_page_script_parses(tmp_path):
    s = open(PAGE, encoding="utf-8").read()
    start = s.index("<script>") + len("<script>")
    end = s.rindex("</script>")
    js = tmp_path / "page.js"
    # שורות ריקות לפני — כדי שמספר השורה בשגיאה יתאים ל-index.html
    js.write_text("\n" * s[:start].count("\n") + s[start:end], encoding="utf-8")
    r = subprocess.run(["node", "--check", str(js)], capture_output=True,
                       text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr[:600]
