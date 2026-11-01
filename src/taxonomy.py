"""טקסונומיית התאורה: תרגום בין קטגוריה שהעובד מכיר לקודי בלוקים ב-DXF.

כל שקופית מאירה תת-קבוצה אחרת של גופים — אלה שמדברים עליהם בה.
העובד חושב "שקועים בסלון", לא "בלוק SH". כאן נעשה התרגום.
"""
from __future__ import annotations

import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")


def load(path=None):
    path = path or os.path.join(KNOWLEDGE, "taxonomy.yaml")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def types(tax=None):
    return (tax or load())["lighting_types"]


def resolve(name, tax=None):
    """שם קטגוריה (עברית או key באנגלית) -> רשימת קודי בלוקים.

    מחזיר [] אם הקטגוריה מוכרת אבל אין לה מיפוי — זה מצב לגיטימי,
    והקורא צריך לבקש מהמשתמש לבחור ידנית.
    """
    name = (name or "").strip()
    for t in types(tax):
        names = [t["he"], t["key"]] + t.get("aliases", [])
        if any(name == n or name in n for n in names):
            return list(t.get("dxf_blocks", []))
    return None          # None = קטגוריה לא מוכרת בכלל


def describe_unmapped(codes_seen, tax=None):
    """אילו קודים שנמצאו בשרטוט אינם ממופים לאף קטגוריה."""
    mapped = set()
    for t in types(tax):
        mapped.update(t.get("dxf_blocks", []))
    return sorted(c for c in codes_seen if c.upper() not in {m.upper() for m in mapped})
