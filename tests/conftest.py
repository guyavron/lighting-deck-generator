"""הגדרות משותפות לבדיקות.

קונסולת Windows ברירת המחדל היא cp1252 ולא יודעת עברית. בלי זה כל
בדיקה שמדפיסה טקסט עברי נופלת על UnicodeEncodeError שאין לו קשר לנבדק.
כל עובדי המשרד על Windows, ולכן זה נפתר כאן ולא בשורת הפקודה.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


ROOT = os.path.join(os.path.dirname(__file__), "..")


def pytest_sessionstart(session):
    """A fresh clone has no library/ (it is generated, not committed).

    The photo bank is built in code and is deterministic (~6 s), so the
    tests build it themselves instead of failing with "the bank is empty".
    """
    lib = os.path.join(ROOT, "library")
    if os.path.isdir(lib) and any(f.endswith(".png") for f in os.listdir(lib)):
        return
    sys.path.insert(0, os.path.join(ROOT, "examples"))
    import make_demo_library
    make_demo_library.build()
