"""הרכבת השקופית וכתיבת PPTX בר-עריכה.

המצגת אינה נצרבת לתמונה אחת. פאנל התוכנית+ההארה הוא רסטר (הוא ממילא
רסטר), אבל הוא מונח כתמונה נפרדת ב-PowerPoint יחד עם הכותרת, וכל
השאר נשאר בר-עריכה.

זה אפשרי כי רקע השקופית שחור טהור (schemeClr tx1) ורקע פאנל התוכנית
שחור טהור, ולכן ההרכבה ב-PowerPoint זהה פיקסלית להרכבה בפוטושופ.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime

import yaml
from PIL import Image
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")

A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_layout(style=None):
    """גיאומטריית השקופית. `style` — סגנון המצגת (D-050): "black" או
    ריק = מה שנמדד במצגות השחורות; שם אחר נלקח מ-`deck_styles` ומוזג
    מעל הבסיס, כך שסגנון מגדיר רק את מה שהוא משנה.
    """
    with open(os.path.join(KNOWLEDGE, "layout.yaml"), encoding="utf-8") as fh:
        base = yaml.safe_load(fh)
    over = (base.get("deck_styles") or {}).get(style or "")
    if not over:
        return base
    over = {k: v for k, v in over.items() if k not in ("label",)}
    out = _merge(base, over)
    out["style"] = style
    return out


def hex_rgb(h, default=(0, 0, 0)):
    h = (h or "").lstrip("#")
    if len(h) != 6:
        return default
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def plan_panel_box(content_aspect, layout, alone=False, align="left"):
    """גודל ומיקום פאנל התוכנית, מותאם ליחס הממדים של התוכן.

    בייחוס הפאנל משתנה בין פרויקטים ולא נשאר קבוע:
      • בניין צר וגבוה  -> עמודה שמאלית צרה (DECK B: 332x878, יחס 0.38)
      • דירה רחבה       -> פאנל רחב שתופס רוב השקופית (מצגת 2024: ~65%)
    לכן הפאנל נגזר מהתוכן. אם כופים תמיד עמודה צרה, תוכנית רחבה
    מצטמצמת לרצועה — נמדד בפועל: קומה ביחס 3.7 קיבלה 489x132.

    `align="center"` — באמצע **החלק השמאלי** (D-047): המלבן שבין
    השוליים (4%) לרוחב המרבי של התוכנית, לרוחב ולגובה. ברירת המחדל
    היא צמוד לפינה השמאלית העליונה, כמו שנמדד.
    """
    p = layout["plan_panel"]
    ph = layout["photo_area"]
    c = layout["canvas"]
    x0, y0 = p["x"], p["y"]
    max_h = p["height"]

    # התצלומים תמיד מימין; מה שמשתנה הוא כמה רוחב התוכנית לוקחת.
    narrow_w = p.get("max_width_narrow", 489)
    wide_w = p.get("max_width_wide", 1212)
    max_w = narrow_w if content_aspect <= p.get("wide_threshold_aspect", 1.4) else wide_w
    # `alone` — שקופית בלי תצלומים (D-031). אין מה שיחלוק את הרוחב,
    # ולכן התוכנית מקבלת את כל רוחב התוכן, מ-4% עד 96%, וממורכזת.
    # בלי זה שקופית פתיחה של תת-אזור הייתה תוכנית בצד שמאל וחצי
    # שקופית שחורה.
    if alone:
        max_w = ph["x_end"] - x0
    w = min(max_w, max_h * content_aspect)
    h = w / content_aspect
    if h > max_h:
        h, w = max_h, max_h * content_aspect
    if alone:
        x0 = x0 + (ph["x_end"] - x0 - w) / 2
    elif align == "center":
        x0 = x0 + (max_w - w) / 2
        y0 = y0 + (max_h - h) / 2
    return int(x0), int(y0), int(w), int(h)


def compose(plan_img, layout, panel_xy):
    """מניח את פאנל התוכנית על קנבס שחור בגודל השקופית."""
    c = layout["canvas"]
    canvas = Image.new("RGB", (c["width_px"], c["height_px"]), (0, 0, 0))
    canvas.paste(plan_img, (panel_xy[0], panel_xy[1]))
    # קו הכותרת הלבן — אלמנט קבוע בכל שקופיות התוכן
    hr = layout["header_rule"]
    rule = Image.new("RGB", (hr["width"], hr["height"]),
                     tuple(int(hr["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    canvas.paste(rule, (hr["x"], hr["y"]))
    return canvas


def photo_boxes(plan_box, layout, n):
    """מיקומי התצלומים בצד ימין, לפי המידות שנמדדו בייחוס.

    התצלומים תמיד מימין, נגמרים תמיד ב-x=1921 (96%), ומתחילים אחרי
    פער מפאנל התוכנית. ראה knowledge/layout.yaml.
    """
    ph = layout["photo_area"]
    px, py, pw, phgt = plan_box
    gap = ph.get("min_gap_from_plan", 60)
    x0 = px + pw + max(gap, 60)
    x1 = ph["x_end"]
    y0, y1 = ph["y"], ph["y"] + ph["height"]
    W, H = x1 - x0, y1 - y0
    if W < 120 or n <= 0:
        return []
    if n == 1:
        return [(x0, y0, W, H)]
    if n == 2:
        h = (H - 24) // 2
        return [(x0, y0, W, h), (x0, y0 + h + 24, W, h)]
    # שלושה: אחד גדול למעלה, שניים קטנים מתחת — הדפוס שנמדד במצגת 2024
    top_h = int(H * 0.6)
    half = (W - 24) // 2
    bot_h = H - top_h - 24
    return [(x0, y0, W, top_h),
            (x0, y0 + top_h + 24, half, bot_h),
            (x0 + half + 24, y0 + top_h + 24, half, bot_h)]


def photos_only_boxes(sizes, layout):
    """תיבות לשקופית תצלומים בלבד (D-035) — שורה אחת, ממורכזת.

    אותו גובה לכולם, כל תצלום ביחס שלו, רווחים שווים. אם השורה
    רחבה מהשטח — הגובה קטן עד שהיא נכנסת, ואז היא ממורכזת גם
    בגובה. נמדד במצגת ייחוס א; ראה knowledge/layout.yaml.
    """
    po = layout["photos_only"]
    sizes = [s for s in sizes if s and s[0] > 0 and s[1] > 0][:po.get("max_photos", 3)]
    if not sizes:
        return []
    gap, x0, x1 = po["gap"], po["x"], po["x_end"]
    h = float(po["height"])
    ratios = [w / hh for w, hh in sizes]
    room = (x1 - x0) - gap * (len(sizes) - 1)
    if sum(ratios) * h > room:
        h = room / sum(ratios)
    widths = [r * h for r in ratios]
    total = sum(widths) + gap * (len(sizes) - 1)
    x = x0 + ((x1 - x0) - total) / 2
    y = po["y"] + (po["height"] - h) / 2
    out = []
    for w in widths:
        out.append((int(round(x)), int(round(y)), int(round(w)), int(round(h))))
        x += w + gap
    return out


def _fit(box, img_size):
    """התאמת תמונה לתיבה בלי מתיחה ובלי חיתוך, ממורכזת."""
    bx, by, bw, bh = box
    iw, ih = img_size
    scale = min(bw / iw, bh / ih)
    w, h = int(iw * scale), int(ih * scale)
    return (bx + (bw - w) // 2, by + (bh - h) // 2, w, h)


# ─── פריסה ידנית ─────────────────────────────────────────────────
#
# D-020: המתכנן מזיז ומשנה גודל בתצוגה, לא ב-PowerPoint.
#
# הפריסה האוטומטית נשארת נקודת הפתיחה — היא נמדדה מ-5 מצגות והיא
# נכונה ברוב המקרים. מה שנוסף הוא **דריסה**: תיבה שאדם הזיז גוברת
# על החישוב, ורק היא. מה שלא נגעו בו ממשיך לזרום אוטומטית.
#
# **כל המספרים כאן בקואורדינטות הקנבס (2000x1125).** זו יחידת
# המידה היחידה בין הדפדפן, התצוגה והייצוא. מי שמכניס פיקסלים של
# מסך או אחוזים לתוך המבנה הזה — שובר את השרשרת.


def _as_box(v):
    """[x,y,w,h] מכל צורה סבירה, או None. רוחב או גובה אפס = אין."""
    if not v or len(v) < 4:
        return None
    try:
        x, y, w, h = (float(v[i]) for i in range(4))
    except (TypeError, ValueError):
        return None
    if w < 1 or h < 1:
        return None
    return (int(round(x)), int(round(y)), int(round(w)), int(round(h)))


def _locked_plan(box, auto_plan, canvas):
    """תיבת התוכנית שאדם קבע, ביחס הממדים של הרסטר עצמו.

    **יחס הממדים נעול — וכאן הוא נאכף, לא רק בגרירה.** גיא, 12.10:
    אחרי סיבוב "התוכנית נמרחה", ושתיים מתשע שקופיות במצגת יצאו
    מעוותות. התיבה שנגררה נשמרה ביחס של לפני הסיבוב, והרסטר המסובב
    נמתח אליה: 1212x330 בתיבה ביחס 0.27, ו-273x878 בתיבה ביחס 3.2.
    `auto_plan` הוא תמיד ביחס הרסטר (הוא נגזר ממנו), ולכן הוא המידה.

    כשהיחס שגוי: שומרים את המרכז ואת השטח, מתקנים את היחס, ומקטינים
    אם צריך עד שהתיבה נכנסת לשקופית — סיבוב של תוכנית רחבה בגובה
    מלא היה מוציא אותה מהשקופית, וזה ה"קפיצה" שגיא ראה.
    """
    if not box:
        return None
    x, y, w, h = box
    want = auto_plan[2] / max(auto_plan[3], 1)
    if abs((w / h) / want - 1) <= 0.02:
        return box
    cx, cy = x + w / 2, y + h / 2
    area = w * h
    nw = (area * want) ** 0.5
    nh = nw / want
    cw, ch = canvas["width_px"], canvas["height_px"]
    k = min(1.0, cw / nw, ch / nh)
    nw, nh = nw * k, nh * k
    nx = min(max(cx - nw / 2, 0), cw - nw)
    ny = min(max(cy - nh / 2, 0), ch - nh)
    return (int(round(nx)), int(round(ny)), int(round(nw)), int(round(nh)))


def title_layout(n_lines, layout, override=None, rtl=True):
    """תיבת הכותרת וגדלי הגופן — **חישוב אחד לתצוגה ולייצוא**.

    נמדד בייחוס: התיבה יושבת top=39-41 בגובה 50, כלומר תחתית 89-91,
    וקו הכותרת ב-91. הכותרת נעצרת בקו ולא חוצה אותו. תיבה גבוהה מדי
    חוצה אותו — זה קרה בפועל (תחתית 153).

    קודם היו כאן שתי נוסחאות: הייצוא חישב תיבה, והתצוגה ציירה טקסט
    ב-`hr.y - size*1.35`. שתיהן נתנו כמעט אותו דבר, וזה בדיוק הסוג
    של "כמעט" שמתפוצץ בשקט אחרי שינוי אחד.
    """
    c = layout["canvas"]
    hr = layout["header_rule"]
    t = layout["title"]
    W, H = c["width_px"], c["height_px"]
    pt_px = H / 540.0                      # 7.5 אינץ' = 540 נקודות
    avail = hr["y"] - 8                    # מרווח נשימה מעל הקו

    ov = override or {}
    base = ov.get("pt")
    if base:
        sizes = [float(base)] * max(1, n_lines)
        if n_lines > 1:
            sizes = [float(base)] + [float(base) * 9.0 / 11.0] * (n_lines - 1)
    else:
        sizes = [float(x) for x in title_sizes(n_lines, t["size_pt"])]
        # הכותרת חייבת להיכנס מעל הקו. מכווצים עד שנכנס, במקום להניח
        # שהמתכנן לא יכתוב ארבע שורות.
        while sum(x * 1.2 for x in sizes) * pt_px > avail and sizes[0] > 6:
            sizes = [max(6.0, x - 1) for x in sizes]

    h = sum(x * 1.2 for x in sizes) * pt_px + 6
    if not base:
        h = min(h, avail)
    width = ov.get("w") or W * 0.34
    right = t["right_edge_pct"] / 100.0 * W
    # עברית נצמדת לקצה הימני, אנגלית לקצה השמאלי של קו הכותרת (4%).
    # נמדד במצגת ייחוס א: כל 227 הכותרות באנגלית מתחילות ב-3.6%.
    auto_x = (right - width) if rtl else hr["x"]
    x = ov.get("x")
    y = ov.get("y")
    box = (int(round(x if x is not None else auto_x)),
           int(round(y if y is not None else max(4, hr["y"] - h))),
           int(round(width)), int(round(h)))
    return box, sizes


def resolve(plan_box, layout, photo_sizes, n_title_lines=1, override=None,
            title_rtl=True, rule=True):
    """המיקומים הסופיים של כל רכיב בשקופית.

    `plan_box`     התיבה האוטומטית מ-`plan_panel_box`
    `photo_sizes`  [(w,h)] של התמונות בפועל, לצורך התאמה לתיבה
    `override`     {"plan":[x,y,w,h], "photos":[[x,y,w,h]|null],
                    "title":{"x","y","w","pt"}} — מה שאדם הזיז

    **התצוגה והייצוא קוראים לפונקציה הזו ולא מחשבים בעצמם.** זו
    הסיבה היחידה שהתצוגה אינה יכולה להראות משהו אחר ממה שייצא.

    `title_rtl`    הצד של הכותרת — לפי שפתה (`title_is_rtl`)
    `rule`         האם יש פס מתחת לכותרת. הגדרה של המצגת כולה.
    """
    ov = override or {}
    c = layout["canvas"]
    hr = layout["header_rule"]
    rule_box = ((hr["x"], hr["y"], hr["width"], max(hr["height"], 2))
                if rule else None)
    if plan_box is None:
        # שקופית תצלומים בלבד (D-035): אין תוכנית, והתצלומים בשורה
        autos = photos_only_boxes(photo_sizes, layout)
        ov_photos = ov.get("photos") or []
        photos = [(_as_box(ov_photos[i]) if i < len(ov_photos) else None) or
                  (autos[i] if i < len(autos) else None)
                  for i in range(len(photo_sizes))]
        frames = list(photos)
        tbox, sizes = title_layout(n_title_lines, layout, ov.get("title"),
                                   rtl=title_rtl)
        return {"canvas": (c["width_px"], c["height_px"]),
                "rule": rule_box,
                "auto_plan": None, "plan": None, "photos": photos,
                "frames": frames,
                "title": {"box": tbox, "sizes": [round(s, 2) for s in sizes],
                          "rtl": bool(title_rtl)}}
    auto_plan = tuple(int(v) for v in plan_box)
    plan = _locked_plan(_as_box(ov.get("plan")), auto_plan, c) or auto_plan

    # תיבות התצלומים נגזרות מהתוכנית **אחרי ההזזה** — מי שמצר את
    # התוכנית מצפה שהתצלומים יתרחבו. אבל תוכנית שנגררה ימינה עלולה
    # לא להשאיר מקום כלל, ואז התצלומים היו נעלמים בלי הסבר; במקרה
    # כזה חוזרים לפריסה האוטומטית.
    autos = photo_boxes(plan, layout, len(photo_sizes))
    if len(autos) < len(photo_sizes):
        autos = photo_boxes(auto_plan, layout, len(photo_sizes))

    ov_photos = ov.get("photos") or []
    photos = []
    # המסגרת של כל תצלום — שם יושב הריבוע האפור של תצלום מוצר
    # בסגנון האפור (D-050). בתיבה אוטומטית זו התיבה כולה, והתמונה
    # ממורכזת בתוכה; בתיבה שאדם גרר המסגרת היא התמונה עצמה.
    frames = []
    for i, size in enumerate(photo_sizes):
        manual = _as_box(ov_photos[i]) if i < len(ov_photos) else None
        if manual:
            photos.append(manual)
            frames.append(manual)
        elif i < len(autos):
            # תיבה אוטומטית היא מסגרת; התמונה ממורכזת בתוכה בלי מתיחה.
            # תיבה שאדם קבע היא התמונה עצמה, כי הוא גרר את פינותיה.
            photos.append(_fit(autos[i], size))
            frames.append(tuple(int(v) for v in autos[i]))
        else:
            photos.append(None)
            frames.append(None)

    tbox, sizes = title_layout(n_title_lines, layout, ov.get("title"),
                               rtl=title_rtl)
    return {
        "canvas": (c["width_px"], c["height_px"]),
        "rule": rule_box,
        "auto_plan": auto_plan,
        "plan": plan,
        "photos": photos,
        "frames": frames,
        "title": {"box": tbox, "sizes": [round(s, 2) for s in sizes],
                  "rtl": bool(title_rtl)},
    }


def title_sizes(n_lines, base_pt):
    """גדלי גופן לפי מספר השורות.

    שורה אחת: 14pt, כמו ברוב מצגות הייחוס. יותר משורה: 11 ואז 9,
    בעקבות מצגת ייחוס א שמשתמש ב-8 ו-11 לשתי שורות. גופן 14 בשתי שורות
    גולש מעבר לקו העליון.
    """
    if n_lines == 1:
        return [base_pt]
    return [11] + [9] * (n_lines - 1)


def is_hebrew(text):
    """האם הכותרת עברית. נמדד לפי אותיות, לא לפי ניחוש.

    מצגות המשרד לפעמים באנגלית מלאה — מצגת ייחוס א, הגדולה ביותר, כולה
    אנגלית. כותרת אנגלית עם rtl="1" מסתדרת הפוך: סימני פיסוק
    ומספרים קופצים לצד הלא נכון.
    """
    for c in text or "":
        if "֐" <= c <= "׿":
            return True
    return False


def title_is_rtl(text):
    """הצד של הכותרת: עברית מימין, אנגלית משמאל (גיא והסטודיו, 18.10).

    כותרת בלי אותיות בכלל נשארת מימין, כמו לפני הכלל.
    """
    if is_hebrew(text):
        return True
    return not any(ch.isalpha() for ch in text or "")


def _set_rtl(paragraph, align="r", rtl=True):
    """PowerPoint צריך rtl="1" מפורש, אחרת טקסט מעורב עברית/אנגלית נשבר.

    ולהפך: כותרת אנגלית חייבת rtl="0", אחרת היא נשברת באותה מידה.
    היישור נקבע לפי שפת הכותרת כולה (`title_is_rtl`). קודם הוא היה
    לימין תמיד, אבל במצגת ייחוס א, שכולה אנגלית, הכותרות מיושרות לשמאל.
    """
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("algn", align)
    pPr.set("rtl", "1" if rtl else "0")


def _hebrew_run(run, font, hebrew):
    """שפה וגופן עברי לקטע טקסט.

    **נתפס בפתיחה ב-PowerPoint עצמו (19.10), והיה כך מאז ומעולם:**
    `font.name` קובע רק את הגופן הלטיני. אותיות עבריות הן "complex
    script" ב-PowerPoint, ובלי `<a:cs>` הן נכתבו בגופן ברירת המחדל ולא
    ב-Assistant Light. ובלי `lang`, מספר שליד "|" עבר לצד הלא נכון:
    "אזור 1 | פס" הוצג "אזור | 1פס". מצגת ייחוס ו, שנכתבה ב-PowerPoint,
    מגדירה את שניהם: `lang` ו-`<a:latin>` + `<a:cs>` באותו גופן.
    """
    rPr = run._r.get_or_add_rPr()
    rPr.set("lang", "he-IL" if hebrew else "en-US")
    # **בלי altLang, ועם "גופן עברי" (charset=-79) — כמו מצגת ייחוס ו ומצגת ייחוס ב** (גיא,
    # 25.10). כשהגופן מגיע מהענן של מיקרוסופט, `altLang="en-US"` ובלי charset
    # גרמו ל-PowerPoint לעוות אותיות: "קומה" ← "ק מה". כל אחד מהשניים לבדו תיקן
    # בבדיקה על המצגת של גיא; עושים את שניהם, כמו מצגות הסטודיו.
    rPr.attrib.pop("altLang", None)
    cs = rPr.find(f"{{{A}}}cs")
    if cs is None:
        cs = etree.SubElement(rPr, f"{{{A}}}cs")
    cs.set("typeface", font)
    if hebrew:
        for e in (rPr.find(f"{{{A}}}latin"), cs):
            if e is not None:
                e.set("pitchFamily", "2")
                e.set("charset", "-79")


def _black_background(slide, color="#000000"):
    """רקע השקופית. שחור = `schemeClr tx1`, כמו בכל 295 שקופיות הייחוס;
    כל צבע אחר (הסגנון האפור, D-050) — `srgbClr` מפורש."""
    bg = etree.SubElement(slide._element, f"{{{A}}}__tmp")
    slide._element.remove(bg)
    h = (color or "#000000").lstrip("#").upper()
    fill = ('<a:schemeClr val="tx1"/>' if h == "000000"
            else '<a:srgbClr val="%s"/>' % h)
    xml = (
        '<p:bg xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        f'xmlns:a="{A}"><p:bgPr><a:solidFill>{fill}</a:solidFill>'
        '<a:effectLst/></p:bgPr></p:bg>'
    )
    el = etree.fromstring(xml)
    cSld = slide._element.find(
        "{http://schemas.openxmlformats.org/presentationml/2006/main}cSld")
    cSld.insert(0, el)


def geometry_for(spec, layout):
    """הגיאומטריה של שקופית אחת — מהדריסה אם יש, ואחרת אוטומטית.

    מאפשר לקוראים ותיקים (`make_deck`, `make_slide`) להעביר `plan_box`
    בלבד ולקבל את אותה תוצאה שהממשק מקבל.
    """
    if spec.get("geom"):
        return spec["geom"]
    sizes = []
    for p in spec.get("photos", []):
        sizes.append(_image_size(p))
    return resolve(spec["plan_box"], layout, sizes,
                   n_title_lines=max(1, len(spec["title_lines"])),
                   override=spec.get("override"),
                   title_rtl=title_is_rtl(" ".join(spec["title_lines"])),
                   rule=spec.get("rule", True))


def _image_size(path):
    try:
        from PIL import Image as _I
        with _I.open(path) as im:
            return im.size
    except Exception:
        return (4, 3)


def build_pptx(out_path, slides, layout):
    """slides — [{plan, plan_box|geom, photos:[path], title_lines}]

    כל רכיב מונח כאובייקט PPTX נפרד: התוכנית, כל תצלום, קו הכותרת
    והכותרת. אין תמונה מלאת-פריים.

    זו סטייה מכוונת ממבנה הייחוס. שם השקופית היא תמונה מרוכבת אחת
    מפני שפוטושופ מחייב זאת — לא מפני שזה עדיף. מכיוון שרקע השקופית
    ורקע התוכנית שחורים טהורים, הרכבה ב-PowerPoint זהה פיקסלית,
    והמתכנן יכול להזיז ולשנות גודל של התוכנית ושל כל תצלום בנפרד.

    **המיקומים מגיעים מ-`resolve` ולא מחושבים כאן.** קודם הייתה
    כאן נוסחה שנייה לתיבת הכותרת, שונה מזו שהתצוגה ציירה. כל עוד
    יש שתי נוסחאות, יום אחד הן ייפרדו.
    """
    c = layout["canvas"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(c["slide_emu"][0]), Emu(c["slide_emu"][1])
    blank = prs.slide_layouts[6]
    t = layout["title"]

    for spec in slides:
        s = prs.slides.add_slide(blank)
        _black_background(s, c.get("background"))
        cx = prs.slide_width / c["width_px"]
        cy = prs.slide_height / c["height_px"]
        geom = geometry_for(spec, layout)

        # קו הכותרת — מלבן דק, לא צרוב. כבוי = None (הגדרת המצגת)
        from pptx.enum.shapes import MSO_SHAPE
        if geom.get("rule"):
            rx, ry, rw, rh = geom["rule"]
            rule = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(rx * cx)),
                                      Emu(int(ry * cy)), Emu(int(rw * cx)),
                                      Emu(int(rh * cy)))
            rule.fill.solid()
            hexcol = layout["header_rule"]["color"].lstrip("#")
            rule.fill.fore_color.rgb = RGBColor(*[int(hexcol[i:i+2], 16) for i in (0, 2, 4)])
            rule.line.fill.background()
            rule.shadow.inherit = False

        # התוכנית כתמונה נפרדת במיקומה, ולא כתמונה מלאת-פריים
        if spec.get("plan"):
            bx, by, bw, bh = geom["plan"]
            s.shapes.add_picture(spec["plan"], Emu(int(bx * cx)), Emu(int(by * cy)),
                                 width=Emu(int(bw * cx)), height=Emu(int(bh * cy)))

        # **התיבה היא התמונה.** `resolve` כבר מרכז תיבה אוטומטית סביב
        # התמונה; תיבה שאדם גרר את פינותיה היא כבר המלבן שהוא רוצה.
        # התאמה נוספת כאן הייתה מזיזה את מה שהוא הניח.
        # ריבוע מאחורי תצלום מוצר — רק בסגנון שמגדיר אותו (D-050)
        card = (layout.get("photo_card") or {}).get("color")
        cards = spec.get("cards") or []
        for k, fr in enumerate(geom.get("frames") or []):
            if card and fr and k < len(cards) and cards[k]:
                rx, ry, rw, rh = fr
                sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(rx * cx)),
                                        Emu(int(ry * cy)), Emu(int(rw * cx)),
                                        Emu(int(rh * cy)))
                sh.fill.solid()
                sh.fill.fore_color.rgb = RGBColor(*hex_rgb(card))
                sh.line.fill.background()
                sh.shadow.inherit = False
        for box, path in zip(geom["photos"], spec.get("photos", [])):
            if not box:
                continue
            fx, fy, fw, fh = box
            s.shapes.add_picture(path, Emu(int(fx * cx)), Emu(int(fy * cy)),
                                 width=Emu(int(fw * cx)), height=Emu(int(fh * cy)))

        tx, ty, tw, th = geom["title"]["box"]
        sizes = geom["title"]["sizes"]
        tb = s.shapes.add_textbox(Emu(int(tx * cx)), Emu(int(ty * cy)),
                                  Emu(int(tw * cx)), Emu(int(th * cy)))
        tf = tb.text_frame
        tf.word_wrap = True
        # **כל השוליים אפס.** PowerPoint מוסיף 0.1 אינץ' לצדדים כברירת
        # מחדל, כלומר 15 פיקסלים בקואורדינטות הקנבס — והכותרת נחתה
        # ב-95.9% במקום ב-96.7% שנמדד. עכשיו קצה התיבה הוא קצה הטקסט,
        # וזה מה שהתצוגה מציירת.
        tf.margin_top = tf.margin_bottom = 0
        tf.margin_left = tf.margin_right = 0
        for i, line in enumerate(spec["title_lines"]):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            run = para.add_run()
            run.text = line
            # שורה אחת: 14pt כמו ברוב הייחוס. יותר משורה: 11/9pt,
            # כמו מצגת ייחוס א שמשתמש ב-8 ו-11 לשתי שורות. גופן 14 בשתי
            # שורות גולש מעבר לקו.
            run.font.size = Pt(sizes[i] if i < len(sizes) else sizes[-1])
            run.font.name = t["font"]
            run.font.color.rgb = RGBColor(*hex_rgb(t.get("color"), (255, 255, 255)))
            _hebrew_run(run, t["font"], is_hebrew(line))
            _set_rtl(para, align="r" if geom["title"].get("rtl", True) else "l",
                     rtl=is_hebrew(line))
    # **כותבים לשם זמני ורק בסוף מחליפים** (B-03). שמירה ישירה לשם
    # הסופי השאירה, אחרי קריסה או כיבוי באמצע, קובץ `deck_….pptx` שבור
    # שנראה כמו כל מצגת. כך: או מצגת שלמה או כלום. אם הכתיבה נכשלת
    # נשאר קובץ `.partial` בלבד — הכלי לא מוחק (חוק ברזל 3).
    # אותו דפוס כמו `_write_atomic` של הפרויקטים.
    tmp_path = out_path + ".partial"
    prs.save(tmp_path)
    os.replace(tmp_path, out_path)
    return out_path


def write_manifest(path, data):
    data = dict(data)
    data["generated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return path


_stamp_lock = threading.Lock()
_stamp_taken = set()      # שמות שחולקו בתהליך הזה, גם אם הקובץ עוד לא נכתב


def stamped(directory, base, ext):
    """הכלי לעולם לא כותב מעל קובץ קיים — ראה CLAUDE.md, חוק ברזל 2.

    שתי הפקות באותה שנייה קיבלו קודם אותו שם, והשנייה כתבה מעל הראשונה
    (B-01). עכשיו שם שכבר חולק או שכבר קיים מקבל סיומת _2, _3 וכן הלאה.
    """
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    with _stamp_lock:
        n = 1
        while True:
            suffix = "" if n == 1 else f"_{n}"
            path = os.path.join(directory, f"{base}_{stamp}{suffix}{ext}")
            key = os.path.normcase(os.path.abspath(path))
            if key not in _stamp_taken and not os.path.exists(path):
                _stamp_taken.add(key)
                return path
            n += 1
