"""חיתוך תצלום הגוף מתוך תמונה מרוכבת.

השקופית בייחוס היא לעיתים תמונה אחת גדולה: שרטוט משמאל, כותרת למעלה,
ותצלום הגוף מימין — הכל צרוב בפוטושופ. גיא ביקש שהחילוץ ייתן **רק את
תצלום הגוף**.

**חותכים רק כשאין ברירה.** כשיש PSD, `layer.bbox` נותן קופסה מדויקת
ואין מה לנחש. כשיש תצלום נפרד ב-PPTX, הקובץ עצמו הוא התצלום. הקוד כאן
נכנס לפעולה רק כשהמקור היחיד הוא התמונה המרוכבת.

**מה שלא עבד, ואל תחזור אליו:** זיהוי רכיבים מחוברים על פיקסלים
לא-שחורים. השרטוט הוא קווי שיער אפורים על שחור, והוא מתפרק לעשרות
רסיסים במקום להיות גוש אחד — 3 עד 6 "אזורים" לכל שקופית, כולם חלקי
שרטוט, ואף לא אחד מהם התצלום.

**מה שעבד:** רוויה. השרטוט אפור — הפרש אפסי בין ערוצי RGB. תצלום הוא
צבעוני. עמודה עם צפיפות בהירות גבוהה **וגם** רוויה ממשית היא תצלום;
עמודה בהירה בלי רוויה היא שרטוט.

נמדד על 110 מרוכבות: ל-51 יש תצלום צרוב ולשאר הצד הימני שחור לגמרי —
שם התצלום הונח מעל ב-PowerPoint ואין מה לחתוך.
"""
from __future__ import annotations

import csv
import io
import os

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
KNOWLEDGE = os.path.join(ROOT, "knowledge")
CROPS = os.path.join(KNOWLEDGE, "asset_crops.csv")

CROP_COLS = ["asset_id", "x", "y", "w", "h", "fixed_by", "fixed_at"]

# ספים שנמדדו. בהירות מעל 40 נחשבת תוכן; הפרש ערוצים מעל 25 נחשב צבע.
DARK = 40
SATURATED = 25
MIN_COLOR = 0.30         # שיעור מינימלי של פיקסלים צבעוניים בעמודה
MIN_BRIGHT = 0.55        # וגם צפיפות. ראה הערת ההארה למטה.
MIN_SIDE = 200           # קופסה קטנה מזה אינה תצלום גוף

# **ההארה מפילה את מבחן הרוויה לבדו.** סמני ההארה צהובים (#F0EB61)
# ורוויים מאוד, ולכן עמודה שעוברת דרך אשכול הארה נראית "צבעונית"
# בדיוק כמו תצלום. ההבדל הוא צפיפות: תצלום ממלא את העמודה מלמעלה
# עד למטה, ונקודות הארה מפוזרות. לכן נדרשות שתי התנאות יחד.


def _columns(im, n=160, rows=90):
    """לכל עמודה: שיעור פיקסלים בהירים, ושיעור פיקסלים צבעוניים."""
    s = im.convert("RGB").resize((n, rows), Image.LANCZOS)
    px = s.load()
    bright = [0.0] * n
    color = [0.0] * n
    for x in range(n):
        b = c = 0
        for y in range(rows):
            r, g, bl = px[x, y]
            mx, mn = max(r, g, bl), min(r, g, bl)
            if mx > DARK:
                b += 1
                if mx - mn > SATURATED:
                    c += 1
        bright[x] = b / float(rows)
        color[x] = c / float(rows)
    return bright, color


def _rows_of(im, x0, x1, rows=90):
    """גבולות אנכיים בתוך טווח העמודות שנבחר."""
    s = im.convert("RGB").resize((160, rows), Image.LANCZOS)
    px = s.load()
    keep = []
    for y in range(rows):
        c = 0
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if max(r, g, b) > DARK and max(r, g, b) - min(r, g, b) > SATURATED:
                c += 1
        if c / float(max(x1 - x0, 1)) > MIN_COLOR:
            keep.append(y)
    return (keep[0], keep[-1]) if keep else (0, rows - 1)


def estimate(im):
    """קופסת התצלום בתוך המרוכבת, או None כשאין מה לחתוך.

    מחזיר (x, y, w, h) בפיקסלים של התמונה המקורית.
    """
    W, H = im.size
    n, rows = 160, 90
    bright, color = _columns(im, n, rows)

    hot = [x for x in range(n)
           if color[x] > MIN_COLOR and bright[x] > MIN_BRIGHT]
    if not hot:
        return None

    # הרצף הצבעוני הארוך ביותר. פערים של עד 3 עמודות נסגרים, כי
    # תצלום עם אזור כהה באמצע אינו שני תצלומים.
    best = run = [hot[0]]
    for x in hot[1:]:
        if x - run[-1] <= 3:
            run.append(x)
        else:
            if len(run) > len(best):
                best = run
            run = [x]
    if len(run) > len(best):
        best = run

    x0, x1 = best[0], best[-1] + 1
    y0, y1 = _rows_of(im, x0, x1, rows)

    sx, sy = W / float(n), H / float(rows)
    box = (int(x0 * sx), int(y0 * sy),
           int((x1 - x0) * sx), int((y1 - y0 + 1) * sy))
    if box[2] < MIN_SIDE or box[3] < MIN_SIDE:
        return None
    return box


# ─── חיתוכים שאדם תיקן ───────────────────────────────────────────

def load_crops():
    """קופסאות שתוקנו ידנית. הן גוברות על האומדן."""
    if not os.path.exists(CROPS):
        return {}
    out = {}
    with io.open(CROPS, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                out[r["asset_id"]] = (int(r["x"]), int(r["y"]),
                                      int(r["w"]), int(r["h"]))
            except (ValueError, KeyError):
                continue
    return out


def save_crop(asset_id, box, fixed_by=""):
    """שמירת תיקון. הקובץ המקורי לעולם אינו נדרס — רק השורה הזו.

    מחיקת השורה מחזירה לאומדן האוטומטי.
    """
    import datetime
    rows = []
    if os.path.exists(CROPS):
        with io.open(CROPS, encoding="utf-8-sig") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if r.get("asset_id") != asset_id]
    rows.append({"asset_id": asset_id, "x": box[0], "y": box[1],
                 "w": box[2], "h": box[3], "fixed_by": fixed_by,
                 "fixed_at": datetime.datetime.now()
                 .strftime("%Y-%m-%d %H:%M:%S")})
    with io.open(CROPS, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, CROP_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CROP_COLS})


def apply_crop(asset_id, library_dir, box=None):
    """יצירת `crops/<id>.png` מהמקור. המקור לעולם אינו נדרס.

    בלי `box` — משתמשים במה שרשום ב-CSV; אם אין שם שורה, החיתוך
    הקיים נמחק והתמונה חוזרת להיות מלאה.
    """
    src = os.path.join(library_dir, asset_id + ".png")
    if not os.path.exists(src):
        return None
    out_dir = os.path.join(library_dir, "crops")
    out = os.path.join(out_dir, asset_id + ".png")
    if box is None:
        box = load_crops().get(asset_id)
    if box is None:
        if os.path.exists(out):
            os.remove(out)        # מסירים גזירה, לא מקור
        return None
    os.makedirs(out_dir, exist_ok=True)
    im = Image.open(src)
    x, y, w, h = box
    x = max(0, min(x, im.size[0] - 1))
    y = max(0, min(y, im.size[1] - 1))
    w = max(1, min(w, im.size[0] - x))
    h = max(1, min(h, im.size[1] - y))
    im.convert("RGB").crop((x, y, x + w, y + h)).save(out)
    return out
