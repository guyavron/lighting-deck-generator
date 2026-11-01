"""תצוגה מקדימה של השקופית — מאותה גיאומטריה שמייצרת את ה-PPTX.

גיא, אחרי המצגת הראשונה: "השרטוטים והתמונות לא מסודרים בצורה טובה,
בגלל זה חשוב אפשרות לתצוגה מקדימה של השקופית לפני הפקת מצגת."

**התצוגה חייבת לשקר פחות מהמצגת, לא יותר.** לכן היא אינה מציירת
פריסה משלה: היא מקבלת את התוצאה של `slide.resolve`, בדיוק זו
ש-`build_pptx` מקבל, ומציירת אותה על קנבס בגודל שנמדד (2000x1125).
מה שרואים כאן הוא מה שייצא — ואם הפריסה תשתנה יום אחד, שתי הדרכים
ישתנו יחד.

הרקע שחור טהור, כמו רקע השקופית וכמו רקע התוכנית, ולכן ההרכבה כאן
זהה פיקסלית להרכבה ב-PowerPoint (D-016).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

FONTS = ("assistant.ttf", "arial.ttf", "segoeui.ttf")


def _font(size):
    for n in FONTS:
        p = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _rtl(text):
    """PIL אינו עושה סידור דו-כיווני. לתצוגה פנימית די בהיפוך.

    זה משפיע רק על התצוגה המקדימה — ב-PPTX הטקסט אמיתי ו-PowerPoint
    מסדר אותו בעצמו לפי rtl.
    """
    if not any("\u0590" <= c <= "\u05ff" for c in text):
        return text
    out = []
    for tok in text.split(" "):
        letters = [c for c in tok if c.isalpha()]
        if letters and all("\u0590" <= c <= "\u05ff" for c in letters):
            out.append(tok[::-1])
        else:
            out.append(tok)
    return " ".join(reversed(out))


def render(plan_img, title, photos, layout, geom, cards=None):
    """שקופית אחת כתמונה.

    `plan_img`  פאנל התוכנית עם ההארה
    `photos`    נתיבי קבצים, עד שלושה
    `geom`      התוצאה של `slide.resolve` — **בדיוק זו שהייצוא מקבל**

    **הגיאומטריה מגיעה מבחוץ ולא מחושבת כאן.** קודם הפאנל רונדר
    ביחס אחד ונמתח לתיבה של יחס אחר, וכפיית "רחבה" עיוותה את
    התוכנית בתצוגה בלבד. תצוגה שמשקרת דווקא בכפייה ידנית חסרת ערך.

    הכותרת מצוירת כאן בגופן חלופי ובהיפוך ידני, ולכן היא נאמנה
    במיקום ולא בצורת האותיות. הממשק מרכיב את השקופית בדפדפן עם
    הגופן האמיתי; המסלול הזה קיים כדי שהגיאומטריה תהיה בדיקה של
    השרת ולא הבטחה של הדפדפן.
    """
    from slide import hex_rgb
    c = layout["canvas"]
    W, H = c["width_px"], c["height_px"]
    # צבעי הסגנון (D-050). בשחור: רקע שחור, כותרת ופס לבנים, כמו קודם.
    canvas = Image.new("RGB", (W, H), hex_rgb(c.get("background"), (0, 0, 0)))
    d = ImageDraw.Draw(canvas)
    tcol = hex_rgb(layout["title"].get("color"), (255, 255, 255))
    rcol = hex_rgb(layout["header_rule"].get("color"), (255, 255, 255))
    card = (layout.get("photo_card") or {}).get("color")

    box = geom["plan"]
    if plan_img is not None and box:          # תצלומים בלבד: אין תוכנית
        if plan_img.size != (box[2], box[3]):
            plan_img = plan_img.resize((box[2], box[3]), Image.LANCZOS)
        canvas.paste(plan_img, (box[0], box[1]))

    for k, fr in enumerate(geom.get("frames") or []):
        if card and fr and cards and k < len(cards) and cards[k]:
            d.rectangle([fr[0], fr[1], fr[0] + fr[2], fr[1] + fr[3]], fill=hex_rgb(card))

    for rect, path in zip(geom["photos"], photos):
        if not rect:
            continue
        try:
            im = Image.open(path).convert("RGB")
        except Exception:
            continue
        x, y, w, h = rect
        canvas.paste(im.resize((max(w, 1), max(h, 1)), Image.LANCZOS), (x, y))

    if geom.get("rule"):
        rx, ry, rw, rh = geom["rule"]
        d.rectangle([rx, ry, rx + rw, ry + rh], fill=rcol)

    tx, ty, tw, th = geom["title"]["box"]
    size = max(6, int(round(geom["title"]["sizes"][0] * H / 540.0)))
    if geom["title"].get("rtl", True):
        d.text((tx + tw, ty), _rtl(title or ""),
               fill=tcol, font=_font(size), anchor="ra")
    else:
        d.text((tx, ty), title or "", fill=tcol, font=_font(size),
               anchor="la")
    return canvas
