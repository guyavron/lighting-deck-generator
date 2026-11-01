"""שרת מקומי לממשק הפקת המצגות.

    python src/server.py
    ואז לפתוח http://127.0.0.1:8000

רץ מקומית בלבד. קבצי DXF של 56MB אינם עוזבים את המחשב.

המודל שהממשק מממש (לפי גיא):
  העובד מסמן אזורים בעצמו על התוכנית ונותן להם שם,
  ובתוך כל אזור בוחר אילו קטגוריות תאורה יהיו שקופיות.
  כשכל האזורים מוכנים — המצגת מוכנה.

זיהוי האזורים האוטומטי נשאר כהצעת פתיחה בלבד. גיא מסר שחלוקת
הקומות "משתנה תמיד", ולכן זיהוי אוטומטי לא יכול להיות גזרת גורל.
"""
from __future__ import annotations

import csv
import hashlib
import collections
import io
import json
import os
import re
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# קונסולת Windows ברירת המחדל היא cp1252 ואינה יודעת עברית. בלי זה
# השרת קורס על הודעת פתיחה. כל עובדי המשרד על Windows.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

import dxf_read
import framing
import glow as G
import library as LIB
import make_deck
import plan_render as PR
import profile_match as PM
import slide as SL
import subarea as SA
import taxonomy as TX

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DXF_DIR = os.path.join(ROOT, "DXF")
OUT_DIR = os.path.join(ROOT, "out")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

app = FastAPI(title="הפקת מצגות תאורה")

# מצב בזיכרון לכל שרטוט שנטען. טעינה ורינדור יקרים (עשרות שניות),
# ולכן נשמרים ולא מחושבים מחדש בכל בקשה.
_cache: dict = {}
_lock = threading.Lock()

OVERVIEW_W, OVERVIEW_H = 1180, 760


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# התקדמות הטעינה, לכל שרטוט. בדיקת השמישות: 80 שניות של "טוען…"
# בלי שום שינוי על המסך — עובד לא יודע אם הכלי עובד או תקוע. הממשק
# שואל את `/api/load_progress` פעם בשנייה בזמן שהטעינה רצה.
_progress: dict = {}


def _step(name, step, **kw):
    with _lock:
        p = _progress.setdefault(name, {"t0": time.time()})
        p.update(step=step, **kw)


def load_drawing(name):
    with _lock:
        if name in _cache:
            return _cache[name]
    path = os.path.join(DXF_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(404, "קובץ לא נמצא: " + name)
    try:
        return _load_drawing(name, path)
    except HTTPException:
        raise
    except Exception as e:
        # **לא 500 עם "טעינה נכשלה"** (B-04). קובץ ששבור מבפנים צריך
        # לומר את זה בעברית. הסיבה האמיתית נשארת בקונסולה של השרת.
        import traceback
        traceback.print_exc()
        raise HTTPException(400, "לא הצלחתי לקרוא את השרטוט " + os.path.splitext(name)[0] +
                            ". " + _BAD_DXF) from e
    finally:
        with _lock:
            _progress.pop(name, None)


def _load_drawing(name, path):
    t0 = time.time()
    # השלבים מקבילים לרשימה שהממשק מציג. "ראשונה" = ההקלטה עוד לא
    # במטמון, ושלב 2 ייקח כדקה במקום שניות.
    _step(name, 1, first=not PR.is_recorded(path))
    survey = dxf_read.survey(path)
    _step(name, 2, n_fixtures=len(survey.fixtures))
    player = PR.record_cached(path)
    _step(name, 3)
    prof = PM.load()
    shown = {l for l in PR.census(player) if PM.classify(l, prof) == "show"}
    layout = SL.load_layout()
    app_look = layout["plan_appearance"]

    pts = [(f.x, f.y) for f in survey.fixtures]
    body, dropped = framing.main_body(pts)
    # חלון הסקירה נגזר מגוף התוכנית — מקרא הגופים יושב לעיתים עשרות
    # אלפי יחידות משם ומרסק את קנה המידה.
    fr = framing.frame_for(body, (OVERVIEW_W, OVERVIEW_H))
    win = fr.window
    # אבל חלון שנגזר מהגופים בלבד חותך גיאומטריה: נמדד ב-111 (2).dxf
    # שהוא חתך 1,695 יחידות מימין ו-388 מלמעלה, ובזבז 4,789 משמאל.
    # לכן מאחדים עם גבולות הגיאומטריה, כל עוד אלה אינם מנופחים.
    try:
        bb = player.bbox()
        geo = (bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y)
        area = lambda w: max(w[2] - w[0], 1e-9) * max(w[3] - w[1], 1e-9)
        if area(geo) < 5 * area(win):
            merged = (min(win[0], geo[0]), min(win[1], geo[1]),
                      max(win[2], geo[2]), max(win[3], geo[3]))
            win = framing.expand_to_aspect(merged, OVERVIEW_W / OVERVIEW_H,
                                           margin_frac=0.02)
    except Exception:
        pass
    fr_window = win
    img, _, _ = PR.render(player, (OVERVIEW_W, OVERVIEW_H), window=fr_window,
                          supersample=2, layers=shown,
                          line_color=_rgb(app_look["architecture_line"]),
                          fill_color=_rgb(app_look["wall_fill"]))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    to_px, ov_scale = PR.make_transform(fr_window, (OVERVIEW_W, OVERVIEW_H))
    code_to_type = {}
    for t in TX.load()["lighting_types"]:
        for c in t.get("dxf_blocks", []):
            code_to_type[c.upper()] = t["he"]

    fixtures = []
    for f in survey.fixtures:
        x, y = to_px(f.x, f.y)
        row = {"x": round(x, 1), "y": round(y, 1), "code": f.code,
               "layer": f.layer,
               "type": code_to_type.get(f.code.upper(), ""),
               "wx": f.x, "wy": f.y}
        # גוף לינארי נשלח עם כל קודקודיו, כדי שהממשק יצייר פס ולא
        # נקודה בודדת במרכזו. גוף מנופח נשלח עם רדיוסו.
        if f.kind == "line" and f.pts:
            row["kind"] = "line"
            row["pts"] = [[round(v, 1) for v in to_px(px_, py_)]
                          for px_, py_ in f.pts]
        elif f.kind == "circle":
            row["kind"] = "circle"
            row["r"] = round(f.radius * ov_scale, 1)
        fixtures.append(row)

    # המקרא נשאר בתוכנית, אבל אינו מוצע כאזור (D-044)
    code_at = {}
    for f in survey.fixtures:
        code_at.setdefault((f.x, f.y), f.code)
    leg = framing.legend_columns(body, [code_at[p] for p in body])
    rooms = [p for i, p in enumerate(body) if i not in leg] or body

    suggested = []
    for i, area in enumerate(sorted(framing.clusters(rooms, axis=1),
                                    key=lambda g: -min(p[1] for p in g))):
        xs = [p[0] for p in area]
        ys = [p[1] for p in area]
        a = [to_px(min(xs), max(ys)), to_px(max(xs), min(ys))]
        suggested.append({"name": "אזור " + str(i + 1),
                          "x0": round(min(a[0][0], a[1][0]) - 14),
                          "y0": round(min(a[0][1], a[1][1]) - 14),
                          "x1": round(max(a[0][0], a[1][0]) + 14),
                          "y1": round(max(a[0][1], a[1][1]) + 14),
                          "n": len(area)})

    # כל השכבות שיש בהן גיאומטריה, עם ברירת המחדל של הפרופיל.
    # המתכנן רואה את הרשימה המלאה ויכול לשנות — הפרופיל הוא נקודת
    # פתיחה, לא החלטה סגורה.
    counts = PR.census(player)
    layer_list = [{"name": n, "n": c,
                   "role": PM.classify(n, prof),
                   "on": PM.classify(n, prof) == "show"}
                  for n, c in counts.items()]

    state = {
        "path": path, "survey": survey, "player": player, "shown": shown,
        "layers": layer_list,
        "lighting_layers": {l["name"] for l in layer_list
                            if l["role"] == "lighting"},
        "code_names": code_to_type,
        "png": buf.getvalue(), "window": fr_window,
        "fixtures": fixtures, "suggested": suggested,
        "dropped": len(dropped), "seconds": round(time.time() - t0, 1),
        "has_architecture": survey.has_architecture,
    }
    with _lock:
        _cache[name] = state
    return state


@app.get("/", response_class=HTMLResponse)
def index():
    # **בלי מטמון.** כל הממשק הוא קובץ אחד בשם קבוע, והדפדפן שמר
    # אותו: תיקון שנכתב בשרת פשוט לא הגיע למסך, ונראה כאילו הוא
    # לא בוצע. כלי מקומי אינו מרוויח דבר ממטמון דף.
    with open(os.path.join(WEB_DIR, "index.html"), encoding="utf-8") as fh:
        return Response(content=fh.read(), media_type="text/html; charset=utf-8",
                        headers={"Cache-Control": "no-store, must-revalidate"})


@app.get("/api/drawings")
def drawings():
    if not os.path.isdir(DXF_DIR):
        return {"files": []}
    files = sorted(f for f in os.listdir(DXF_DIR) if f.lower().endswith(".dxf"))
    return {"files": [{"name": f,
                       "mb": round(os.path.getsize(os.path.join(DXF_DIR, f)) / 1e6, 1)}
                      for f in files]}


_BAD_DXF = "הקובץ פגום או אינו שרטוט DXF. ייצא אותו מחדש מאוטוקאד ונסה שוב."


def _looks_like_dxf(head: bytes, tail: bytes) -> bool:
    """בדיקה זולה: הכותרת של DXF והסוף שלו. לא קוראים את הקובץ כולו.

    DXF טקסטואלי פותח בזוגות שורות (קוד, ערך): אפס אחד או יותר
    הערות (999), ואז `0 / SECTION`. הוא נגמר ב-`0 / EOF`. קובץ שנחתך
    באמצע חסר את הסוף. DXF בינארי נושא חתימה ייעודית בראשו.
    """
    if head.startswith(b"AutoCAD Binary DXF"):
        return True
    lines = head.decode("latin-1").lstrip("\ufeff").replace("\r", "").split("\n")
    i = 0
    while i + 1 < len(lines) and lines[i].strip() == "999":
        i += 2
    if not (i + 1 < len(lines) and lines[i].strip() == "0"
            and lines[i + 1].strip() == "SECTION"):
        return False
    tail_lines = [x.strip() for x in tail.decode("latin-1").replace("\r", "").split("\n")
                  if x.strip()]
    return len(tail_lines) >= 2 and tail_lines[-1] == "EOF" and tail_lines[-2] == "0"


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    """העלאת שרטוט. נכתב בנתחים — קבצי DXF כאן הם 4 עד 78MB.

    הקובץ נשמר ב-DXF/ ונשאר על המחשב. שום דבר לא נשלח החוצה.
    """
    name = os.path.basename(file.filename or "")
    if not name.lower().endswith(".dxf"):
        raise HTTPException(400, "יש להעלות קובץ DXF")
    os.makedirs(DXF_DIR, exist_ok=True)
    chunks, h = [], hashlib.sha1()
    while chunk := await file.read(1 << 20):
        chunks.append(chunk)
        h.update(chunk)
    size = sum(len(c) for c in chunks)
    if size == 0:
        raise HTTPException(400, "הקובץ ריק")
    # קובץ שאינו DXF, או DXF שנחתך באמצע, נדחה לפני שנשמר (B-04).
    # קודם הוא נשמר ב-DXF/ לתמיד, נשאר בבורר, והטעינה שלו נפלה.
    head = chunks[0][:4096]
    tail = b"".join(chunks[-2:])[-256:]
    if not _looks_like_dxf(head, tail):
        raise HTTPException(400, _BAD_DXF)
    # אותו קובץ שכבר כאן — חוזרים אליו ולא שומרים עותק.
    # מצב הפרויקט נשמר לפי שם הקובץ, ולכן עותק חדש היה פותח פרויקט
    # ריק, והעבודה הקודמת נשארת מאחור בשם אחר. כך קרה 17 פעם.
    same = _identical_drawing(size, h.hexdigest())
    if same:
        return {"name": same, "mb": round(size / 1e6, 1), "existing": True}
    dest = os.path.join(DXF_DIR, name)
    # לא דורסים קובץ קיים — אותו חוק ברזל כמו בייצוא
    if os.path.exists(dest):
        stem, ext = os.path.splitext(name)
        dest = os.path.join(DXF_DIR, stem + "_" +
                            time.strftime("%Y%m%d-%H%M%S") + ext)
        name = os.path.basename(dest)
    with open(dest, "wb") as out:
        for c in chunks:
            out.write(c)
    return {"name": name, "mb": round(size / 1e6, 1), "existing": False}


def _identical_drawing(size, digest):
    """שם שרטוט ב-DXF/ שתוכנו זהה בדיוק, או None.

    כשיש כמה עותקים זהים (נוצרו לפני התיקון), מחזירים את זה שהפרויקט
    שלו נשמר אחרון — שם נמצאת העבודה העדכנית.
    """
    best, best_t = None, -1.0
    for f in os.listdir(DXF_DIR):
        p = os.path.join(DXF_DIR, f)
        if not f.lower().endswith(".dxf") or os.path.getsize(p) != size:
            continue
        full = hashlib.sha1()
        with open(p, "rb") as fh:
            while chunk := fh.read(1 << 20):
                full.update(chunk)
        if full.hexdigest() != digest:
            continue
        pp = _project_path(f)
        t = os.path.getmtime(pp) if os.path.exists(pp) else 0.0
        if t > best_t:
            best, best_t = f, t
    return best


# ─── האם יש רקע שיוצג בפועל? (D-037) ───────────────────────────
# הבדיקה הקודמת ספרה ישויות בקובץ. ב-3.dxf היא מצאה 1,266 — אבל
# אלה חזיתות של הבניין על שכבה "0", הרחק מהתוכנית, ושכבה "0" גם
# מוסתרת בפרופיל. התוצאה: אין אזהרה, ושקופיות שחורות. עכשיו נבדק
# מה **יצויר**: השכבות המוצגות כברירת מחדל שאינן תאורה.
_MIN_BACKGROUND_PRIMITIVES = 2000


def _shows_architecture(s):
    shown = sum(l["n"] for l in s["layers"] if l["role"] == "show")
    return bool(s["survey"].has_architecture) and shown >= _MIN_BACKGROUND_PRIMITIVES


def _hidden_candidates(s):
    """שכבות מוסתרות שאינן תאורה ויש בהן תוכן — אולי התוכנית שם."""
    c = [(l["name"], l["n"]) for l in s["layers"]
         if l["role"] == "hide" and l["n"] >= 200]
    return [{"name": n, "n": k} for n, k in sorted(c, key=lambda x: -x[1])[:5]]


@app.get("/api/load_progress")
def load_progress(name: str):
    """איפה הטעינה של שרטוט עומדת. `active: false` = לא רצה (או נגמרה)."""
    with _lock:
        p = dict(_progress.get(name) or {})
    if not p:
        return {"active": False}
    return {"active": True, "step": p.get("step", 1),
            "first": bool(p.get("first")),
            "n_fixtures": p.get("n_fixtures"),
            "elapsed": round(time.time() - p["t0"])}


@app.get("/api/load")
def load(name: str):
    s = load_drawing(name)
    return {
        "width": OVERVIEW_W, "height": OVERVIEW_H,
        "fixtures": s["fixtures"], "suggested": s["suggested"],
        "dropped": s["dropped"], "seconds": s["seconds"],
        "has_architecture": _shows_architecture(s),
        "hidden_candidates": _hidden_candidates(s),
        "n_fixtures": len(s["survey"].fixtures),
        "unmapped": TX.describe_unmapped(
            sorted({f.code for f in s["survey"].fixtures})),
        "layers": s["layers"],
        "code_names": s["code_names"],
    }


# ─── עובי ובהירות לכל שכבה (D-031) ──────────────────────────────

def _layer_styles(st, styles):
    """הגדרות העובד, נקיות: בלי שכבות תאורה ובלי ערכים לא מוכרים.

    שכבות התאורה אינן מקבלות סגנון גם אם משהו בממשק ישלח — מה
    שנראה בהן הוא הזוהר, והוא מכויל מול הייחוס.
    """
    if isinstance(styles, str):
        try:
            styles = json.loads(styles) if styles else {}
        except ValueError:
            styles = {}
    ls = SL.load_layout()["plan_appearance"]["layer_style"]
    widths = ls["widths"]
    lo, hi = ls.get("brightness_min", -1.0), ls.get("brightness_max", 1.0)
    out = {}
    for name, v in (styles or {}).items():
        if name in st.get("lighting_layers", ()) or not isinstance(v, dict):
            continue
        w = v.get("w") if v.get("w") in widths else "normal"
        try:
            # הטווח מהידע, ולכן גם ערך ישן ששמור בפרויקט (‎-90%) נאכף
            b = round(max(lo, min(hi, float(v.get("b") or 0))), 2)
        except (TypeError, ValueError):
            b = 0.0
        if w != "normal" or b:
            out[name] = {"w": w, "b": b}
    return out


def _style_key(styles):
    return tuple(sorted((k, v["w"], v["b"]) for k, v in styles.items()))


def _render_kw(look, styles):
    """הארגומנטים המשותפים לכל רינדור תוכנית — סקירה, אזור, שקופית."""
    widths = (look.get("layer_style") or {}).get("widths") or {}
    kw = {"line_color": _rgb(look["architecture_line"]),
          "fill_color": _rgb(look["wall_fill"]),
          "styles": styles,
          "widths": {k: v["factor"] for k, v in widths.items()}}
    # הסגנון האפור (D-050): רקע בהיר וריהוט במילוי. השחור לא מגדיר
    # אותם, ולכן כל רינדור שחור נשאר בדיוק כפי שהיה.
    if look.get("background") and look["background"].upper() != "#000000":
        kw["background"] = _rgb(look["background"])
    if look.get("furniture_fill"):
        kw["furniture"] = {"fill": _rgb(look["furniture_fill"]),
                           "layers": look.get("furniture_layers") or []}
    return kw


@app.get("/api/plan.png")
def plan_png(name: str, layers: str = "", styles: str = ""):
    """תמונת הסקירה. layers ריק = הפרופיל שנשמר בטעינה.

    כשהמתכנן משנה שכבות, מרנדרים מחדש. הריקורד כבר במטמון ולכן זה
    נמשך שניות בודדות ולא עשרות.
    """
    st = load_drawing(name)
    sty = _layer_styles(st, styles)
    if not layers and not sty:
        return Response(st["png"], media_type="image/png")

    wanted = {l for l in layers.split("") if l} or set(st["shown"])
    key = (tuple(sorted(wanted)), _style_key(sty))
    cached = st.setdefault("png_variants", {})
    if key not in cached:
        layout = SL.load_layout()
        look = layout["plan_appearance"]
        img, _, _ = PR.render(st["player"], (OVERVIEW_W, OVERVIEW_H),
                              window=st["window"], supersample=2, layers=wanted,
                              **_render_kw(look, sty))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # מגבילים את המטמון כדי שלא ינפח את הזיכרון בשינויים רבים
        if len(cached) > 12:
            cached.clear()
        cached[key] = buf.getvalue()
    return Response(cached[key], media_type="image/png")


AREA_W, AREA_H = 1180, 800


@app.get("/api/area.png")
def area_png(name: str, x0: float, y0: float, x1: float, y1: float,
             layers: str = "", styles: str = "", poly: str = ""):
    """רינדור מוגדל של אזור בודד, בקואורדינטות הסקירה.

    בתצוגת הסקירה הגופים במרחק 2 פיקסלים זה מזה ואי אפשר לפגוע
    בגוף בודד. בלי הזום הזה הבחירה הידנית אינה שמישה.
    """
    st = load_drawing(name)
    wx0, wy0, wx1, wy1 = st["window"]
    sx = (wx1 - wx0) / OVERVIEW_W
    sy = (wy1 - wy0) / OVERVIEW_H
    lo_x, hi_x = sorted((x0, x1))
    lo_y, hi_y = sorted((y0, y1))
    win = (wx0 + lo_x * sx, wy1 - hi_y * sy,
           wx0 + hi_x * sx, wy1 - lo_y * sy)
    cut = win
    win = framing.expand_to_aspect(win, AREA_W / AREA_H, margin_frac=0.04)

    wanted = {l for l in layers.split("") if l} or st["shown"]
    layout = SL.load_layout()
    look = layout["plan_appearance"]
    img, _, _ = PR.render(st["player"], (AREA_W, AREA_H), window=win,
                          supersample=2, layers=wanted,
                          **_render_kw(look, _layer_styles(st, styles)))
    to_px, a_scale = PR.make_transform(win, (AREA_W, AREA_H))
    # **תת-אזור: רק הצורה שגזרו** (גיא, 12.10: "רואים רק את החלק
    # המודגש ששרטטנו"). אותו חיתוך כמו בשקופיות העבודה, ולכן מה
    # שעובדים עליו הוא מה שייצא.
    try:
        ring = SA.close_ring([(p[0], p[1]) for p in json.loads(poly or "[]")
                              if len(p) >= 2])
    except (ValueError, TypeError):
        ring = []
    if len(ring) < 3:
        # אזור רגיל: רק המלבן שגזרו, כמו בשקופית — מה שעובדים עליו
        # בשלב 2 הוא בדיוק מה שייצא
        ring = [(cut[0], cut[1]), (cut[2], cut[1]), (cut[2], cut[3]), (cut[0], cut[3])]
    img = SA.clip(img, [to_px(x, y) for x, y in ring],
                  _rgb(look.get("background") or "#000000"))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    pts = []
    for i, f in enumerate(st["survey"].fixtures):
        if not (win[0] <= f.x <= win[2] and win[1] <= f.y <= win[3]):
            continue
        px_, py_ = to_px(f.x, f.y)
        row = {"i": i, "x": round(px_, 1), "y": round(py_, 1)}
        if f.kind == "line" and f.pts:
            row["kind"] = "line"
            row["pts"] = [[round(v, 1) for v in to_px(ax, ay)]
                          for ax, ay in f.pts]
        elif f.kind == "circle":
            row["kind"] = "circle"
            row["r"] = round(f.radius * a_scale, 1)
        pts.append(row)
    import base64
    return {"png": "data:image/png;base64," +
                   base64.b64encode(buf.getvalue()).decode(),
            "width": AREA_W, "height": AREA_H, "fixtures": pts,
            # חלון העולם של התצוגה. בלעדיו הממשק יכול לסמן תת-אזור
            # רק בפיקסלים של הזום הזה — והוא נכון בו בלבד, ושגוי
            # בפאנל השקופית שמרונדר בגודל ובחלון אחרים.
            "window": [win[0], win[1], win[2], win[3]]}


# ─── שמירת מצב פרויקט ────────────────────────────────────────────
# מצגת היא עבודה של שעות. איבודה ברענון דף אינו סביר, ולכן המצב
# נשמר לדיסק בכל שינוי. אותו עיקרון כמו חוקי הברזל האחרים:
# המערכת לא מאבדת עבודה של אדם.
PROJECTS_DIR = os.path.join(ROOT, "out", "projects")


def _project_path(drawing):
    safe = hashlib.sha1(drawing.encode("utf-8")).hexdigest()[:16]
    return os.path.join(PROJECTS_DIR, safe + ".json")


# ─── הגנה על העבודה (D-036) ─────────────────────────────────────
# בדיקת שמישות (13.10) מצאה ארבע דרכים לאבד מצגת שלמה:
#  1. קובץ פגום (הפסקת חשמל באמצע שמירה) נפתח כפרויקט ריק, והשינוי
#     הראשון דרס אותו — 111 שקופיות. → כתיבה אטומית, גרסאות שמורות,
#     ופרויקט שלא נקרא **חוסם שמירה** במקום להתחיל מאפס.
#  2. שמירה שנכשלה (שרת למטה) — שקט מוחלט. → זה בצד הממשק.
#  3. שני חלונות על אותו פרויקט: האחרון ששומר מוחק את השני. → מספר
#     גרסה (`rev`); שמירה מגרסה ישנה נדחית ב-409.
#  4. שינוי ואז סגירה תוך חצי שנייה. → בצד הממשק.
HISTORY_DIR = os.path.join(PROJECTS_DIR, "history")
_SNAPSHOT_EVERY = 10 * 60          # שניות בין גרסאות שמורות
_project_lock = threading.Lock()


def _history_dir(drawing):
    return os.path.join(HISTORY_DIR, os.path.basename(_project_path(drawing))[:-5])


def _read_project(drawing):
    """(state, None) / (None, "missing") / (None, "corrupt")."""
    p = _project_path(drawing)
    if not os.path.exists(p):
        return None, "missing"
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh), None
    except (ValueError, OSError):
        return None, "corrupt"


def _versions(drawing):
    """גרסאות שמורות, החדשה ראשונה: [{"id", "saved_at", "slides"}]."""
    d = _history_dir(drawing)
    out = []
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d), reverse=True):
        if not f.endswith(".json") or ".corrupt" in f:
            continue
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                st = json.load(fh)
        except (ValueError, OSError):
            continue
        out.append({"id": f[:-5], "saved_at": st.get("saved_at", ""),
                    "slides": sum(len(a.get("slides") or [])
                                  for a in st.get("areas") or [])})
    return out


def _write_atomic(path, data):
    """כתיבה לקובץ זמני ואז החלפה. קובץ חצי-כתוב לעולם אינו נשאר במקום."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _snapshot(drawing, state, force=False):
    """שומר עותק של הגרסה הנוכחית ב-history/, לכל היותר פעם ב-10 דקות.

    לא מוחקים גרסאות ישנות — חוק ברזל 3. גרסה היא ~40KB.
    """
    d = _history_dir(drawing)
    os.makedirs(d, exist_ok=True)
    have = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if have and not force:
        last = os.path.getmtime(os.path.join(d, have[-1]))
        if time.time() - last < _SNAPSHOT_EVERY:
            return
    name = time.strftime("%Y%m%d-%H%M%S") + ".json"
    _write_atomic(os.path.join(d, name), state)


@app.get("/api/project")
def project_get(drawing: str):
    state, err = _read_project(drawing)
    if err == "missing":
        return {"found": False}
    if err == "corrupt":
        # **לא "לא נמצא".** הממשק חייב לדעת שיש כאן עבודה שלא נקראה,
        # אחרת הוא מתחיל מאפס ודורס אותה בשמירה הראשונה.
        return {"found": True, "corrupt": True, "versions": _versions(drawing)}
    return {"found": True, "state": state, "rev": int(state.get("rev") or 0)}


@app.get("/api/project/versions")
def project_versions(drawing: str):
    return {"versions": _versions(drawing)}


@app.post("/api/project")
async def project_put(request: Request):
    body = await request.json()
    drawing = body.get("drawing")
    if not drawing:
        raise HTTPException(400, "חסר שם שרטוט")
    base = int(body.pop("base_rev", -1) if "base_rev" in body else -1)
    # "שמור בכל זאת" — העובד בחר לדרוס גרסה שנשמרה ממקום אחר. היא
    # נשמרת קודם בגרסאות, בלי חלון 10 הדקות.
    force = bool(body.pop("force", False))
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    with _project_lock:
        cur, err = _read_project(drawing)
        if err == "corrupt":
            # פרויקט שלא נקרא לעולם אינו נדרס בשמירה רגילה
            raise HTTPException(409, "הפרויקט בדיסק פגום — שחזר גרסה לפני שממשיכים")
        cur_rev = int((cur or {}).get("rev") or 0)
        if cur is not None and base >= 0 and base != cur_rev and not force:
            # **שני חלונות.** מי ששומר מגרסה ישנה היה מוחק את מה שנשמר
            # בינתיים — נמדד: שקופית שנוספה בחלון אחד נעלמה.
            return Response(json.dumps({"conflict": True, "rev": cur_rev,
                                        "saved_at": cur.get("saved_at", "")},
                                       ensure_ascii=False),
                            status_code=409, media_type="application/json")
        if cur is not None:
            _snapshot(drawing, cur, force=force)
        body["rev"] = cur_rev + 1
        body["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _write_atomic(_project_path(drawing), body)
    return {"saved": True, "rev": body["rev"], "saved_at": body["saved_at"]}


@app.post("/api/project/restore")
async def project_restore(request: Request):
    """מחזיר גרסה שמורה. הנוכחית (גם פגומה) נשמרת קודם — לא מוחקים."""
    body = await request.json()
    drawing, vid = body.get("drawing"), body.get("version")
    src = os.path.join(_history_dir(drawing or ""), (vid or "") + ".json")
    if not drawing or not vid or not os.path.exists(src):
        raise HTTPException(404, "הגרסה לא נמצאה")
    with _project_lock:
        p = _project_path(drawing)
        cur, err = _read_project(drawing)
        d = _history_dir(drawing)
        os.makedirs(d, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if err == "corrupt":
            import shutil
            shutil.copy2(p, os.path.join(d, stamp + ".corrupt.json"))
        elif cur is not None:
            _snapshot(drawing, cur, force=True)
        with open(src, encoding="utf-8") as fh:
            state = json.load(fh)
        state["rev"] = int((cur or {}).get("rev") or 0) + 1
        state["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _write_atomic(p, state)
    return {"restored": True, "rev": state["rev"]}


class SlideSpec(BaseModel):
    type: str = ""
    codes: list[str] = []
    # שכבות תאורה שנבחרו לשקופית — הרמה הראשית בבחירה
    layers_lit: list[str] = []
    option: str = ""
    # אינדקסים של גופים שנבחרו ידנית בלחיצה. ריק = לפי הקטגוריה.
    picks: list[int] = []
    # מזהי תצלומים שנבחרו במאגר. ריק = ברירת המחדל לפי הקטגוריה.
    photos: list[str] = []
    # פריסת התוכנית: -1 אוטומטי לפי יחס האזור, 0 צרה, 1 רחבה.
    # מה שנבחר בתצוגה המקדימה חייב להגיע גם לייצוא, אחרת התצוגה
    # מראה משהו אחר ממה שיוצא — וזו בדיוק הבעיה שהיא באה לפתור.
    wide: int = -1
    # כותרת מלאה שהמתכנן הקליד. "|" מפריד לשורות, כמו בייחוס
    # ("חדר מאסטר | תאורה דקורטיבית | אופציה א"). ריק = כותרת אוטומטית.
    title: str = ""
    # פריסה ידנית — מה שהמתכנן הזיז בתצוגה, בקואורדינטות הקנבס
    # (2000x1125). ריק = הפריסה האוטומטית. ראה `slide.resolve`.
    #   {"plan":[x,y,w,h], "photos":[[x,y,w,h]|null], "title":{x,y,w,pt}}
    geom: dict = {}
    # שקופית הפתיחה של תת-אזור: התוכנית של **אזור האב** עם המסכה
    # הצהובה עליה, בלי הארה. אחריה השקופיות חתוכות לתת-האזור עצמו.
    # כך בדיוק במצגת ייחוס א: 97 מציגה מסכה, 98 כבר חתוכה. הפוליגון עצמו
    # שייך לאזור (`AreaSpec.poly`) ולא לשקופית — הוא תחום עבודה,
    # לא קישוט של שקופית אחת.
    mask: bool = False
    # שקופית תצלומים בלבד (D-035): בלי תוכנית ובלי הארה. עד 3
    # תצלומים בשורה ממורכזת — הפריסה שנמדדה במצגת ייחוס א.
    photos_only: bool = False
    # שקופית ששוחררה מנעילת התוכנית של האזור (D-047) — "רק כאן".
    # הפריסה שלה ב-`geom`/`wide` כרגיל.
    plan_free: bool = False
    # הזוהר של השקופית (D-051): {"color", "size", "power"} מתוך
    # `per_slide` ב-glow.yaml. ריק = הפריסט של הסגנון.
    glow: dict = {}
    # הקטגוריה שבה התצלומים נבחרו, וסינון התגיות בזמן הבחירה. משמשים
    # רק לזיכרון המאגר אחרי הפקה (D-038).
    photo_category: str = ""
    photo_tags: list[str] = []
    # שקופית מאושרת (✓, D-034). שקופית מאושרת בלי תצלום היא בחירה,
    # ולכן אינה מופיעה ברשימת "בלי תצלום".
    done: bool = False


class AreaSpec(BaseModel):
    name: str = ""
    x0: float
    y0: float
    x1: float
    y1: float
    slides: list[SlideSpec] = []
    # ── תת-אזור ──
    # תת-אזור הוא אזור לכל דבר, עם פוליגון אורתוגונלי שמצמצם אותו.
    # הפוליגון **בקואורדינטות השרטוט**, לא בפיקסלים: התוכנית מרונדרת
    # בשלושה גדלים לפחות, ופוליגון בפיקסלים היה נכון באחד ושגוי בשניים.
    poly: list[list[float]] = []
    parent: str = ""                    # שם האזור שממנו נגזר, לתצוגה
    # נעילת התוכנית של האזור (D-047): {"plan":[x,y,w,h], "rot", "wide",
    # "align": "left"|"center"}. ריק = אין נעילה, כל שקופית לעצמה —
    # כך נשאר פרויקט ישן שעוד לא נפתח בממשק החדש.
    plan_lock: dict = {}
    # תיבת אזור האב — נחוצה לשקופית הפתיחה, שמראה את התוכנית המלאה.
    # נשמרת כאן כדי שתת-האזור יהיה עצמאי ולא יידרש לחפש את אביו.
    parent_box: list[float] = []


class BuildSpec(BaseModel):
    drawing: str
    project: str = "deck_a"
    photos_per_slide: int = 1
    # שכבות להצגה. ריק = פרופיל ברירת המחדל.
    layers: list[str] = []
    # עובי ובהירות לכל שכבה: {שכבה: {"w": "thick", "b": 0.3}} (D-031)
    layer_styles: dict = {}
    # הפס מתחת לכותרת — הגדרה של המצגת כולה, לא של שקופית
    title_rule: bool = True
    # סגנון המצגת (D-050): "" / "black" או "grey"
    deck_style: str = ""
    areas: list[AreaSpec] = []


_panels: "collections.OrderedDict" = collections.OrderedDict()
_PANEL_MAX = 16


def _plan_panel(name, player, shown, window, size, look, styles=None):
    """פאנל התוכנית המרונדר, ממוטמן.

    **נמדד:** רינדור אחד של `111 (2).dxf` = 5.5 שניות, כי כל קריאה
    מריצה מחדש את ההקלטה כולה. גיא: "זמן טעינה של השקופית מאוד ארוך."
    הפאנל אינו תלוי בתצלום, בכותרת או בהארה — רק בשרטוט, בשכבות
    המוצגות, בחלון ובגודל. לכן שינוי בשקופית עולה 0.4 שניות ולא 6.

    המפתח כולל את השכבות: העובד מדליק ומכבה שכבות אדריכליות, וזה
    כן משנה את התמונה.
    """
    styles = styles or {}
    key = (name, frozenset(shown), tuple(round(v, 3) for v in window), size,
           _style_key(styles), look.get("background"), look.get("furniture_fill"),
           look.get("architecture_line"))
    with _lock:
        hit = _panels.get(key)
        if hit is not None:
            _panels.move_to_end(key)
            return hit
    img = PR.render(player, size, window=window, supersample=3, layers=shown,
                    **_render_kw(look, styles))[0]
    with _lock:
        _panels[key] = img
        while len(_panels) > _PANEL_MAX:
            _panels.popitem(last=False)
    return img


def _forced_aspect(aspect, wide, layout):
    """יחס הפאנל אחרי כפייה. -1 אוטומטי, 0 צר, 1 רחב.

    הכפייה על היחס ולא על התיבה, כדי ששתי הדרכים — התצוגה והייצוא —
    יעברו דרך אותה `plan_panel_box`.
    """
    th = layout["plan_panel"]["wide_threshold_aspect"]
    if wide == 1:
        return max(aspect, th + .01)
    if wide == 0:
        return min(aspect, th - .01)
    return aspect


# סיבוב התוכנית בצעדים של 90 מעלות, בכיוון השעון.
# **הרסטר עצמו מסתובב, ולא מונח בזווית.** PowerPoint מסובב סביב
# המרכז ומשאיר תיבה תוחמת בגודל המקורי; CSS מסובב אחרת. כל עוד
# התמונה שנשלחת כבר מסובבת, שתי הדרכים מניחות מלבן רגיל ואין להן
# איפה להיפרד. transpose בכפולות של 90 גם אינו מאבד ולו פיקסל.
_ROT = {}
try:
    from PIL import Image as _PILImage
    _ROT = {90: _PILImage.Transpose.ROTATE_270,
            180: _PILImage.Transpose.ROTATE_180,
            270: _PILImage.Transpose.ROTATE_90}
except Exception:                                   # PIL ישן
    from PIL import Image as _PILImage
    _ROT = {90: _PILImage.ROTATE_270, 180: _PILImage.ROTATE_180,
            270: _PILImage.ROTATE_90}


def _rot_of(geom):
    """הסיבוב שנשמר בשקופית. כל ערך שאינו כפולה של 90 הוא 0."""
    try:
        r = int((geom or {}).get("rot", 0)) % 360
    except (TypeError, ValueError):
        return 0
    return r if r in (90, 180, 270) else 0


def _area_box_world(s, a, mask=False):
    """המלבן שהעובד גזר, בקואורדינטות השרטוט: (x0, y0, x1, y1).

    בשקופית הפתיחה של תת-אזור זה המלבן של האב (`parent_box`), כי היא
    מראה את השלם עם המסכה."""
    x0w, y0w, x1w, y1w = s["window"]
    sx = (x1w - x0w) / OVERVIEW_W
    sy = (y1w - y0w) / OVERVIEW_H

    def to_world(px, py):
        return (x0w + px * sx, y1w - py * sy)

    box_src = (a.parent_box if (mask and len(a.parent_box) == 4)
               else [a.x0, a.y0, a.x1, a.y1])
    bx0, by0, bx1, by1 = box_src
    wx0, wy0 = to_world(min(bx0, bx1), max(by0, by1))
    wx1, wy1 = to_world(max(bx0, bx1), min(by0, by1))
    return (wx0, wy0, wx1, wy1)


def _area_fixtures(s, a, mask=False):
    """הגופים שבתוך האזור, והפוליגון שצמצם אותם. בלי מסגור ובלי ציור —
    ולכן זול מספיק לבדיקה של כל המצגת (`_slide_blocker`)."""
    wx0, wy0, wx1, wy1 = _area_box_world(s, a, mask)
    inside = [f for f in s["survey"].fixtures
              if wx0 <= f.x <= wx1 and wy0 <= f.y <= wy1]
    # הפוליגון מצמצם את האזור — אבל לא בשקופית הפתיחה, שכל תפקידה
    # להראות איפה תת-האזור יושב בתוך השלם.
    poly = [] if mask else [(p[0], p[1]) for p in (a.poly or []) if len(p) >= 2]
    if len(poly) >= 3:
        inside = [f for f in inside if SA.contains(poly, f.x, f.y)]
    return inside, poly


def _frame_points(inside, poly, box=None):
    """הנקודות שהמסגור נגזר מהן. סדר העדיפויות:

    1. הפוליגון של תת-אזור (D-026).
    2. **המלבן שהעובד גזר** (`box`, בקואורדינטות השרטוט). "מה שגוזרים
       זה מה שרואים": קודם המסגור היה לפי הגופים, והם יושבים 50–100
       ס"מ מהקירות — כל שקופית איבדה את הקירות החיצוניים, ולעובד לא
       הייתה דרך להחזיר אותם. הופך את D-057; ראה docs/decisions.md.
    3. הגופים עצמם, רק כשאין מלבן תקין (כמו ב-CLI).
    """
    if len(poly) >= 3:
        return list(poly)
    if box and box[2] > box[0] and box[3] > box[1]:
        x0, y0, x1, y1 = box
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    # **גוף לינארי תורם את כל קודקודיו למסגור.** לפי המרכז בלבד,
    # פס באורך 1425 יחידות היה נחתך בשני קצותיו.
    pts = []
    for f in inside:
        if getattr(f, "kind", "point") == "line" and getattr(f, "pts", None):
            pts.extend(f.pts)
        else:
            pts.append((f.x, f.y))
    return pts


def _cut_ring(s, area, sl, sub_ring=()):
    """המלבן שהעובד גזר, כטבעת בקואורדינטות השרטוט, לחיתוך התוכנית.

    ריק כשהאזור הוא תת-אזור (הפוליגון שלו כבר חותך) — חוץ משקופית
    הפתיחה שלו, שמראה את האב ונחתכת למלבן של האב."""
    if len(sub_ring) >= 3 and not sl.mask:
        return []
    x0, y0, x1, y1 = _area_box_world(s, area, bool(sl.mask))
    if x1 <= x0 or y1 <= y0:
        return []
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _cut_at_edge(inside, box):
    """כמה גופים באזור חורגים מהמלבן ולכן ייחתכו בקצה השקופית.

    זה הסיכון שעבר עם המסגור לפי המלבן: גוף רחוק כבר לא מותח את החלון,
    אבל פס לינארי שחלקו בחוץ, או גוף מנופח שהרדיוס שלו חוצה את הקצה,
    נחתכים. שלב 3 מראה את המספר, כדי שזה לא יקרה בשקט (B-02)."""
    x0, y0, x1, y1 = box
    n = 0
    for f in inside:
        kind = getattr(f, "kind", "point")
        if kind == "line" and getattr(f, "pts", None):
            if any(not (x0 <= x <= x1 and y0 <= y <= y1) for x, y in f.pts):
                n += 1
        elif kind == "circle" and getattr(f, "radius", 0):
            r = f.radius
            if f.x - r < x0 or f.x + r > x1 or f.y - r < y0 or f.y + r > y1:
                n += 1
    return n


def _area_geometry(s, spec, a, layout, wide=-1, rot=0, mask=False,
                   plan_size=None, alone=False, align="left"):
    """גופים באזור, יחס הפאנל, וחלון המסגור. משותף לייצוא ולתצוגה.

    כל מה שקובע איך השקופית תיראה חייב לחיות במקום אחד. תצוגה
    מקדימה שמחשבת פריסה משלה תשקר בדיוק במקום שבו היא הכי נחוצה.

    `mask=True` היא שקופית הפתיחה של תת-אזור: **התוכנית של אזור
    האב**, בלי צמצום לפוליגון. כל שאר שקופיות תת-האזור מסוגרות
    לפוליגון עצמו — וזה ההבדל שהופך את תת-האזור מקישוט לתחום
    עבודה. מצגת ייחוס א 97 מול 98.
    """
    inside, poly = _area_fixtures(s, a, mask)
    if not inside:
        return None

    # **תת-אזור ממוסגר לפי הפוליגון, לא לפי הגופים שבתוכו.**
    # זה היה הבאג שגיא ראה פעמיים: "התת אזור הופך למלבן במקום
    # הפוליגון שהגדרתי". המסגור לפי הגופים נתן חלון **בתוך**
    # הפוליגון — נמדד אצלו: פוליגון בגובה 1018 יחידות מול חלון
    # בגובה 425 — ולכן החיתוך לא חתך דבר והשקופית הראתה פרוסה
    # מלבנית שרירותית. הצורה שהעובד גזר היא מה שהוא ביקש לראות.
    pts = _frame_points(inside, poly, None if len(poly) >= 3
                        else _area_box_world(s, a, mask))
    xs = sorted(p[0] for p in pts)
    ys = sorted(p[1] for p in pts)
    aspect = (max(make_deck.pctl(xs, .98) - make_deck.pctl(xs, .02), 1e-9) /
              max(make_deck.pctl(ys, .98) - make_deck.pctl(ys, .02), 1e-9))
    # הכפייה נכנסת כאן, לפני הרינדור — כך התוכנית מרונדרת בגודל
    # התיבה הסופית במקום להימתח אליה אחר כך.
    #
    # הסיבוב נכנס באותו מקום ומאותה סיבה. אחרי סיבוב של 90 מעלות
    # התוכנית **מוצגת** ביחס ההפוך, ולכן זה היחס שקובע את התיבה;
    # הרינדור נעשה בגודל המוחלף, והתמונה מסתובבת אליו בדיוק.
    shown_aspect = (1.0 / aspect) if rot in (90, 270) else aspect
    box = SL.plan_panel_box(_forced_aspect(shown_aspect, wide, layout), layout,
                            alone=alone, align=align)
    # `plan_size` — התיבה שאדם קבע. הרסטר מרונדר בגודל שבו יוצג,
    # אחרת תוכנית שהוגדלה ידנית נמתחת והקווים מתעבים (גיא, 12.10).
    w, h = plan_size or (box[2], box[3])
    size = (h, w) if rot in (90, 270) else (w, h)
    fr = framing.frame_for(pts, size)
    return inside, box, fr, size


def _lit_fixtures(s, sl, inside):
    """הגופים המוארים בשקופית. בחירה ידנית גוברת על שכבה ועל בלוק.

    **הצמצום לתת-אזור אינו כאן.** `inside` כבר מסונן לפי הפוליגון
    ב-`_area_geometry`, כי תת-אזור משנה גם את המסגור ולא רק את
    ההארה. שקופית הפתיחה היא היוצאת מן הכלל, ובה ממילא אין הארה.
    """
    if sl.picks:
        all_f = s["survey"].fixtures
        return [all_f[i] for i in sl.picks if 0 <= i < len(all_f)]
    # **שקופית הפתיחה של תת-אזור היא תוכנית ומסכה בלבד.** במצגת ייחוס א
    # 97 ו-105 אין בה ולו סמן הארה אחד — כל תפקידה לומר "לכאן אנחנו
    # נכנסים", וזוהר היה גונב את המבט מהמסכה.
    if sl.mask:
        return []
    lay = {l.lower() for l in sl.layers_lit}
    codes = {c.upper() for c in sl.codes}
    # **בלי בחירה — לא מאיר כלום, ולא מאיר הכל.** קודם רשימה ריקה
    # פירושה היה "בלי סינון", כלומר כל גופי האזור; הממשק לעומת זאת
    # מציג אפס נקודות צהובות. מי שמוריד את כל התיבות רואה תוכנית
    # כבויה ומקבל שקופית מוצפת. אותו כלל בשני הצדדים.
    if not lay and not codes:
        return []
    return [f for f in inside
            if (not lay or f.layer.lower() in lay)
            and (not codes or f.code.upper() in codes)]


def _slide_photos(sl, cat_assets, asset_idx, per_slide):
    """בחירת המתכנן גוברת; ברירת המחדל לפי קטגוריה היא רשת ביטחון.

    **שקופית פתיחה של תת-אזור אינה מקבלת תצלום מעצמה** (D-031).
    תפקידה לומר "לכאן אנחנו נכנסים"; תצלום בה הוא בחירה של אדם.
    """
    out = []
    for aid in sl.photos[:3]:
        p_ = LIB.image_path(aid)
        if os.path.exists(p_):
            out.append(p_)
    if not out and not sl.mask and not sl.photos_only:
        for r in cat_assets.get(sl.type, [])[:per_slide]:
            if r["asset_name"] in asset_idx:
                out.append(asset_idx[r["asset_name"]])
    return out


_glowed: "collections.OrderedDict" = collections.OrderedDict()
# תצוגת המצגת מרכיבה כל שקופית בנפרד. עם 8 ערכים היא הייתה מפנה
# את הפאנל של השקופית הראשונה עוד לפני שהגיעה לאחרונה, וכל גלילה
# חזרה הייתה מרנדרת מחדש. תמונה כזו היא ~1.5MB, וזה כלי מקומי.
_GLOW_MAX = 24


def _glow_panel(key, base, size, points, preset, cal):
    """פאנל התוכנית עם ההארה, ממוטמן.

    ההארה אינה תלויה בפריסה — הזזת התוכנית או של תצלום אינה משנה
    ולו פיקסל אחד בפאנל. בלי המטמון הזה כל גרירה הייתה מריצה את
    מנוע ההארה מחדש, וגרירה שמגיבה אחרי שנייה אינה גרירה.
    """
    with _lock:
        hit = _glowed.get(key)
        if hit is not None:
            _glowed.move_to_end(key)
            return hit
    img = (G.render_glow(size, points, preset, radius=cal["marker_radius_px"],
                         stack=cal["stack"], base=base) if points else base)
    with _lock:
        _glowed[key] = img
        while len(_glowed) > _GLOW_MAX:
            _glowed.popitem(last=False)
    return img


def _title_lines(area_name, sl):
    """**שורה אחת.** בייחוס הכותרת היא `חדר | קטגוריה | אופציה` על
    שורה אחת צמודה לקו הלבן; פיצול ל-"|" הפך אותה לשלוש שורות
    שדחפו את הטקסט למטה ולתוך הקו.
    """
    if (sl.title or "").strip():
        return [" | ".join(t.strip() for t in sl.title.split("|") if t.strip())]
    return [" | ".join(t for t in (area_name, sl.type, sl.option) if t)]


def _slide_label(n, area_name, sl):
    """איך שקופית נקראת בהודעה לעובד: המספר שלה בשלב 3 והכותרת."""
    return "שקופית " + str(n) + " · " + (_title_lines(area_name, sl)[0] or "(ללא כותרת)")


def _photo_gaps(spec):
    """שקופיות שאין בהן תצלום, ושאיש לא אמר שכך צריך.

    לא נספרות: שקופית פתיחה של תת-אזור (בלי תצלום מעצמה, D-031)
    ושקופית מאושרת — ✓ על שקופית בלי תצלום הוא החלטה של העובד.
    מחזיר [(אינדקס אזור, אינדקס שקופית, מספר במצגת)].
    """
    cat_assets = make_deck.load_category_assets()
    asset_idx = make_deck.load_asset_index()
    out, n = [], 0
    for ai, a in enumerate(spec.areas):
        for si, sl in enumerate(a.slides):
            n += 1
            if sl.mask or sl.done:
                continue
            if not _slide_photos(sl, cat_assets, asset_idx, spec.photos_per_slide):
                out.append((ai, si, n))
    return out


def _issue(spec, ai, si, n, text):
    a = spec.areas[ai]
    return {"area": ai, "slide": si,
            "text": text + ": " + _slide_label(n, a.name, a.slides[si])}


def _slide_blocker(s, a, sl, cat_assets, asset_idx, per_slide):
    """למה השקופית **לא תצא** במצגת, או None אם תצא (D-045).

    **הכלל היחיד** — ההפקה מדלגת לפיו ושלב 3 מזהיר לפיו, ולכן אין
    מצב ששלב 3 אומר דבר אחד וההפקה עושה אחר. שקופית פתיחה של
    תת-אזור היא תוכנית ומסכה, בלי הארה, ויוצאת תמיד.

    **שקופית תצלומים בלבד בלי תצלום לא תצא** (B-06): אין בה תוכנית,
    ולכן בלי תצלום היא כותרת וקו בלבד. גם ✓ לא משנה את זה — ✓ הוא
    החלטה "בלי תצלום", והשקופית הזו היא תצלומים ותו לא.
    """
    if sl.photos_only:
        if not _slide_photos(sl, cat_assets, asset_idx, per_slide):
            return "שקופית תצלומים בלבד, ואין בה תצלום"
        return None
    inside, _ = _area_fixtures(s, a, mask=bool(sl.mask))
    if not inside:
        return "האזור ריק מגופי תאורה"
    if sl.mask:
        return None
    if (not _lit_fixtures(s, sl, inside)
            and not _slide_photos(sl, cat_assets, asset_idx, per_slide)):
        return "אין בה גופים מוארים ואין תצלום"
    return None


@app.post("/api/deck_check")
def deck_check(spec: BuildSpec):
    """מה חסר במצגת — לפני ההפקה, בלי לרנדר דבר (שלב 3)."""
    s = load_drawing(spec.drawing)
    cat_assets = make_deck.load_category_assets()
    asset_idx = make_deck.load_asset_index()
    blocked = []
    for ai, a in enumerate(spec.areas):
        for si, sl in enumerate(a.slides):
            why = _slide_blocker(s, a, sl, cat_assets, asset_idx,
                                 spec.photos_per_slide)
            if why:
                blocked.append({"area": ai, "slide": si, "reason": why})
    # שקופית שלא תצא אינה מסומנת גם "בלי תצלום" — זו בעיה אחת, הגדולה
    stop = {(b["area"], b["slide"]) for b in blocked}
    # **גוף רחוק שהמסגור משאיר מחוץ לתמונה** (B-02): לא נבלע בשקט.
    # הנקודות תלויות באזור ובשקופית פתיחה בלבד, ולכן סופרים פעם אחת.
    far_by = {}
    far = []
    for ai, a in enumerate(spec.areas):
        for si, sl in enumerate(a.slides):
            if (ai, si) in stop:
                continue
            key = (ai, bool(sl.mask))
            if key not in far_by:
                inside, poly = _area_fixtures(s, a, mask=bool(sl.mask))
                if len(poly) >= 3:
                    far_by[key] = 0
                else:
                    far_by[key] = _cut_at_edge(inside, _area_box_world(s, a, bool(sl.mask)))
            if far_by[key]:
                far.append({"area": ai, "slide": si, "count": far_by[key]})
    return {"blocked": blocked, "far": far,
            "no_photo": [{"area": ai, "slide": si}
                         for ai, si, _ in _photo_gaps(spec) if (ai, si) not in stop]}


def _plan_layout(area, sl, wide):
    """הפריסה של התוכנית בשקופית אחרי נעילת האזור (D-047).

    מחזיר (דריסה, wide, יישור, נעולה). שקופית נעולה מקבלת את המיקום,
    הגודל, הסיבוב וה-wide של האזור, וכל מה שנשמר בה עצמה לתוכנית
    נזנח (התצלומים והכותרת שלה נשארים שלה). שקופית פתיחה של תת-אזור
    ותצלומים-בלבד אינן בנעילה: הראשונה היא תוכנית אחרת, ובשנייה אין
    תוכנית.
    """
    ov = dict(sl.geom or {})
    lock = area.plan_lock or {}
    if not lock or sl.mask or sl.photos_only or sl.plan_free:
        return ov, wide, "left", False
    ov.pop("plan", None)
    ov.pop("rot", None)
    if lock.get("plan"):
        ov["plan"] = lock["plan"]
    if lock.get("rot"):
        ov["rot"] = lock["rot"]
    w = lock.get("wide", -1)
    align = "center" if lock.get("align") == "center" else "left"
    return ov, (w if w in (0, 1) else -1), align, True


def _scene(drawing, project, layers, area, sl, s, layout, cal,
           wide, photos_per_slide, styles=None, rule=True):
    """כל מה שצריך כדי להראות שקופית אחת — ולייצא אותה.

    **התצוגה והייצוא קוראים שניהם לפונקציה הזו**, ולכן אין דרך שהם
    ייפרדו. כל מה שהם עושים בנפרד הוא לצייר את התוצאה.
    """
    look = layout["plan_appearance"]
    shown = set(layers) if layers else s["shown"]
    ov, wide, align, locked = _plan_layout(area, sl, wide)
    rot = _rot_of(ov)
    photos = _slide_photos(sl, make_deck.load_category_assets(),
                           make_deck.load_asset_index(), photos_per_slide)
    # הצד של הכותרת לפי שפתה — אותו טקסט שייכתב בשקופית
    title_kw = {"title_rtl": SL.title_is_rtl(_title_lines(area.name, sl)[0]),
                "rule": rule}
    # ריבוע אפור מאחורי תצלום מוצר — רק בסגנון שמגדיר אותו (D-050)
    cards = [False] * len(photos)
    if layout.get("photo_card"):
        prod = _product_ids()
        cards = [os.path.splitext(os.path.basename(p))[0] in prod for p in photos]
    if sl.photos_only:
        # אין תוכנית, אין הארה — רק תצלומים וכותרת (D-035)
        geom = SL.resolve(None, layout, [SL._image_size(p) for p in photos],
                          n_title_lines=1, override=ov, **title_kw)
        return {"panel": None, "key": "photos-only", "geom": geom,
                "photos": photos, "lit": [], "fr": None, "shown": shown,
                "ring": [], "cards": cards}
    # בלי תצלום התוכנית עוברת למרכז השקופית — אבל לא בשקופית נעולה:
    # זו בדיוק ה"קפיצה" שהנעילה באה למנוע.
    alone = not photos and not locked
    geo = _area_geometry(s, None, area, layout, wide=wide, rot=rot,
                         mask=bool(sl.mask), alone=alone, align=align)
    if geo is None:
        return None
    inside, box, fr, size = geo
    geom = SL.resolve(box, layout, [SL._image_size(p) for p in photos],
                      n_title_lines=1, override=ov, **title_kw)
    # תוכנית שאדם שינה את גודלה מרונדרת מחדש בגודל הזה — כ-5 שניות,
    # ורק כשהגודל השתנה. הזזה בלבד אינה משנה את המפתח.
    if tuple(geom["plan"][2:]) != (box[2], box[3]):
        geo = _area_geometry(s, None, area, layout, wide=wide, rot=rot,
                             mask=bool(sl.mask), plan_size=geom["plan"][2:],
                             alone=alone, align=align)
        inside, box, fr, size = geo
    pw, ph = size

    styles = _layer_styles(s, styles)
    base = _plan_panel(drawing, s["player"], shown, fr.window, (pw, ph), look,
                       styles)
    to_panel, panel_scale = PR.make_transform(fr.window, (pw, ph))

    # ── שקופית הפתיחה של תת-אזור: המסכה נצרבת מתחת להארה ──
    # השרת מיישר את הפוליגון בעצמו ולא סומך על הדפדפן, כדי שמסכה
    # עקומה לא תוכל להגיע למצגת. `_plan_panel` מחזיר תמונה מהמטמון
    # והיא משותפת לשקופיות אחרות, ולכן `SA.render` מחזיר חדשה.
    ring = SA.close_ring([(p[0], p[1]) for p in (area.poly or []) if len(p) >= 2])
    if len(ring) >= 3:
        poly_px = [to_panel(x, y) for x, y in ring]
        if sl.mask:
            base = SA.render(base, poly_px)      # פתיחה: המסכה על השלם
        else:                                    # עבודה: רק הצורה עצמה
            base = SA.clip(base, poly_px,
                           _rgb(look.get("background") or "#000000"))
    # ── אזור רגיל: רק המלבן שגזרו ──
    # החלון גדול מהגזירה (שוליים, והתאמה לצורת הפאנל), ובלי זה נכנסו
    # לשקופית חלקים מהחדרים השכנים שהעובד לא ביקש (גיא: "האם הגזירה
    # היא הגזירה המדויקת?"). אותו חיתוך כמו בתת-אזור: השוליים נשארים,
    # אבל ריקים. ההארה מצוירת אחר כך ורשאית לגלוש מעט.
    cut = _cut_ring(s, area, sl, ring)
    if cut:
        base = SA.clip(base, [to_panel(x, y) for x, y in cut],
                       _rgb(look.get("background") or "#000000"))

    lit = _lit_fixtures(s, sl, inside)
    preset = G.preset_for(project or None, sl.type or None)
    # סגנון שמגדיר הארה משלו (האפור: מיזוג רגיל, נקודה זהובה) גובר
    if layout.get("glow"):
        preset = dict(preset, **layout["glow"])
    preset = G.apply_slide_choice(preset, sl.glow)
    pts = []
    if lit:
        pts = [G.shape_for(f, to_panel, panel_scale, cal["marker_radius_px"])
               for f in lit]
    # הסיבוב נכנס למפתח אף שהוא מוחל אחרי המטמון: הדפדפן שומר את
    # הפאנל לפי המפתח הזה, ובלעדיו סיבוב היה מחזיר "אותו פאנל" —
    # והתמונה על המסך לא הייתה מסתובבת.
    key = hashlib.sha1(repr((
        drawing, sorted(shown), tuple(round(v, 3) for v in fr.window),
        (pw, ph), sorted(G.shape_key(sh) for sh in pts),
        str(preset), rot,
        [(round(x, 2), round(y, 2)) for x, y in ring], bool(sl.mask),
        [(round(x, 2), round(y, 2)) for x, y in cut],
        _style_key(styles),
    )).encode("utf-8")).hexdigest()[:16]
    panel = _glow_panel(key, base, (pw, ph), pts, preset, cal)
    if rot in _ROT:
        panel = panel.transpose(_ROT[rot])
    return {"panel": panel, "key": key, "geom": geom, "photos": photos,
            "lit": lit, "fr": fr, "shown": shown, "ring": ring, "cards": cards}


def _product_ids():
    """מזהי התצלומים שהם צילום מוצר (גוף על רקע לבן)."""
    return {a["asset_id"] for a in LIB.load() if a.get("is_product")}


class PreviewSpec(BaseModel):
    drawing: str
    project: str = ""
    layers: list[str] = []
    layer_styles: dict = {}
    area: AreaSpec
    slide: SlideSpec
    wide: int = -1        # -1 אוטומטי, 0 צר, 1 רחב
    photos_per_slide: int = 1
    title_rule: bool = True
    deck_style: str = ""
    # מפתח הפאנל שכבר יש לדפדפן. זהה = לא שולחים את התמונה שוב.
    have_panel: str = ""


@app.post("/api/slide")
def slide_scene(spec: PreviewSpec):
    """פאנל התוכנית המואר, והגיאומטריה כמספרים.

    גיא: "למה אני לא יכול להזיז את השרטוט ואת התמונה ולסדר כמו שאני
    רוצה?" תמונה מוכנה מהשרת אינה יכולה להיגרר. לכן השרת שולח את
    החלק שרק הוא יודע לייצר — התוכנית עם ההארה — ואת המספרים, והדפדפן
    מרכיב את השקופית. גרירה מגיבה מיד ולא בסבב לשרת.

    **המספרים כאן הם אותם מספרים שהייצוא משתמש בהם** (`slide.resolve`),
    ולכן התצוגה עדיין אינה יכולה להראות משהו אחר ממה שייצא.
    """
    s = load_drawing(spec.drawing)
    layout = SL.load_layout(spec.deck_style)
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]

    sc = _scene(spec.drawing, spec.project, spec.layers, spec.area, spec.slide,
                s, layout, cal, spec.wide, spec.photos_per_slide,
                spec.layer_styles, spec.title_rule)
    if sc is None:
        raise HTTPException(400, "האזור ריק מגופי תאורה")
    panel, key, geom, photos = sc["panel"], sc["key"], sc["geom"], sc["photos"]

    out = {
        "panel_key": key,
        "reuse": key == spec.have_panel,
        "canvas": list(geom["canvas"]),
        "rule": list(geom["rule"]) if geom["rule"] else None,
        # מקום הפס גם כשהוא כבוי — קווי העזר בגרירה נצמדים לשוליים שלו
        "rule_guide": [layout["header_rule"][k] for k in ("x", "y", "width", "height")],
        "auto_plan": list(geom["auto_plan"]) if geom["auto_plan"] else None,
        "plan": list(geom["plan"]) if geom["plan"] else None,
        "photos": [list(b) if b else None for b in geom["photos"]],
        "title": {"box": list(geom["title"]["box"]),
                  "sizes": geom["title"]["sizes"],
                  "rtl": geom["title"]["rtl"]},
        # שם הקובץ במאגר הוא מזהה הנכס, ולכן הדפדפן יכול לטעון את
        # התצלום ישירות. כך גם ברירת מחדל לפי קטגוריה, שהעובד לא
        # בחר במפורש, מוצגת בתצוגה בדיוק כמו שהיא תיוצא.
        "photo_ids": [os.path.splitext(os.path.basename(p))[0] for p in photos],
        "font": layout["title"]["font"],
        # צבעי הסגנון (D-050) — הדפדפן לא מחזיק אותם בעצמו
        "look": {"background": layout["canvas"].get("background") or "#000000",
                 "title": layout["title"].get("color") or "#FFFFFF",
                 "rule": layout["header_rule"].get("color") or "#E0E0E0",
                 "card": (layout.get("photo_card") or {}).get("color")},
        "frames": [list(b) if b else None for b in (geom.get("frames") or [])],
        "cards": sc["cards"],
        # מה אפשר לבחור לזוהר, ומה צבע ברירת המחדל של הסגנון (D-051)
        "glow_options": G.load_presets().get("per_slide") or {},
        "glow_default": (layout.get("glow") or {}).get("color") or
                        G.preset_for(spec.project or None)["color"],
    }
    if not out["reuse"] and panel is not None:
        import base64
        buf = io.BytesIO()
        panel.save(buf, "PNG")
        out["panel"] = ("data:image/png;base64," +
                        base64.b64encode(buf.getvalue()).decode())
        out["panel_size"] = list(panel.size)
    return out


@app.post("/api/preview.png")
def preview_png(spec: PreviewSpec):
    """אותה שקופית, מורכבת בשרת — בדיקה שהמספרים אכן מרכיבים שקופית.

    הממשק מרכיב בדפדפן, עם הגופן האמיתי. המסלול הזה נשאר כדי
    שהגיאומטריה תהיה ניתנת לבדיקה בלי דפדפן.
    """
    import preview as PV
    s = load_drawing(spec.drawing)
    layout = SL.load_layout(spec.deck_style)
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]

    sc = _scene(spec.drawing, spec.project, spec.layers, spec.area, spec.slide,
                s, layout, cal, spec.wide, spec.photos_per_slide,
                spec.layer_styles, spec.title_rule)
    if sc is None:
        raise HTTPException(400, "האזור ריק מגופי תאורה")
    title = _title_lines(spec.area.name, spec.slide)[0]
    img = PV.render(sc["panel"], title, sc["photos"], layout, sc["geom"],
                    cards=sc["cards"])

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


def _deck_base(drawing):
    """שם הקובץ מתחיל בשם הפרויקט (B-19), כדי שבתיקיית הורדות עם עשר מצגות
    אפשר יהיה לדעת איזו שייכת למי. בלי תווים שוינדוס אוסרת, ובאורך סביר."""
    name = os.path.splitext(os.path.basename(drawing or ""))[0]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    name = re.sub(r"\s+", " ", name).strip(" .")[:50].strip(" .")
    return name or "deck"


@app.post("/api/build")
def build(spec: BuildSpec):
    s = load_drawing(spec.drawing)
    layout = SL.load_layout(spec.deck_style)
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]
    shown_layers = set(spec.layers) if spec.layers else s["shown"]

    slides_out = []
    # מה שהעובד רואה אחרי ההפקה: רק מה שאפשר לתקן, וכל שורה אומרת
    # איזו שקופית. הערות המסגור ("גופים מרוחקים", "חיתוך דליל") היו
    # כאן ורק הרעישו — העובד כבר ראה וסידר כל שקופית בתצוגה. הן
    # נשמרות במניפסט בלבד.
    issues = []
    framing_notes = []
    n = 0
    cat_assets = make_deck.load_category_assets()
    asset_idx = make_deck.load_asset_index()
    for ai, a in enumerate(spec.areas):
        for si, sl in enumerate(a.slides):
            n += 1
            # אותו כלל ששלב 3 מזהיר לפיו (D-045), ולפני הציור — שקופית
            # שלא תצא אינה מצוירת לחינם. **שקופית ריקה מהארה אינה בהכרח
            # שקופית ריקה:** פתיחה של תת-אזור היא תוכנית ומסכה בלבד.
            why = _slide_blocker(s, a, sl, cat_assets, asset_idx,
                                 spec.photos_per_slide)
            if why:
                issues.append(_issue(spec, ai, si, n, "לא יצאה — " + why))
                continue
            # **אותה `_scene` שהתצוגה קוראת לה.** קודם היה כאן העתק
            # שני של אותו חישוב, ושם התגלו שני מקרים שבהם התצוגה
            # הראתה דבר אחד והמצגת הוציאה אחר.
            sc = _scene(spec.drawing, spec.project, spec.layers, a, sl,
                        s, layout, cal, sl.wide, spec.photos_per_slide,
                        spec.layer_styles, spec.title_rule)
            if sc is None:          # לא אמור לקרות — `_slide_blocker` בודק את זה
                issues.append(_issue(spec, ai, si, n,
                                     "לא יצאה — האזור ריק מגופי תאורה"))
                continue
            for w in (sc["fr"].warnings if sc["fr"] else []):
                msg = "אזור '" + (a.name or "?") + "': " + w
                if msg not in framing_notes:
                    framing_notes.append(msg)

            # התמונה נשארת בזיכרון של ההפקה הזו בלבד. קודם היא נשמרה
            # בשם קבוע (`out/.ui_001.png`) שכל ההפקות חלקו, ושתי הפקות
            # בו-זמניות ערבבו תוכניות בין פרויקטים (B-01).
            img = None
            if sc["panel"] is not None:
                img = io.BytesIO()
                sc["panel"].save(img, "PNG")
                img.seek(0)
            slides_out.append({"plan": img, "geom": sc["geom"],
                               "title_lines": _title_lines(a.name, sl),
                               "photos": sc["photos"], "cards": sc["cards"]})

    photos_placed = sum(len(x.get("photos", [])) for x in slides_out)
    # שקופית שלא יצאה כבר דווחה למעלה — לא מדווחים עליה פעמיים
    skipped = {(i["area"], i["slide"]) for i in issues}
    issues += [_issue(spec, ai, si, k, "בלי תצלום")
               for ai, si, k in _photo_gaps(spec) if (ai, si) not in skipped]
    warnings = [i["text"] for i in issues]

    if not slides_out:
        raise HTTPException(400, "לא נוצרה אף שקופית. " + " | ".join(warnings))

    pptx = SL.stamped(OUT_DIR, _deck_base(spec.drawing), ".pptx")
    SL.build_pptx(pptx, slides_out, layout)
    remembered = _remember_exported_photos(spec)
    SL.write_manifest(os.path.splitext(pptx)[0] + ".manifest.json", {
        "drawing": spec.drawing,
        "dxf_sha1": make_deck.sha1_of(s["path"]),
        "slides": len(slides_out),
        "areas": [{
            "name": a.name,
            "box": [a.x0, a.y0, a.x1, a.y1],
            "parent": a.parent or None,
            "sub_area_poly": a.poly or None,
            "glow": [sl.glow or None for sl in a.slides],
            "plan_lock": a.plan_lock or None,
            "slides": [{
                "title": sl.title,
                "layers_lit": sl.layers_lit,
                "codes": sl.codes,
                "manual_picks": len(sl.picks),
                # פריסה שאדם הזיז. נרשמת כדי שאפשר יהיה לשחזר מצגת
                # מהמניפסט בלבד — חוק ברזל 5.
                "manual_layout": sl.geom or None,
                "sub_area_intro": bool(sl.mask),
                "photos_only": bool(sl.photos_only),
            } for sl in a.slides],
        } for a in spec.areas],
        "layers_shown": sorted(shown_layers),
        # עובי ובהירות שהעובד קבע — בלעדיהם אי אפשר לשחזר את המראה
        "layer_styles": _layer_styles(s, spec.layer_styles) or None,
        "title_rule": spec.title_rule,
        "deck_style": spec.deck_style or "black",
        "photos_placed": photos_placed,
        "glow_project": spec.project, "glow_calibration": cal,
        "warnings": warnings, "framing_notes": framing_notes, "source": "ui",
        "photo_choices_remembered": remembered,
    })
    return {"file": os.path.basename(pptx), "slides": len(slides_out),
            "warnings": warnings, "issues": issues}


@app.get("/api/recent_decks")
def recent_decks(limit: int = 5):
    """המצגות האחרונות שהופקו (B-12). אחרי רענון באמצע הפקה הקישור נעלם
    מהמסך, אבל הקובץ קיים — כאן מוצאים אותו שוב."""
    rows = []
    try:
        for f in os.listdir(OUT_DIR):
            if f.lower().endswith(".pptx") and not f.endswith(".partial"):
                st = os.stat(os.path.join(OUT_DIR, f))
                rows.append({"file": f, "mtime": st.st_mtime,
                             "mb": round(st.st_size / 1e6, 1)})
    except OSError:
        pass
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return {"decks": rows[:max(1, min(limit, 20))]}


@app.get("/api/download")
def download(file: str):
    p = os.path.join(OUT_DIR, os.path.basename(file))
    if not os.path.exists(p):
        raise HTTPException(404, "לא נמצא")
    return FileResponse(p, filename=os.path.basename(p))


# ─── מאגר התצלומים ────────────────────────────────────────────────

LIBRARY_DIR = os.path.join(ROOT, "library")


def _asset_row(a):
    """רק מה שהממשק צריך. שדות פנימיים לא נשלחים."""
    return {
        "id": a["asset_id"],
        "name": a["name"],
        "kind": a.get("kind") or "",
        "manufacturer": a.get("manufacturer") or "",
        "tags": a["tags"],
        # החלל מוצג ואינו מסנן — הוא מספר איפה הגוף שימש פעם
        "rooms": a["crit_tags"].get("room", []),
        "install": (a["crit_tags"].get("install") or [""])[0],
        "n_projects": a["n_projects"],
        "direct": bool(a.get("direct")),
        # לא תויג עדיין בציר רך שנבחר (D-048) — מוצג מתחת לקו
        "untagged": bool(a.get("untagged")),
        "w": a.get("width"), "h": a.get("height"),
    }


@app.get("/api/photos/search")
def photos_search(category: str = "", tags: str = "", text: str = "",
                  rooms: str = "", code: str = "", lit: str = "",
                  auto: int = 0):
    """הספריה כפי שהעובד סינן אותה. השרטוט אינו משתתף בסינון.

    קודם היה כאן ניחוש כפול: הקטגוריה מהשרטוט סיננה, וקוד הבלוק
    דירג לפי דקורטיבי מול טכני. גיא: "הוא מניח מהשרטוט ואני לא
    רוצה את זה. אני רוצה שהעובד יסנן לפי מה שהוא רוצה."

    `category` נשאר, אך ורק כדי להעלות למעלה תצלום שכבר נבחר פעם
    לאותה קטגוריה — זיכרון של בחירה אנושית, לא הנחה על הגוף.
    """
    want = [t for t in tags.split("|") if t.strip()]
    want_rooms = [t for t in rooms.split("|") if t.strip()]
    # D-048: `lit` = הקטגוריות שדולקות בשקופית. כל עוד העובד לא נגע
    # בשבבים (`auto=1`), סוג ההתקנה שלהן מסומן מעצמו. מה שסומן כך
    # חוזר ב-`auto_tags`, כדי שהממשק יראה אותו כשבב דולק.
    auto_tags = []
    if auto:
        auto_tags = [t for t in LIB.auto_install([c for c in lit.split("|") if c])
                     if t not in want]
        want = want + auto_tags
    rows = LIB.search(tags=want, rooms=want_rooms, text=text,
                      category=category or None)
    return {
        "auto_tags": auto_tags,
        "n_untagged": sum(1 for a in rows if a.get("untagged")),
        "results": [_asset_row(a) for a in rows],
        "filters": LIB.filter_spec(want, want_rooms),
        "query_en": LIB.search_query(want, want_rooms, category or None),
        "total": len(LIB.load()),
    }


@app.get("/api/photos/img")
def photos_img(id: str, full: int = 0):
    """התמונה כפי שמגישים אותה — הגזורה, אלא אם ביקשו את המלאה.

    `full=1` מחזיר את המקור בלי חיתוך. עורך החיתוך צריך אותו:
    אי אפשר לתקן קופסה בזמן שמסתכלים על התוצאה שלה.
    """
    safe = "".join(c for c in id if c.isalnum())
    if not safe:
        raise HTTPException(404, "תצלום לא נמצא")
    p = (os.path.join(LIBRARY_DIR, safe + ".png") if full
         else LIB.image_path(safe))
    if not os.path.exists(p):
        raise HTTPException(404, "תצלום לא נמצא")
    return FileResponse(p, media_type="image/png")


def _stamp():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_tags(rows):
    """כתיבת asset_tags.csv בשלמותו, בלי לאבד עמודות."""
    import csv as _csv
    import tag_assets as TA
    cols = list(TA.COLS)
    for extra in ("reviewed_by", "reviewed_at"):
        if extra not in cols:
            cols.insert(cols.index("reviewed") + 1, extra)
    with io.open(TA.TAGS, "w", encoding="utf-8-sig", newline="") as fh:
        w = _csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows.values():
            w.writerow({c: r.get(c, "") for c in cols})
    LIB.asset_tags.cache_clear()
    LIB.load.cache_clear()


# ─── סקירת הבנק ואישורו ─────────────────────────────────────────
#
# גיא: "אם הקריטריונים לא נכונים — שהעובד יתקן ויאשר. אם החיתוך לא
# טוב — שיתקן. אם לא יכול — להסתיר ולשמור."
#
# שלוש פעולות בסדר הזה, והסתרה היא המוצא האחרון. אין מסלול מחיקה.

class TagSpec(BaseModel):
    asset_id: str
    values: dict = {}
    by: str = ""
    approve: bool = False


class CropSpec(BaseModel):
    asset_id: str
    x: int
    y: int
    w: int
    h: int
    by: str = ""


class HideSpec(BaseModel):
    asset_id: str
    hidden: bool = True
    by: str = ""
    reason: str = ""


@app.get("/api/bank")
def bank(only_unreviewed: int = 0, limit: int = 3000):
    """כל הבנק לסקירה — כולל המוסתרים, שאותם רואים רק כאן."""
    rows = []
    for a in LIB.load():
        if only_unreviewed and a["reviewed"]:
            continue
        rows.append({
            "id": a["asset_id"], "name": a["name"],
            "source": a.get("kind") or "", "hidden": a.get("hidden", False),
            "reviewed": a["reviewed"], "reviewed_by": a.get("reviewed_by", ""),
            "by_human": a.get("by_human", False),
            "projects": (a.get("used_in_projects") or "").split("|"),
            "tags": {k: v for k, v in a["crit_tags"].items()},
            "cropped": os.path.exists(os.path.join(
                LIBRARY_DIR, "crops", a["asset_id"] + ".png")),
        })
        if len(rows) >= limit:
            break
    total = len(LIB.load())
    return {"assets": rows, "total": total,
            "reviewed": sum(1 for a in LIB.load() if a["reviewed"]),
            "criteria": LIB.filter_spec()}


@app.post("/api/bank/tags")
def bank_tags(spec: TagSpec):
    """תיקון תגיות, ואישור. עבודת אדם גוברת על הגזירה."""
    import tag_assets as TA
    rows = TA.existing()
    r = rows.get(spec.asset_id) or {"asset_id": spec.asset_id}
    for k, v in spec.values.items():
        if k in ("install", "style", "finish", "beam", "cct", "room", "note"):
            r[k] = "|".join(v) if isinstance(v, list) else (v or "")
    if spec.approve:
        r["reviewed"] = "1"
        r["reviewed_by"] = spec.by
        r["reviewed_at"] = _stamp()
    rows[spec.asset_id] = r
    _write_tags(rows)
    return {"ok": True, "asset_id": spec.asset_id}


@app.post("/api/bank/crop")
def bank_crop(spec: CropSpec):
    import crop_photo as CP
    CP.save_crop(spec.asset_id, (spec.x, spec.y, spec.w, spec.h), spec.by)
    CP.apply_crop(spec.asset_id, LIBRARY_DIR)
    LIB.load.cache_clear()
    return {"ok": True}


@app.delete("/api/bank/crop")
def bank_crop_reset(asset_id: str):
    """ביטול חיתוך — התמונה חוזרת מלאה. המקור מעולם לא נגע."""
    import crop_photo as CP
    import csv as _csv
    rows = [r for r in _csv.DictReader(
        io.open(CP.CROPS, encoding="utf-8-sig"))
        if r.get("asset_id") != asset_id] if os.path.exists(CP.CROPS) else []
    with io.open(CP.CROPS, "w", encoding="utf-8-sig", newline="") as fh:
        w = _csv.DictWriter(fh, CP.CROP_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in CP.CROP_COLS})
    CP.apply_crop(asset_id, LIBRARY_DIR)
    LIB.load.cache_clear()
    return {"ok": True}


@app.post("/api/bank/hide")
def bank_hide(spec: HideSpec):
    LIB.set_hidden(spec.asset_id, spec.hidden, spec.by, spec.reason)
    return {"ok": True}


class PickSpec(BaseModel):
    category: str = ""
    asset_id: str
    tags: list[str] = []


def _remember_exported_photos(spec):
    """זיכרון המאגר: רק תצלומים שיצאו במצגת (D-038).

    קודם כל לחיצה על תצלום נרשמה כבחירה — גם ניסיון שבוטל מיד. עובד
    שבודק עשרה תצלומים הפך את כולם ל"מועדפים", ובבדיקת השמישות סשן
    אחד רשם 113. עכשיו נרשם מה שהעובד באמת הגיש ללקוח.
    צמד קטגוריה↔תצלום שכבר רשום אינו נרשם שוב — הפקה חוזרת של אותה
    מצגת לא מנפחת את הקובץ.
    """
    seen = {(r.get("category") or "", (r.get("asset_id") or "").strip())
            for r in LIB._choice_rows()}
    n = 0
    for a in spec.areas:
        for sl in a.slides:
            for aid in sl.photos[:3]:
                key = (sl.photo_category or "", aid)
                if not aid or key in seen:
                    continue
                LIB.record_choice(sl.photo_category, aid, sl.photo_tags,
                                  source="export")
                seen.add(key)
                n += 1
    return n


@app.post("/api/photos/pick")
def photos_pick(spec: PickSpec):
    """כל בחירה מחזקת את הקישור קטגוריה↔תצלום.

    זה מה שמצמצם את זמן החיפוש לאורך זמן: תצלום שנבחר פעם אחת
    מוצע ראשון בפעם הבאה ולא מחופש שוב.
    """
    LIB.record_choice(spec.category, spec.asset_id, spec.tags)
    return {"ok": True, "preferred": LIB.preferred(spec.category)}


class FetchSpec(BaseModel):
    url: str
    category: str = ""
    tags: list[str] = []
    name: str = ""


MAX_FETCH = 12 * 1024 * 1024


_DRAG_HINT = " אפשר לשמור את התמונה במחשב ולגרור אותה לכאן."


def _fetch_error_text(e):
    """הודעה בעברית פשוטה לכשל בהורדת תמונה (בלי טקסט טכני של פייתון)."""
    import socket
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 404:
            return "התמונה לא נמצאה בכתובת הזו (404)." + _DRAG_HINT
        if e.code in (401, 403):
            return ("האתר לא מרשה להוריד משם אוטומטית (%d)." % e.code) + _DRAG_HINT
        return ("האתר החזיר שגיאה (%d)." % e.code) + _DRAG_HINT
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "האתר לא ענה בזמן." + _DRAG_HINT
    if isinstance(e, urllib.error.URLError):
        if isinstance(e.reason, (TimeoutError, socket.timeout)):
            return "האתר לא ענה בזמן." + _DRAG_HINT
        return "השרת לא מצליח להגיע לאינטרנט, או שהכתובת לא קיימת." + _DRAG_HINT
    return "ההורדה נכשלה." + _DRAG_HINT


@app.post("/api/photos/fetch")
def photos_fetch(spec: FetchSpec):
    """הדבקת כתובת תמונה — נשמרת למאגר ומתויגת בהקשר הנוכחי.

    הורדה אוטומטית מאתרי יצרנים היא שבירה, ולכן האדם בוחר את
    התמונה והמערכת רק שומרת אותה. מה שנשמר פעם אחת לא מחופש שוב.
    """
    import urllib.request
    from PIL import Image

    url = (spec.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "כתובת לא תקינה")

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            data = r.read(MAX_FETCH + 1)
    except Exception as e:
        raise HTTPException(400, _fetch_error_text(e))

    if len(data) > MAX_FETCH:
        raise HTTPException(400, "התמונה גדולה מ-12MB")
    if "image" not in ctype and not data[:8].startswith(bytes([137, 80, 78, 71])):
        page = ctype.startswith("text/html")
        raise HTTPException(400,
            "זו כתובת של עמוד, לא של תמונה. פתח את התמונה, קליק ימני, "
            '"העתק כתובת תמונה" — והדבק אותה.' if page else
            "הכתובת אינה מצביעה על תמונה (%s)" % ctype)

    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise HTTPException(400, "הקובץ אינו תמונה תקינה")

    base = os.path.basename(urllib.parse.urlparse(url).path)
    return _save_to_library(data, im, spec.name or os.path.splitext(base)[0],
                            spec.category, spec.tags, "web")


def _save_to_library(data, im, name, category, tags, kind):
    """שמירת תמונה חדשה למאגר. משותף להדבקת קישור ולגרירת קובץ.

    הקובץ נקרא לפי hash התוכן, ולכן אותה תמונה שתגיע פעמיים —
    פעם מקישור ופעם מגרירה — היא נכס אחד ולא שניים.
    """
    aid = hashlib.sha1(data).hexdigest()[:12]
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    path = os.path.join(LIBRARY_DIR, aid + ".png")
    if not os.path.exists(path):          # לא דורסים קובץ קיים
        im.convert("RGB").save(path)

    name = (name or "").strip() or aid
    tags = [t for t in (tags or []) if t]
    if category and category not in tags:
        tags.insert(0, category)

    ap = os.path.join(ROOT, "knowledge", "assets.csv")
    known = {r["asset_id"] for r in LIB.load()}
    if aid not in known:
        with io.open(ap, "a", encoding="utf-8-sig", newline="") as fh:
            csv.writer(fh).writerow(
                [aid, name, kind, "", im.width, im.height,
                 " / ".join(tags), "", 1, "library/%s.png" % aid])
        LIB.load.cache_clear()
        _tag_new_asset(aid, tags)

    LIB.record_choice(category, aid, tags, source=kind)
    return {"ok": True, "id": aid, "name": name}


def _tag_new_asset(aid, tags):
    """תגיות של תמונה חדשה נכנסות גם ל-asset_tags.csv.

    בלי זה הן חיות רק במחרוזת ההקשר: הסינון עובד, אבל מסך הסקירה
    מראה "בלי תגיות" ואי אפשר לתקן או לאשר אותן. שתי הרשומות
    חייבות לומר את אותו דבר.
    """
    import tag_assets as TA
    crit = LIB.criteria()["criteria"]
    by_val = {v: k for k, f in crit.items() for v in f["values"]}
    row = {"asset_id": aid}
    for t in tags:
        key = by_val.get(t)
        if not key:
            continue
        cur = [x for x in (row.get(key) or "").split("|") if x]
        if t not in cur:
            cur.append(t)
        row[key] = "|".join(cur if crit[key].get("multi") else [t])
    if len(row) == 1:
        return
    rows = TA.existing()
    rows[aid] = row
    _write_tags(rows)


@app.post("/api/photos/upload")
async def photos_upload(file: UploadFile = File(...), category: str = Form(""),
                        tags: str = Form("")):
    """גרירת קובץ תמונה מהמחשב.

    יש אתרים שחוסמים הורדה ישירה, והקישור נכשל בלי שהעובד יבין
    למה. שמירה בשם וגרירה עוקפת את זה לגמרי.
    """
    from PIL import Image
    data = await file.read(MAX_FETCH + 1)
    if len(data) > MAX_FETCH:
        raise HTTPException(400, "התמונה גדולה מ-12MB")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise HTTPException(400, "הקובץ אינו תמונה")
    name = os.path.splitext(os.path.basename(file.filename or ""))[0]
    want = [t for t in (tags or "").split("|") if t.strip()]
    return _save_to_library(data, im, name, category, want, "uploaded")


def _lan_address():
    """הכתובת של המחשב ברשת המקומית. לא שולח דבר — UDP בלי חבילה."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


if __name__ == "__main__":
    import argparse
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true",
                    help="לאפשר גישה ממחשבים אחרים באותה רשת")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    # ברירת המחדל נשארת המחשב הזה בלבד: ברשת ציבורית (בית קפה) --lan
    # היה חושף שרטוטים ותצלומים של לקוחות לכל מי שמחובר.
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print(f"הממשק זמין ב-http://127.0.0.1:{args.port}")
    if args.lan:
        ip = _lan_address()
        if ip:
            print(f"ממחשבים אחרים ברשת: http://{ip}:{args.port}")
        print("כל מי שמתחבר עובד על אותם פרויקטים.")
    uvicorn.run(app, host=host, port=args.port, log_level="warning")
