"""רינדור תוכנית אדריכלית מ-DXF לקווי שיער לבנים על שחור.

יעד הרינדור אינו המצאה — הוא חולץ משכבת "קרקע הכל" ב-deck_b.psd
אל refcache/, וכך התוכנית צריכה להיראות: רקע שחור, קווי שיער
בהירים, קירות במילוי אפור.

הרינדור נעשה ב-supersampling ואז הקטנה, כי ל-PIL אין החלקת קצוות
לקווים, ובלעדיה קווי שיער נראים משוננים ולא כמו הייחוס.
"""
from __future__ import annotations

import os
import threading

import ezdxf
import numpy as np
import yaml
from ezdxf.addons.drawing import Frontend, RenderContext, recorder
from ezdxf.addons.drawing.backend import Backend
from ezdxf.addons.drawing.config import Configuration
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")


class PILBackend(Backend):
    """מצייר את הפרימיטיבים של ezdxf ישירות ל-PIL.

    כל הצבעים נדרסים לצבע אחיד — בייחוס אין צבעי CAD, שכבת
    Black & White מנטרלת אותם. ראה knowledge/layout.yaml.
    """

    def __init__(self, size, transform, line_color=(224, 224, 224),
                 fill_color=(192, 192, 192), width=1, draw_fills=True,
                 layers=None, styles=None):
        super().__init__()
        self.img = Image.new("RGB", size, (0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.t = transform
        self.line_color = line_color
        self.fill_color = fill_color
        self.width = width
        self.draw_fills = draw_fills
        # layers=None משמעו הכל. אחרת רק השכבות ברשימה — כך אפשר
        # להקליט פעם אחת ולרסטר הרבה פרופילי שכבות בזול.
        self.layers = set(layers) if layers is not None else None
        # {שכבה: (רוחב, צבע קו, צבע מילוי)} — מה שהעובד עיבה או הבהיר.
        # שכבה שאינה כאן מצוירת בברירת המחדל.
        self.styles = styles or {}
        self.counts = {"line": 0, "path": 0, "fill": 0, "point": 0}

    def _skip(self, properties):
        return self.layers is not None and properties.layer not in self.layers

    def _pt(self, v):
        return self.t(v.x, v.y)

    def _look(self, properties):
        st = self.styles.get(properties.layer)
        return st if st else (self.width, self.line_color, self.fill_color)

    def set_background(self, color):
        pass  # הרקע תמיד שחור

    def draw_point(self, pos, properties):
        if self._skip(properties):
            return
        x, y = self._pt(pos)
        self.d.point((x, y), fill=self._look(properties)[1])
        self.counts["point"] += 1

    def draw_line(self, start, end, properties):
        if self._skip(properties):
            return
        w, line, _ = self._look(properties)
        self.d.line([self._pt(start), self._pt(end)], fill=line, width=w)
        self.counts["line"] += 1

    def draw_solid_lines(self, lines, properties):
        for a, b in lines:
            self.draw_line(a, b, properties)

    def draw_path(self, path, properties):
        if self._skip(properties):
            return
        pts = [self._pt(v) for v in path.flattening(distance=0.05, segments=8)]
        if len(pts) > 1:
            w, line, _ = self._look(properties)
            self.d.line(pts, fill=line, width=w, joint="curve")
        self.counts["path"] += 1

    def draw_filled_polygon(self, points, properties):
        if self._skip(properties):
            return
        pts = [self._pt(v) for v in points.vertices()]
        if len(pts) > 2 and self.draw_fills:
            self.d.polygon(pts, fill=self._look(properties)[2])
        self.counts["fill"] += 1

    def draw_filled_paths(self, paths, properties):
        if self._skip(properties):
            return
        for p in paths:
            pts = [self._pt(v) for v in p.flattening(distance=0.05, segments=8)]
            if len(pts) > 2 and self.draw_fills:
                self.d.polygon(pts, fill=self._look(properties)[2])
        self.counts["fill"] += 1

    def draw_image(self, image_data, properties):
        pass  # תמונות משובצות אינן חלק ממראה הייחוס

    def configure(self, config):
        pass

    def clear(self):
        pass

    def finalize(self):
        pass


def load_profile(name="default"):
    p = os.path.join(KNOWLEDGE, "layer_profile.yaml")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return (yaml.safe_load(fh) or {}).get(name, {})


def record(path, layer_filter=None):
    """טוען DXF ומקליט את פרימיטיבי הציור, בלי לרסטר עדיין."""
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    ctx = RenderContext(doc)
    rec = recorder.Recorder()
    cfg = Configuration()
    Frontend(ctx, rec, config=cfg).draw_layout(msp, finalize=True)
    return rec.player()


def make_transform(window, out_size):
    """המרה מקואורדינטות שרטוט לפיקסלים.

    שומר על יחס הממדים תמיד — לעולם לא מותחים ולא חותכים תוכנית תאורה.
    משמש גם את הרינדור וגם את מיקום ההארה, כדי ששניהם יתיישרו בדיוק.
    """
    W, H = out_size
    x0, y0, x1, y1 = window
    span_x = max(x1 - x0, 1e-9)
    span_y = max(y1 - y0, 1e-9)
    scale = min(W / span_x, H / span_y)
    off_x = (W - span_x * scale) / 2
    off_y = (H - span_y * scale) / 2

    def t(x, y):
        return (off_x + (x - x0) * scale,
                H - (off_y + (y - y0) * scale))    # DXF: ציר Y כלפי מעלה

    return t, scale


def shade(rgb, b):
    """בהירות: 0 = כמו שהוא, 1 = לבן, -1 = שחור. קו ומילוי זזים יחד."""
    b = max(-1.0, min(1.0, float(b or 0)))
    if b >= 0:
        return tuple(int(round(c + (255 - c) * b)) for c in rgb)
    return tuple(int(round(c * (1 + b))) for c in rgb)


def layer_looks(styles, widths, base_width, line_color, fill_color):
    """{שכבה: {"w": "thick", "b": 0.3}} -> {שכבה: (רוחב, קו, מילוי)}.

    `widths` הם הכופלים מ-knowledge/layout.yaml. רוחב לפחות פיקסל
    אחד ברזולוציית הדגימה — "דק" נראה דק בזכות ההקטנה שאחריה.
    """
    out = {}
    for name, st in (styles or {}).items():
        st = st or {}
        f = widths.get(st.get("w") or "normal", 1.0)
        b = st.get("b") or 0
        if f == 1.0 and not b:
            continue
        out[name] = (max(1, int(round(base_width * f))),
                     shade(line_color, b), shade(fill_color, b))
    return out


# ─── ציור מגיאומטריה מוכנה ────────────────────────────────────────
#
# **נמדד:** ציור של `111 (2).dxf` = 5-9 שניות, בכל גודל, כי כל
# ציור הריץ מחדש את ההקלטה כולה — מאות אלפי פרימיטיבים, גם כשהחלון
# הוא חדר אחד. גיא (12.10): שינוי עובי "לא עשה כלום" ותת-אזור "טוען
# המון זמן" — הבקשות נערמו בשרת זו על זו.
#
# לכן ההקלטה מתורגמת **פעם אחת** למערכים: קודקודים בקואורדינטות
# השרטוט, תיבה תוחמת ושכבה לכל פרימיטיב. ציור הוא אז סינון וקטורי
# (שכבות מוצגות ∩ חלון) ומעבר רק על מה שנשאר, **באותו סדר כמו
# בהקלטה** — מילוי שבא אחרי קו מכסה אותו, בדיוק כמו קודם.

LINE, PATH, FILL, POINT = 0, 1, 2, 3


class _Collector(Backend):
    """אוסף את הפרימיטיבים בסדר ההקלטה, בלי לצייר."""

    def __init__(self, only=None):
        super().__init__()
        self.kind, self.layer, self.off = [], [], [0]
        self.xy = []
        self.layers = {}
        self.only = only

    def _skip(self, properties):
        return self.only is not None and properties.layer not in self.only

    def _add(self, kind, properties, pts):
        if not pts:
            return
        lid = self.layers.setdefault(properties.layer, len(self.layers))
        self.kind.append(kind)
        self.layer.append(lid)
        self.xy.extend(pts)
        self.off.append(len(self.xy))

    def set_background(self, color): pass
    def configure(self, config): pass
    def clear(self): pass
    def finalize(self): pass
    def draw_image(self, image_data, properties): pass

    def draw_point(self, pos, properties):
        if not self._skip(properties):
            self._add(POINT, properties, [(pos.x, pos.y)])

    def draw_line(self, start, end, properties):
        if not self._skip(properties):
            self._add(LINE, properties, [(start.x, start.y), (end.x, end.y)])

    def draw_solid_lines(self, lines, properties):
        for a, b in lines:
            self.draw_line(a, b, properties)

    def draw_path(self, path, properties):
        if self._skip(properties):
            return
        pts = [(v.x, v.y) for v in path.flattening(distance=0.05, segments=8)]
        if len(pts) > 1:
            self._add(PATH, properties, pts)

    def draw_filled_polygon(self, points, properties):
        if self._skip(properties):
            return
        pts = [(v.x, v.y) for v in points.vertices()]
        if len(pts) > 2:
            self._add(FILL, properties, pts)

    def draw_filled_paths(self, paths, properties):
        if self._skip(properties):
            return
        for p in paths:
            pts = [(v.x, v.y) for v in p.flattening(distance=0.05, segments=8)]
            if len(pts) > 2:
                self._add(FILL, properties, pts)


class Geometry:
    """ההקלטה כמערכים. קריאה בלבד אחרי הבנייה — בטוח בין תהליכונים."""

    def __init__(self, c: _Collector):
        self.names = list(c.layers)                       # מזהה -> שם
        self.kind = np.asarray(c.kind, dtype=np.uint8)
        self.layer = np.asarray(c.layer, dtype=np.int32)
        self.off = np.asarray(c.off, dtype=np.int64)
        self.xy = np.asarray(c.xy, dtype=np.float64).reshape(-1, 2)
        n = len(self.kind)
        self.bbox = np.zeros((n, 4))
        if n:
            idx = self.off[:-1]
            self.bbox[:, 0] = np.minimum.reduceat(self.xy[:, 0], idx)
            self.bbox[:, 1] = np.minimum.reduceat(self.xy[:, 1], idx)
            self.bbox[:, 2] = np.maximum.reduceat(self.xy[:, 0], idx)
            self.bbox[:, 3] = np.maximum.reduceat(self.xy[:, 1], idx)


_geo = {}
_geo_lock = threading.Lock()
_GEO_MAX = 4


def compiled(player, layers=None):
    """הגיאומטריה של השכבות המוצגות. נבנית פעם אחת לכל צירוף שכבות.

    **רק השכבות המוצגות.** בנייה של כולן נמדדה ב-3 דקות ו-9.2 מיליון
    קודקודים ב-`111 (2).dxf` — רובם בשכבות כבדות שאף אחד לא מציג
    (A-FLOR-OVHD לבדה 124 אלף פרימיטיבים). בנייה לצירוף אחד עולה
    הרצה אחת (~6 שניות, כמו ציור אחד בשיטה הקודמת), ומאז כל ציור —
    בכל חלון, גודל, עובי ובהירות — עולה כשנייה וחצי.
    """
    key = (id(player), frozenset(layers) if layers is not None else None)
    with _geo_lock:
        hit = _geo.get(key)
        if hit is not None and hit[0] is player:
            _geo[key] = _geo.pop(key)                  # הכי טרי בסוף
            return hit[1]
        c = _Collector(set(layers) if layers is not None else None)
        player.replay(c)
        g = Geometry(c)
        _geo[key] = (player, g)
        while len(_geo) > _GEO_MAX:
            _geo.pop(next(iter(_geo)))
        return g


def _fill_furniture(img, d, idx, flat, off, kind, lay, furn_ids, colour, width):
    """ריהוט במילוי לבן (הסגנון האפור, D-050) — מה ש**סגור בקווי הריהוט**.

    ב-111 (2) הספות והשולחנות הם קווים בודדים, לא צורות סגורות: 8,500
    הצורות הסגורות בשכבת I-FURN הן פרטים זעירים. לכן מציירים את קווי
    הריהוט למסכה, ומה שאינו מחובר לשולי התמונה — מוקף בהם — נצבע. אזור
    גדול מ-2% מהתמונה אינו רהיט אלא חדר שהריהוט סגר במקרה, ונשאר.

    דורש scipy. בלעדיו הריהוט נשאר קווים, והשאר מצויר כרגיל.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return
    W, H = img.size
    m = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(m)
    w = max(2, width)
    for i in idx.tolist():
        if lay[i] in furn_ids and kind[i] in (LINE, PATH):
            md.line(flat[off[i] * 2:off[i + 1] * 2], fill=255, width=w)
    free = np.asarray(m) == 0
    lab, n = ndimage.label(free)
    if not n:
        return
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    sizes = np.bincount(lab.ravel())
    ok = np.ones(n + 1, dtype=bool)
    ok[0] = False
    ok[edge] = False
    ok[sizes > 0.02 * W * H] = False
    inside = ok[lab]
    if inside.any():
        img.paste(Image.new("RGB", (W, H), colour),
                  mask=Image.fromarray((inside * 255).astype("uint8"), "L"))


def _render_geo(g, out_size, window, supersample, line_color, fill_color,
                draw_fills, line_width, layers, styles, widths,
                background=(0, 0, 0), furniture=None):
    W, H = out_size
    SW, SH = W * supersample, H * supersample
    if window is None:
        window = (g.xy[:, 0].min(), g.xy[:, 1].min(),
                  g.xy[:, 0].max(), g.xy[:, 1].max())
    x0, y0, x1, y1 = window
    span_x, span_y = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    scale = min(SW / span_x, SH / span_y)
    ox = (SW - span_x * scale) / 2
    oy = (SH - span_y * scale) / 2

    # מה שנכנס לחלון המצויר בפועל (כולל השוליים שנוצרים מהיחס)
    vx0, vx1 = x0 - ox / scale, x0 + (SW - ox) / scale
    vy0, vy1 = y0 - oy / scale, y0 + (SH - oy) / scale
    keep = ((g.bbox[:, 2] >= vx0) & (g.bbox[:, 0] <= vx1) &
            (g.bbox[:, 3] >= vy0) & (g.bbox[:, 1] <= vy1))
    if layers is not None:
        want = np.array([n in layers for n in g.names] or [False])
        keep &= want[g.layer]
    if not draw_fills:
        keep &= g.kind != FILL

    base_w = max(1, line_width * supersample)
    looks = layer_looks(styles, widths or {}, line_width * supersample,
                        line_color, fill_color)
    look_by_id = [looks.get(n, (base_w, line_color, fill_color)) for n in g.names]

    img = Image.new("RGB", (SW, SH), tuple(background))
    d = ImageDraw.Draw(img)
    counts = {"line": 0, "path": 0, "fill": 0, "point": 0}
    furn_ids = set()
    if furniture and furniture.get("fill") is not None:
        want_f = set(furniture.get("layers") or [])
        furn_ids = {i for i, n in enumerate(g.names) if n in want_f}
    idx = np.nonzero(keep)[0]
    if len(idx):
        # המרה וקטורית של כל הקודקודים בבת אחת, ואז פרוסות
        px = ox + (g.xy[:, 0] - x0) * scale
        py = SH - (oy + (g.xy[:, 1] - y0) * scale)
        pxy = np.empty(len(g.xy) * 2)
        pxy[0::2], pxy[1::2] = px, py
        flat = pxy.tolist()
        off, kind, lay = g.off.tolist(), g.kind.tolist(), g.layer.tolist()
        names = ("line", "path", "fill", "point")
        if furn_ids:
            _fill_furniture(img, d, idx, flat, off, kind, lay, furn_ids,
                            tuple(furniture["fill"]), base_w)
        for i in idx.tolist():
            a, b = off[i] * 2, off[i + 1] * 2
            k = kind[i]
            w, line, fill = look_by_id[lay[i]]
            pts = flat[a:b]
            if k == LINE:
                d.line(pts, fill=line, width=w)
            elif k == PATH:
                d.line(pts, fill=line, width=w, joint="curve")
            elif k == FILL:
                d.polygon(pts, fill=fill)
            else:
                d.point(pts, fill=line)
            counts[names[k]] += 1
    return img.resize((W, H), Image.LANCZOS), counts, scale


def render(player, out_size, window=None, supersample=3,
           line_color=(224, 224, 224), fill_color=(192, 192, 192),
           draw_fills=True, line_width=1, layers=None, styles=None,
           widths=None, background=(0, 0, 0), furniture=None):
    """מרסטר את ההקלטה לתמונה — מהגיאומטריה המוכנה (ראה למעלה).

    window — (xmin, ymin, xmax, ymax) ביחידות השרטוט. ברירת המחדל היא
    ה-bbox של ההקלטה, אבל בפרויקטים אמיתיים יש להעביר חלון חסין,
    כי $EXTMIN/$EXTMAX ואפילו הגיאומטריה מכילים חריגים.
    """
    return _render_geo(compiled(player, layers), out_size, window, supersample,
                       line_color, fill_color, draw_fills, line_width,
                       set(layers) if layers is not None else None,
                       styles, widths, background, furniture)


def render_replay(player, out_size, window=None, supersample=3,
                  line_color=(224, 224, 224), fill_color=(192, 192, 192),
                  draw_fills=True, line_width=1, layers=None, styles=None,
                  widths=None):
    """מרסטר את ההקלטה לתמונה.

    window — (xmin, ymin, xmax, ymax) ביחידות השרטוט. ברירת המחדל היא
    ה-bbox של ההקלטה, אבל בפרויקטים אמיתיים יש להעביר חלון חסין,
    כי $EXTMIN/$EXTMAX ואפילו הגיאומטריה מכילים חריגים.
    """
    W, H = out_size
    SW, SH = W * supersample, H * supersample

    if window is None:
        bb = player.bbox()
        window = (bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y)
    transform, scale = make_transform(window, (SW, SH))

    base_w = max(1, line_width * supersample)
    looks = layer_looks(styles, widths or {}, line_width * supersample,
                        line_color, fill_color)
    be = PILBackend((SW, SH), transform, line_color, fill_color,
                    width=base_w, draw_fills=draw_fills, layers=layers,
                    styles=looks)
    player.replay(be)
    img = be.img.resize((W, H), Image.LANCZOS)
    return img, be.counts, scale


class LayerCensus(Backend):
    """סופר פרימיטיבים לכל שכבה, בלי לצייר. משמש לבניית פרופיל שכבות."""

    def __init__(self):
        super().__init__()
        self.per_layer = {}

    def _bump(self, properties, n=1):
        self.per_layer[properties.layer] = self.per_layer.get(properties.layer, 0) + n

    def set_background(self, color): pass
    def configure(self, config): pass
    def clear(self): pass
    def finalize(self): pass
    def draw_image(self, image_data, properties): pass
    def draw_point(self, pos, properties): self._bump(properties)
    def draw_line(self, start, end, properties): self._bump(properties)
    def draw_solid_lines(self, lines, properties): self._bump(properties, sum(1 for _ in lines))
    def draw_path(self, path, properties): self._bump(properties)
    def draw_filled_polygon(self, points, properties): self._bump(properties)
    def draw_filled_paths(self, paths, properties): self._bump(properties)


# ─── מטמון ההקלטה (D-038) ───────────────────────────────────────
# **מקומי למחשב, לא בתיקיית הפרויקט.** הוא היה ב-out/.reccache, בתוך
# התיקייה המשותפת, וצבר 1.2GB שהסתנכרנו לענן — עותקי עבודה שהכלי יוצר מחדש
# מעצמו. בתיקייה המשותפת של המשרד יהיו הבנק, הפרויקטים והתוצרים;
# מטמון אינו שייך לשם. אפשר להפנות אותו בעזרת LIGHTING_CACHE_DIR.
#
# **המפתח הוא תוכן הקובץ, לא הנתיב.** קודם עותק של שרטוט — או אותו
# שרטוט בשם אחר — הוקלט מאפס (~דקה) ונשמר עוד פעם.
_CACHE_VERSION = "2"


def _default_cache_dir():
    env = os.environ.get("LIGHTING_CACHE_DIR")
    if env:
        return env
    base = os.environ.get("LOCALAPPDATA") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return os.path.join(base, "lighting-presentations", "reccache")


CACHE_DIR = _default_cache_dir()
_digests = {}


def _content_key(path):
    """sha1 של התוכן (+ גרסת ezdxf ומטמון). מחושב פעם אחת לקובץ שלא השתנה."""
    import hashlib
    st = os.stat(path)
    memo = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    if memo not in _digests:
        h = hashlib.sha1()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                h.update(chunk)
        h.update(f"|{ezdxf.__version__}|{_CACHE_VERSION}".encode())
        _digests[memo] = h.hexdigest()[:20]
    return _digests[memo]


def is_recorded(path):
    """האם ההקלטה כבר במטמון — כלומר הטעינה תהיה הקצרה."""
    return os.path.exists(os.path.join(CACHE_DIR, _content_key(path) + ".pickle"))


def record_cached(path, force=False):
    """מקליט DXF פעם אחת ושומר במטמון.

    הקלטת 111 (2).dxf לוקחת 39 שניות ורסטור מלא 144. בלי מטמון אי אפשר
    לכייל פרופיל שכבות, כי כל ניסיון עולה שלוש דקות.
    """
    import pickle

    cache = os.path.join(CACHE_DIR, _content_key(path) + ".pickle")
    if not force and os.path.exists(cache):
        try:
            with open(cache, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass      # מטמון פגום — מקליטים מחדש
    player = record(path)
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = cache + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(player, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cache)
    except Exception:
        pass          # מטמון הוא אופטימיזציה, לא נכס — כישלון בו אינו שגיאה
    return player


def census(player):
    be = LayerCensus()
    player.replay(be)
    return dict(sorted(be.per_layer.items(), key=lambda kv: -kv[1]))
