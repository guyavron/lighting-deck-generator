"""מנוע ההארה — שחזור של אפקט Outer Glow של פוטושופ.

ההארה במצגות הסטודיו אינה מכחול מטושטש אלא אפקט שכבה. חולצו 229
מופעים מקבצי ה-PSD, ראה knowledge/glow.yaml.

צינור פוטושופ ל-Outer Glow:
  1. לוקחים את ערוץ האלפא של הצורה
  2. מרחיבים אותו לפי Spread (אחוז מתוך Size) — החלק האטום גדל
  3. מטשטשים גאוסיאנית ביתרת הרדיוס
  4. מכפילים באטימות
  5. ממזגים ב-Screen עם צבע ההארה

הערה על שמות: בפורמט ה-PSD הסליידר "Spread" של Outer Glow נשמר בשדה
Ckmt, ש-psd-tools חושף בשם choke. השדה שהוא קורא לו spread אינו בשימוש
והוא 0 בכל 229 המופעים. לכן knowledge/glow.yaml משתמש ב-choke כ-Spread.
"""
from __future__ import annotations

import os

import yaml
from PIL import Image, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")

# יחס בין "Size" של פוטושופ לסטיית התקן של הגאוסיאן.
# ערך ברירת המחדל נטען מ-knowledge/glow.yaml. אינו קבוע תיאורטי —
# הוא מכויל אמפירית, ראה src/calibrate_glow.py.
SIZE_TO_SIGMA = 0.39


def load_presets(path=None):
    path = path or os.path.join(KNOWLEDGE, "glow.yaml")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def calibration(presets=None):
    """פרמטרי הכיול של המנוע, מתוך קובץ הידע."""
    presets = presets or load_presets()
    return presets.get("calibration", {})


def preset_for(project, lighting_type=None, presets=None):
    """פריסט ההארה של פרויקט, עם החריגים השיטתיים לפי סוג הגוף."""
    presets = presets or load_presets()
    base = dict(presets["defaults"])
    # `defaults` מחזיק רק את מה שזהה בכל 229 המופעים (screen, spread 0,
    # noise 0) — הצבע והגודל תמיד מגיעים מפרויקט. פרויקט ריק או לא
    # מוכר נופל ל-`default_project` ב-glow.yaml, שהוא המצגת החדשה
    # ביותר. קודם זה זרק KeyError ושקופית פשוט לא נוצרה.
    proj = presets["projects"].get(project)
    if proj is None:
        proj = presets["projects"][presets["default_project"]]
    base.update(proj)
    if lighting_type:
        for ov in presets.get("overrides", []):
            if any(m in lighting_type for m in ov["matches"]):
                base.update({k: v for k, v in ov.items()
                             if k not in ("name", "matches", "note")})
                base["override"] = ov["name"]
                break
    return base


def apply_slide_choice(preset, choice, presets=None):
    """הבחירה של שקופית אחת (D-051): צבע, גודל ועוצמה מתוך `per_slide`.

    ערך שאינו ברשימה — מתעלמים ממנו, ולא ממציאים. בלי בחירה הפריסט
    חוזר כמו שהוא, כך ששקופית שלא נגעו בה זהה לקודם.
    """
    if not choice:
        return preset
    cfg = (presets or load_presets()).get("per_slide") or {}
    out = dict(preset)
    colors = {c["color"].upper() for c in cfg.get("colors") or []}
    col = (choice.get("color") or "").upper()
    if col in colors:
        out["color"] = col
    f = ((cfg.get("sizes") or {}).get(choice.get("size") or "") or {}).get("factor")
    if f:
        out["size"] = preset["size"] * f
    f = ((cfg.get("power") or {}).get(choice.get("power") or "") or {}).get("factor")
    if f:
        if out.get("blend") == "normal":
            out["gain"] = preset.get("gain", 1.0) * f
        else:
            out["opacity"] = min(100.0, preset["opacity"] * f)
    return out


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def outer_glow_alpha(mask: Image.Image, size: float, spread: float) -> Image.Image:
    """ערוץ האלפא של ההארה עבור מסכת הצורה. mask הוא 'L'."""
    if size <= 0:
        return Image.new("L", mask.size, 0)
    grow = size * (spread / 100.0)
    remaining = max(size - grow, 0.0)
    m = mask
    if grow >= 1:
        # הרחבת המטה לפני הטשטוש — זה מה ש-Spread עושה
        r = int(round(grow))
        m = m.filter(ImageFilter.MaxFilter(2 * min(r, 10) + 1))
        if r > 10:                       # MaxFilter מוגבל לגרעין 21
            for _ in range((r - 10) // 10):
                m = m.filter(ImageFilter.MaxFilter(21))
    sigma = max(remaining * SIZE_TO_SIGMA, 0.01)
    return m.filter(ImageFilter.GaussianBlur(sigma))


def screen(base: Image.Image, top: Image.Image) -> Image.Image:
    """מיזוג Screen: 1-(1-a)(1-b)."""
    return ImageChops.screen(base, top)


def shape_for(f, to_panel, scale, radius):
    """הצורה שגוף אחד תורם למסכת ההארה.

    **מקום אחד שמתרגם גוף לצורה.** התצוגה, הייצוא וה-CLI קוראים לו,
    כדי שגוף לינארי לא יצא פס באחד ונקודה באחר.
    """
    kind = getattr(f, "kind", "point")
    if kind == "line" and getattr(f, "pts", None):
        return ("line", [to_panel(x, y) for x, y in f.pts])
    if kind == "circle" and getattr(f, "radius", 0):
        x, y = to_panel(f.x, f.y)
        return ("disc", x, y, max(f.radius * scale, radius))
    return to_panel(f.x, f.y)


def shape_key(sh):
    """מפתח מטמון יציב לצורה. `sorted` על נקודות לא עובד על צורות."""
    if sh and isinstance(sh[0], str):
        if sh[0] == "line":
            return ("line",) + tuple((round(x, 1), round(y, 1)) for x, y in sh[1])
        return ("disc", round(sh[1], 1), round(sh[2], 1), round(sh[3], 2))
    return ("pt", round(sh[0], 1), round(sh[1], 1))


def _gauss_blur(a, sigma):
    """טשטוש גאוסיאני בממשיים, בלי scipy. מוקטן פי 4 לפני, ומוגדל
    אחרי — ההארה חלקה ממילא, והמסה נשמרת (הקטנת BOX היא ממוצע)."""
    import numpy as np
    H, W = a.shape
    f = 4 if sigma >= 8 else 1
    if f > 1:
        small = Image.fromarray(a.astype("float32"), "F").resize(
            (max(1, W // f), max(1, H // f)), Image.BOX)
        a2 = np.asarray(small, dtype=np.float64)
    else:
        a2 = a
    s = sigma / f
    r = int(3 * s) + 1
    x = np.arange(-r, r + 1)
    k = np.exp(-x * x / (2 * s * s)); k /= k.sum()
    a2 = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 0, a2)
    a2 = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), 1, a2)
    if f > 1:
        a2 = np.asarray(Image.fromarray(a2.astype("float32"), "F").resize(
            (W, H), Image.BILINEAR), dtype=np.float64)
    return a2


def _render_glow_normal(mask, preset, base, stack):
    """הארה במיזוג רגיל, על רקע בהיר (הסגנון האפור, D-050).

    Screen אינו יכול להבהיר רקע בהיר כמעט בכלל — זה מה שראינו
    בהשוואה הראשונה, שבה ההארה נעלמה על אפור. במצגת ייחוס ו ההארה היא צבע
    שמנת שנצבע מעל הרקע, והערוץ הכחול אף יורד מתחת לרקע (225 → 217),
    מה ש-Screen לא יכול לעשות. הכיול ב-knowledge/layout.yaml.
    """
    import numpy as np
    m = np.asarray(mask, dtype=np.float64) / 255.0
    sigma = max(preset["size"] * SIZE_TO_SIGMA, 0.5)
    n = max(1, int(preset.get("stack", stack)))
    # **תקרה לאלפא** — השיא שנמדד במצגת ייחוס ו (0.6 אחרי השכפול). הכיול
    # נעשה על גוף נקודתי; פס לינארי מצטבר לאורכו, ובלי תקרה הוא הציף
    # חדר שלם בשמנת אטום (נתפס בהדמיית עובד, 19.10). עם התקרה פס זוהר
    # כמו נקודה, רק לכל אורכו.
    cap = 1 - (1 - float(preset.get("max_alpha", 1.0))) ** (1.0 / n)
    a = np.clip(preset.get("gain", 1.0) * _gauss_blur(m, sigma), 0, cap)
    a = 1 - (1 - a) ** n
    out = np.asarray(base, dtype=np.float64)
    col = np.array(_hex_to_rgb(preset["color"]), dtype=np.float64)
    out = out * (1 - a[..., None]) + col * a[..., None]
    img = Image.fromarray(np.clip(out + 0.5, 0, 255).astype("uint8"), "RGB")
    dot = Image.new("RGB", img.size, _hex_to_rgb(preset.get("marker_color") or preset["color"]))
    return Image.composite(dot, img, mask)


def render_glow(size_px, points, preset, radius=2.0, base=None, stack=1):
    """מצייר סמני גופים והארה על רקע שחור.

    points  — כל אחד מהצורות הבאות, בפיקסלים של הפאנל:
        (x, y)                  גוף נקודתי — סמן עגול ברדיוס `radius`
        (x, y, w, h)            מלבן
        ("line", [(x,y), ...])  גוף לינארי — פס לאורך הפוליגון
        ("disc", x, y, r)       גוף מנופח — ליבה אטומה ברדיוס r
    preset  — מילון מ-preset_for()

    **ארבע הצורות אינן ארבעה אפקטים.** אותו Outer Glow בדיוק
    חל על כולן; מה שמשתנה הוא רק מה שמצויר במסכת האלפא
    לפניו. לכן המנוע לא קיבל פרמטרים חדשים: פס לינארי הוא קו
    במסכה, וגוף מנופח הוא עיגול גדול בה (D-024).
    """
    W, H = size_px
    # סגנון שמגדיר נקודה משלו (האפור: נקודה זהובה בגודל 2) — היא הצורה
    radius = preset.get("marker_radius_px", radius)
    mask = Image.new("L", (W, H), 0)
    from PIL import ImageDraw
    d = ImageDraw.Draw(mask)
    for p in points:
        if p and isinstance(p[0], str):
            tag = p[0]
            if tag == "line":
                pts = [(float(q[0]), float(q[1])) for q in p[1]]
                w = max(1, int(round(p[2] if len(p) > 2 else radius)))
                if len(pts) >= 2:
                    d.line(pts, fill=255, width=w, joint="curve")
                elif pts:
                    x, y = pts[0]
                    d.ellipse([x - radius, y - radius,
                               x + radius, y + radius], fill=255)
            elif tag == "disc":
                _, x, y, r = p
                r = max(float(r), radius)
                d.ellipse([x - r, y - r, x + r, y + r], fill=255)
        elif len(p) == 2:
            x, y = p
            d.ellipse([x - radius, y - radius, x + radius, y + radius], fill=255)
        else:
            x, y, w, h = p
            d.rectangle([x - w / 2, y - h / 2, x + w / 2, y + h / 2], fill=255)

    if preset.get("blend") == "normal":
        b = base if base is not None else Image.new("RGB", (W, H), (0, 0, 0))
        return _render_glow_normal(mask, preset, b.convert("RGB"), stack)

    glow_a = outer_glow_alpha(mask, preset["size"], preset.get("choke", 0))
    glow_a = glow_a.point(lambda v: int(v * preset["opacity"] / 100.0))

    colour = _hex_to_rgb(preset["color"])
    # תרומת ההארה = צבע ההארה משוקלל באלפא שלה
    glow = Image.merge("RGB", [
        ImageChops.multiply(Image.new("L", (W, H), c), glow_a) for c in colour])

    out = base.copy() if base is not None else Image.new("RGB", (W, H), (0, 0, 0))
    # הסטודיו משכפל את שכבת ההארה. במיזוג Screen שכפול מגביר את הזנב
    # בלי להרוות את המרכז — ראה "Layer 17" ו-"Layer 17 copy" ב-deck_b.psd.
    for _ in range(max(1, stack)):
        out = screen(out, glow)
    # הצורה עצמה, אטומה, מעל ההארה
    shape_rgb = Image.new("RGB", (W, H), colour)
    out = Image.composite(shape_rgb, out, mask)
    return out
