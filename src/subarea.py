"""סימון תת-אזור — מסכה צהובה שקופה על חלק מהתוכנית.

מקור: מצגת ייחוס א, שקופיות 6, 44, 97, 105. העובד מסמן פוליגון בזוויות
ישרות על חלק מהאזור, והשקופית מדגישה אותו: "כאן מדובר".

**זו אינה הארה.** ההארה היא אור שיוצא מגוף; המסכה היא סימון על
תוכנית. הן נראות שונה, מתנהגות שונה, ומצוירות בסדר קבוע — המסכה
מתחת, ההארה מעליה.

**כל הנקודות בקואורדינטות השרטוט (עולם), לא בפיקסלים.** התוכנית
מרונדרת בשלושה גדלים שונים לפחות — סקירה, זום לאזור, ופאנל
השקופית — ופוליגון בפיקסלים היה נכון באחד מהם ושגוי בשניים.
"""
from __future__ import annotations

import os

import yaml
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")


def spec():
    """פרמטרי המסכה. הידע חי ב-knowledge, לא כאן."""
    with open(os.path.join(KNOWLEDGE, "layout.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)["sub_area_mask"]


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def orthogonalize(points):
    """כל צלע אופקית או אנכית — פוליגון אורתוגונלי, לא מצולע חופשי.

    כל נקודה נצמדת לציר שבו התזוזה גדולה יותר. מי שלוחץ באלכסון
    מקבל צלע בכיוון שהתכוון אליו, ובלחיצה הבאה משלים את המדרגה.

    **השרת מיישר, לא רק הממשק.** הממשק מראה את זה תוך כדי ציור,
    אבל מה שנצרב לתמונה עובר כאן — ולכן מסכה עקומה אינה יכולה
    להגיע למצגת גם אם משהו בדפדפן ישתבש.
    """
    pts = [(float(x), float(y)) for x, y in points if x is not None]
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for x, y in pts[1:]:
        px, py = out[-1]
        if abs(x - px) >= abs(y - py):
            cand = (x, py)
        else:
            cand = (px, y)
        if cand != out[-1]:
            out.append(cand)
    return out


def close_ring(points):
    """סוגר את הטבעת בזווית ישרה, בתוספת פינה אחת לכל היותר."""
    pts = orthogonalize(points)
    if len(pts) < 3:
        return pts
    ax, ay = pts[-1]
    bx, by = pts[0]
    if ax != bx and ay != by:
        pts = pts + [(bx, ay)]
    # נקודה אחרונה שזהה לראשונה אינה מוסיפה צלע
    if len(pts) > 1 and pts[-1] == pts[0]:
        pts = pts[:-1]
    return pts


def contains(points, x, y):
    """האם נקודה בתוך הפוליגון. ray casting רגיל.

    משמש כדי לצמצם את ההארה לתת-האזור: גיא ביקש שאחרי הסימון
    עובדים על תת-האזור, ולא שהמסכה תהיה קישוט בלבד.
    """
    pts = points
    n = len(pts)
    if n < 3:
        return True                      # אין סימון = הכל בפנים
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            t = (y - yi) / (yj - yi) if yj != yi else 0.0
            if x < xi + t * (xj - xi):
                inside = not inside
        j = i
    return inside


def clip(base, points_px, background=(0, 0, 0)):
    """מחוץ לפוליגון — צבע הרקע (שחור, או אפור בסגנון האפור).

    **זה מה שהופך תת-אזור לצורה ולא לריבוע.** בלי זה השקופית
    מציגה את תיבת החוסמת של הפוליגון על כל מה שבתוכה, וגיא צדק
    כשאמר "הציג את תת האזור כריבוע למרות שבבירור גזרתי אותו לא
    כריבוע". מצגת ייחוס א 106 מראה את גוש החניה בלבד — כל המרתף שסביבו
    נעלם, כולל החדרים מימין והשטח המקווקו משמאל.

    נחתכת התוכנית בלבד. ההארה מצוירת אחר כך ורשאית לגלוש מעט מעבר
    לגבול — אור אינו נעצר בקו שרטוט.
    """
    pts = [(round(x), round(y)) for x, y in points_px]
    if len(pts) < 3:
        return base
    m = Image.new("L", base.size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    out = Image.new("RGB", base.size, tuple(background))
    out.paste(base, mask=m)
    return out


def render(base, points_px, params=None):
    """צורב את המסכה לתוך פאנל התוכנית.

    `points_px` — הפוליגון כבר בפיקסלים של הפאנל.

    נצרב ולא מונח כצורת PPTX נפרדת: המסכה מתארת אזור **בתוכנית**,
    וצורה נפרדת הייתה מתנתקת ממנה ברגע שמישהו מזיז את התוכנית
    ב-PowerPoint. ראה `knowledge/layout.yaml`.
    """
    pts = [(round(x), round(y)) for x, y in points_px]
    if len(pts) < 3:
        return base
    p = params or spec()
    # עיגול כלפי מעלה בחצי, ולא round של פייתון. 0.30*255 = 76.5,
    # ו-round מחזיר 76 (עיגול לזוגי) — מה שנתן (72,63,26) במקום
    # (72,64,26) שנמדד. פיקסל אחד, אבל הוא ההבדל בין "נמדד" ל"בערך".
    alpha = int(float(p["opacity"]) * 255 + 0.5)
    over = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(over).polygon(pts, fill=_rgb(p["fill"]) + (alpha,))
    return Image.alpha_composite(base.convert("RGBA"), over).convert("RGB")
