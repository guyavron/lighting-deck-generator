"""תיוג הבנק לפי קריטריוני הסינון — רק ממה שיש עליו ראיה.

    python src/tag_assets.py            # גוזר ומדפיס סיכום
    python src/tag_assets.py --write    # כותב knowledge/asset_tags.csv

יש הבדל בין ראיה לניחוש, ואסור לערבב ביניהם.

**ראיה** היא שם הקבוצה ב-PSD או טקסט כותרת השקופית ב-PPTX. משם
נגזרים סוג ההתקנה (שקועים ← שקוע בתקרה) והחלל. הגזירה
מוגבלת למיפויים חד-משמעיים ב-`asset_criteria.yaml`: "מערכת" ו"ספוטים"
נשארים ריקים במכוון, כי מהשם אי אפשר להכריע בין מסילה שקועה, צמודה
ותלויה — וזה בדיוק הפיצול שהתיוג אמור להוסיף.

**ניחוש** הוא סגנון, גימור, אופי אור וגוון. אלה תכונות חזותיות שאין
להן זכר בטקסט. הן נשארות ריקות.

הסיבה שהן נשארות ריקות ולא מנוחשות: **ערך שגוי שממתין לאישור מקבל
אישור.** שדה ריק מזמין מבט; שדה מלא בניחוש נראה בדוק וחומק. עדיף
בנק חלקי ונכון על בנק מלא ומטעה.

הקובץ נפרד מ-`assets.csv` בכוונה — `seed_library.py` מייצר את
assets.csv מחדש, ותיוג ידני שיושב בתוכו היה נמחק בכל זריעה.
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml

import library as LIB

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
KNOWLEDGE = os.path.join(ROOT, "knowledge")
TAGS = os.path.join(KNOWLEDGE, "asset_tags.csv")

COLS = ["asset_id", "install", "style", "finish", "beam", "cct", "room",
        "reviewed", "note"]


def criteria():
    with io.open(os.path.join(KNOWLEDGE, "asset_criteria.yaml"),
                 encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def existing():
    """תיוג קיים. עבודה של אדם לעולם אינה נדרסת."""
    if not os.path.exists(TAGS):
        return {}
    with io.open(TAGS, encoding="utf-8-sig") as fh:
        return {r["asset_id"]: r for r in csv.DictReader(fh)}


def derive(asset, cfg):
    """מה שאפשר לגזור מהראיה. השאר נשאר ריק."""
    inst_map = cfg.get("derive_install_from_category") or {}
    room_map = cfg.get("derive_room_from_tag") or {}

    install = ""
    rooms = []
    for t in asset["tags"]:
        if not install and t in inst_map:
            install = inst_map[t]
        r = room_map.get(t)
        if r and r not in rooms:
            rooms.append(r)

    return {"install": install, "style": "", "finish": "", "beam": "",
            "cct": "", "room": "|".join(rooms),
            "reviewed": "", "note": ""}


def build(write=False):
    cfg = criteria()
    have = existing()
    rows, stats = [], {"install": 0, "room": 0, "kept": 0, "new": 0}

    for a in LIB.load():
        aid = a["asset_id"]
        d = derive(a, cfg)
        old = have.get(aid)
        if old:
            # ערך שאדם כתב או אישר גובר על הגזירה
            for c in COLS[1:]:
                if (old.get(c) or "").strip():
                    d[c] = old[c]
            stats["kept"] += 1
        else:
            stats["new"] += 1
        if d["install"]:
            stats["install"] += 1
        if d["room"]:
            stats["room"] += 1
        rows.append(dict(d, asset_id=aid))

    if write:
        with io.open(TAGS, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, COLS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in COLS})
    return rows, stats


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="תיוג הבנק מראיה בלבד")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows, st = build(args.write)
    print("נכסים: %d  (קיימים %d, חדשים %d)"
          % (len(rows), st["kept"], st["new"]))
    print("נגזר מראיה:  סוג התקנה %d   חלל %d" % (st["install"], st["room"]))
    print("")
    print("נשאר ריק במכוון — אין לזה ראיה בטקסט, רק בתמונה עצמה:")
    for c in ("style", "finish", "beam", "cct"):
        print("   %-8s %d נכסים" % (c, sum(1 for r in rows if not r[c])))
    print("")
    print("נכתב: " + TAGS if args.write else "לא נכתב (הרץ עם --write)")
