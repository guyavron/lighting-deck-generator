"""בחירת חלון הצפייה בתוכנית.

זו הנקודה שבה מצגת נכשלת בשקט. עמודת התוכנית בשקופית היא 332x878
פיקסלים — יחס 0.38, פורטרט צר. אם לוקחים אזור רחב ודליל ומכניסים
אותו לשם תוך שמירה על יחס הממדים, מקבלים רצועה זעירה שנבלעת בשחור:
נכון טכנית, חסר ערך בפועל.

שני כללים שאינם ניתנים למשא ומתן:
  1. לעולם לא מותחים — יחס הממדים נשמר.
  2. לעולם לא חותכים כדי למלא את המסגרת — זה מוחק חלקי שרטוט בשקט,
     וזה פסול בתוכנית תאורה.

לכן ההתאמה נעשית תמיד על ידי *הרחבת* הצלע הקצרה, ואם התוצאה עדיין
דלילה מדי — מתריעים במקום להפיק שקופית חסרת תועלת.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Framing:
    window: tuple           # (x0, y0, x1, y1) ביחידות השרטוט
    panel_px: tuple         # (w, h) בפיקסלים
    scale: float            # פיקסלים ליחידת שרטוט
    fill_ratio: float       # איזה חלק מהפאנל תפוס בתוכן שנבחר
    warnings: list


def expand_to_aspect(window, aspect, margin_frac=0.06):
    """מרחיב חלון כך שיתאים ליחס הפאנל. אף פעם לא מקטין."""
    x0, y0, x1, y1 = window
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    mx, my = w * margin_frac, h * margin_frac
    x0, x1, y0, y1 = x0 - mx, x1 + mx, y0 - my, y1 + my
    w, h = x1 - x0, y1 - y0
    cur = w / h
    if cur > aspect:            # רחב מדי -> להגביה
        need = w / aspect
        pad = (need - h) / 2
        y0, y1 = y0 - pad, y1 + pad
    elif cur < aspect:          # גבוה מדי -> להרחיב
        need = h * aspect
        pad = (need - w) / 2
        x0, x1 = x0 - pad, x1 + pad
    return (x0, y0, x1, y1)


def panel_fill(content, window):
    """איזה חלק מהפאנל תופסת התיבה החוסמת של התוכן, אחרי התאמת יחס.

    זהו המדד לכשל ה"רצועה": תוכן רחב ושטוח בפאנל פורטרטי מקבל
    letterbox ומצטמצם לפס דק. מדד זה תופס בדיוק את זה.
    """
    cw = max(content[2] - content[0], 1e-9)
    ch = max(content[3] - content[1], 1e-9)
    ww = max(window[2] - window[0], 1e-9)
    wh = max(window[3] - window[1], 1e-9)
    return (cw * ch) / (ww * wh)


def main_body(points):
    """מפריד את גוף התוכנית מגושים מרוחקים, ומחזיר (גוף, מרוחקים).

    מקרא גופי התאורה מצויר לעיתים עשרות אלפי יחידות מהבניין:
    ב-111 (2).dxf הוא ב-x=-228,000 בעוד הבניין ב-x=792..7,345.
    אחוזונים אינם עוזרים כאן — המקרא הוא 7% מהגופים, ולכן אחוזון 2
    נופל בתוכו. הפרדה לפי פער על ציר X היא מה שעובד.
    """
    if len(points) < 5:
        return list(points), []
    groups = clusters(points, axis=0)
    if len(groups) <= 1:
        return list(points), []
    groups.sort(key=len, reverse=True)
    body = groups[0]
    rest = [p for g in groups[1:] for p in g]
    # אם ה"גוף" אינו רוב ברור, עדיף לא לזרוק כלום
    if len(body) < 0.5 * len(points):
        return list(points), []
    return body, rest


def legend_columns(points, codes, gap_frac=0.02, width_frac=0.01,
                   min_kinds=4, max_n=40, kinds_ratio=0.3):
    """אינדקסים של גופים שהם מקרא, לא תאורה של חדר (D-044).

    המקרא מצויר לעיתים **ליד** הבניין ולא הרחק ממנו, ואז `main_body`
    משאיר אותו, והוא הוצע כאזור. צורתו קבועה: עמודה צרה וגבוהה, עם
    הרבה סוגי גופים שונים ומעט מכל סוג. נמדד: `111 (2)` — 12 גופים,
    8 סוגים, ברוחב 55; `1` — 21 גופים, 15 סוגים; `3` — 12 גופים, 5 סוגים.
    עמודות צרות אמיתיות (שורת TA1, פס LINE) הן מסוג אחד או שניים,
    ולכן `min_kinds` מפריד ביניהן. ב-`2` אין מקרא, ולא נמצא דבר.
    """
    if len(points) < 5:
        return set()
    order = sorted(range(len(points)), key=lambda i: points[i][0])
    xs = [points[i][0] for i in order]
    width = xs[-1] - xs[0]
    if width <= 0:
        return set()
    cols, cur = [], [order[0]]
    for a, b in zip(order, order[1:]):
        if points[b][0] - points[a][0] > gap_frac * width:
            cols.append(cur)
            cur = []
        cur.append(b)
    cols.append(cur)
    out = set()
    for c in cols:
        cx = [points[i][0] for i in c]
        cy = [points[i][1] for i in c]
        w, h = max(cx) - min(cx), max(cy) - min(cy)
        kinds = len({codes[i] for i in c})
        if (w < width_frac * width and h > 5 * max(w, 1) and len(c) <= max_n
                and kinds >= min_kinds and kinds / len(c) >= kinds_ratio):
            out.update(c)
    return out


def clusters(points, axis=1, factor=4.0, min_span_frac=0.08):
    """מפצל נקודות לאשכולות לפי פערים ריקים גדולים לאורך ציר.

    בשרטוטי הסטודיו כמה קומות יושבות זו מעל זו באותו קובץ, ומסגור
    של כולן יחד מייצר שקופית חסרת תועלת.

    המבחן הוא מרווח אופייני בין גופים, לא הפריסה הכוללת: בתוך קומה
    הגופים מרוחקים מאות יחידות זה מזה, ובין קומות אלפים. סף יחסי
    לפריסה האנכית חתך חדר אחד לחמישה, וסף יחסי לרוחב לא זיהה קומות
    כלל — שניהם נוסו ונכשלו על הנתונים האמיתיים.
    """
    if len(points) < 3:
        return [list(points)]
    ordered = sorted(points, key=lambda p: p[axis])
    seq = [p[axis] for p in ordered]
    span = seq[-1] - seq[0]
    if span <= 0:
        return [list(points)]
    gaps = [seq[i + 1] - seq[i] for i in range(len(seq) - 1)]
    spacing = [g for g in gaps if g > 1e-9]
    typical = sorted(spacing)[len(spacing) // 2] if spacing else span
    threshold = max(typical * factor, span * min_span_frac)
    out, cur = [], [ordered[0]]
    for i, g in enumerate(gaps):
        if g > threshold:
            out.append(cur)
            cur = []
        cur.append(ordered[i + 1])
    out.append(cur)
    return [c for c in out if c]


def _bounds(points):
    """(גבולות החלון, כמה נקודות מושמטות כחריגות).

    קודם החלון נגזר תמיד מאחוזונים 2%–98%, וגם גוף אמיתי בקצה החדר
    נחתך מחוץ לשקופית בלי שום אזהרה (B-02: שני גופי FOIL דולקים בקומה
    עליונה, פס לינארי בקומת כניסה). עכשיו לוקחים את כל הנקודות —
    **חוץ ממקרה אחד:** פיזור גדול פי 5 ויותר מהפיזור הרגיל (אחוזונים),
    באחד הצירים, פירושו גוף תועה: מקרא שנשאר בתוך המלבן, או חריג מ-1.dxf
    שהיה במיליונים. אז מושמטים רק מי שרחוק מהגוף הראשי יותר מרוחבו
    של הגוף הראשי עצמו — גוף אמיתי בקצה נשאר בפנים גם אז.
    ציר שבו כל הנקודות על קו אחד אינו נחשב: הפיזור הפנימי שלו אפס.
    """
    xs = sorted(p[0] for p in points)
    ys = sorted(p[1] for p in points)

    def pct(a, q):
        return a[max(0, min(len(a) - 1, int(round(q * (len(a) - 1)))))]

    tx0, tx1 = pct(xs, 0.02), pct(xs, 0.98)
    ty0, ty1 = pct(ys, 0.02), pct(ys, 0.98)
    raw = (xs[0], ys[0], xs[-1], ys[-1])

    def far(r0, r1, t0, t1):
        return (t1 - t0) > 0 and (r1 - r0) > 5 * (t1 - t0)
    if not (far(raw[0], raw[2], tx0, tx1) or far(raw[1], raw[3], ty0, ty1)):
        return raw, 0

    def ok(v, t0, t1):
        span = t1 - t0
        return span <= 0 or (t0 - span <= v <= t1 + span)
    core = [(x, y) for x, y in points if ok(x, tx0, tx1) and ok(y, ty0, ty1)]
    if not core:                     # לא אמור לקרות; עדיף חלון מחתך אחוזונים
        return (tx0, ty0, tx1, ty1), len(points)
    cx = [p[0] for p in core]
    cy = [p[1] for p in core]
    return (min(cx), min(cy), max(cx), max(cy)), len(points) - len(core)


def far_outlier_count(points):
    """לא בשימוש מאז שאזור ממוסגר לפי המלבן שנגזר (השרת סופר במקומו
    גופים שנחתכים בקצה, `server._cut_at_edge`). נשאר לבדיקות של `_bounds`.

    כמה גופים ייוותרו מחוץ לחלון כי הם רחוקים מדי (0 = כולם בפנים).

    משמש את שלב 3: חריג שמושמט מוצג לעובד, לא נבלע בשקט.
    """
    return _bounds(points)[1] if points else 0


def frame_for(points, panel_px, min_fill=0.18, min_px_per_unit=None):
    """מחשב חלון צפייה סביב קבוצת נקודות (בדרך כלל גופי התאורה שנבחרו).

    points — [(x, y), ...] ביחידות השרטוט
    """
    warnings = []
    if not points:
        raise ValueError("לא נבחרו גופים — אין ממה לגזור חלון צפייה")

    tight, dropped = _bounds(points)
    if dropped:
        warnings.append(
            "נמצאו גופים חריגים הרחק משאר התוכנית; המסגור מתעלם מהם. "
            "כדאי לבדוק את השרטוט.")

    pw, ph = panel_px
    aspect = pw / ph
    win = expand_to_aspect(tight, aspect)

    win_w = win[2] - win[0]
    win_h = win[3] - win[1]
    scale = min(pw / win_w, ph / win_h)
    fill = panel_fill(tight, win)

    groups = clusters(points, axis=1)
    if len(groups) > 1:
        sizes = ", ".join(str(len(g)) for g in sorted(groups, key=len, reverse=True))
        warnings.append(
            f"הגופים מתפרסים על {len(groups)} אזורים מרוחקים ({sizes} גופים) — "
            f"קומות או חדרים נפרדים. מסגור של כולם יחד מקטין כל אחד. "
            f"כדאי להפיק שקופית לכל אזור.")

    if fill < min_fill:
        warnings.append(
            f"החיתוך דליל: התוכן תופס רק {fill*100:.0f}% משטח הפאנל, "
            f"כי יחס הממדים שלו ({(tight[2]-tight[0])/max(tight[3]-tight[1],1e-9):.1f}) "
            f"רחוק מיחס הפאנל ({pw/ph:.1f}). התוצאה תהיה רצועה דקה. "
            f"כדאי לבחור אזור שמתאים לצורת הפאנל, או לפצל לשתי שקופיות.")

    if min_px_per_unit and scale < min_px_per_unit:
        warnings.append(
            f"קנה המידה קטן מדי ({scale:.3f} פיקסל ליחידה) — פרטים לא ייקראו.")

    return Framing(window=win, panel_px=panel_px, scale=scale,
                   fill_ratio=fill, warnings=warnings)
