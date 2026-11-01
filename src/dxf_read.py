"""קריאת DXF וחילוץ גופי התאורה של הסטודיו.

הזיהוי דטרמיניסטי ומבוסס על תבנית ה-DWG הקבועה של המשרד —
ראה knowledge/dxf_layers.yaml. אין כאן יוריסטיקה של מילות מפתח.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict

import ezdxf
import yaml

import dxftext

HERE = os.path.dirname(os.path.abspath(__file__))
KNOWLEDGE = os.path.join(HERE, "..", "knowledge")


def load_layer_rules(path=None):
    path = path or os.path.join(KNOWLEDGE, "dxf_layers.yaml")
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass
class Fixture:
    """גוף תאורה. `x,y` הוא תמיד נקודת הייחוס שלו.

    **לא כל גוף הוא נקודה.** בשכבות התאורה של המשרד יש שלושה סוגים,
    ושלושתם היו קיימים בשרטוט מהיום הראשון — הכלי פשוט קרא רק את
    הראשון (D-024):

      `point`   בלוק (INSERT). שקוע, צמוד תקרה, תלוי.
      `line`    פוליגון — פס לינארי. ב-`111 (2).dxf` יש 46 פתוחים
                ב-light wall/kir, ועוד 14 סגורים ב-light up שהם
                מלבנים דקיקים (1425x2, 550x3) — כלומר פסים.
      `circle`  מעגל עם רדיוס אמיתי (17.5, 32.0) — גוף שגודלו מצויר.
                זה ה"מנופח": ליבה אטומה בגודל שהמתכנן שרטט.

    `pts` בקואורדינטות השרטוט. `radius` ביחידות השרטוט.
    """
    code: str          # שם הבלוק = הקוד הקנוני של הגוף
    layer: str
    x: float
    y: float
    rotation: float = 0.0
    xscale: float = 1.0
    kind: str = "point"
    pts: tuple = ()            # ל-line: קודקודי הפוליגון
    radius: float = 0.0        # ל-circle: הרדיוס בשרטוט


@dataclass
class Annotation:
    text: str
    method: str
    raw: str
    layer: str
    x: float
    y: float


@dataclass
class DxfSurvey:
    path: str
    seconds: float
    insunits: int
    layer_count: int
    studio_layers: list = field(default_factory=list)
    xref_layers: int = 0
    has_architecture: bool = False
    fixtures: list = field(default_factory=list)
    annotations: list = field(default_factory=list)
    skipped_blocks: dict = field(default_factory=dict)
    arch_loose_entities: int = 0
    arch_inserted_entities: int = 0
    arch_total: int = 0

    def bounds(self, low=0.02, high=0.98):
        """גבולות חסינים מהגופים. $EXTMIN/$EXTMAX משקרים — ראה knowledge."""
        if not self.fixtures:
            return None
        xs = sorted(f.x for f in self.fixtures)
        ys = sorted(f.y for f in self.fixtures)

        def pct(a, q):
            return a[max(0, min(len(a) - 1, int(round(q * (len(a) - 1)))))]

        return (pct(xs, low), pct(ys, low), pct(xs, high), pct(ys, high))

    def raw_bounds(self):
        if not self.fixtures:
            return None
        xs = [f.x for f in self.fixtures]
        ys = [f.y for f in self.fixtures]
        return (min(xs), min(ys), max(xs), max(ys))


def survey(path, rules=None) -> DxfSurvey:
    rules = rules or load_layer_rules()
    sep = rules["xref_separator"]
    fixture_layers = {l.lower() for l in rules["fixture_layers"]}
    excluded = {l.lower() for l in rules["fixture_layers_excluded"]}
    bad_exact = set(rules["block_exclude_exact"])
    bad_prefix = tuple(rules["block_exclude_prefix"])

    t0 = time.time()
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    elapsed = time.time() - t0

    layers = [l.dxf.name for l in doc.layers]
    studio = [l for l in layers if sep not in l and l.lower() in fixture_layers]
    xref_layers = sum(1 for l in layers if sep in l)

    s = DxfSurvey(
        path=path,
        seconds=elapsed,
        insunits=doc.header.get("$INSUNITS", 0),
        layer_count=len(layers),
        studio_layers=studio,
        xref_layers=xref_layers,
    )

    def is_fixture_layer(name):
        n = (name or "").lower()
        return sep not in (name or "") and n in fixture_layers and n not in excluded

    # **גופי הגיאומטריה נאספים בנפרד ומצורפים בסוף.**
    # `slide.picks` שומר אינדקסים לתוך `fixtures`. שרשור הגופים
    # החדשים באמצע הרשימה היה מזיז כל אינדקס בכל פרויקט שמור,
    # והבחירות הידניות היו מצביעות על גופים אחרים.
    geoms = []

    def _poly_fixture(e, layer):
        try:
            pts = [(float(p[0]), float(p[1])) for p in e.get_points()]
        except Exception:
            return None
        if len(pts) < 2:
            return None
        if getattr(e, "closed", False):
            pts = pts + [pts[0]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Fixture(code="LINE", layer=layer, kind="line",
                       x=sum(xs) / len(xs), y=sum(ys) / len(ys),
                       pts=tuple(pts))

    for e in msp:
        t = e.dxftype()
        layer = e.dxf.layer
        if t == "LWPOLYLINE" and is_fixture_layer(layer):
            f = _poly_fixture(e, layer)
            if f is not None:
                geoms.append(f)
            continue
        if t == "CIRCLE" and is_fixture_layer(layer):
            c = e.dxf.center
            geoms.append(Fixture(code="CIRCLE", layer=layer, kind="circle",
                                 x=float(c.x), y=float(c.y),
                                 radius=float(e.dxf.radius or 0.0)))
            continue
        if t == "INSERT":
            name = e.dxf.name
            if name in bad_exact or name.startswith(bad_prefix):
                s.skipped_blocks[name] = s.skipped_blocks.get(name, 0) + 1
                continue
            if not is_fixture_layer(layer):
                continue
            p = e.dxf.insert
            s.fixtures.append(Fixture(
                code=name, layer=layer, x=float(p.x), y=float(p.y),
                rotation=float(getattr(e.dxf, "rotation", 0.0) or 0.0),
                xscale=float(getattr(e.dxf, "xscale", 1.0) or 1.0),
            ))
        elif t in ("TEXT", "MTEXT"):
            raw = e.plain_text() if t == "MTEXT" else (e.dxf.text or "")
            if not raw.strip():
                continue
            d = dxftext.decode(raw)
            p = e.dxf.insert if t == "MTEXT" else e.dxf.insert
            s.annotations.append(Annotation(
                text=d["text"], method=d["method"], raw=raw, layer=layer,
                x=float(p.x), y=float(p.y)))

    s.fixtures.extend(geoms)

    # ── האם הרקע האדריכלי בכלל בקובץ? ──────────────────────────────
    # ב-2 מתוך 4 קבצים אמיתיים הוא פשוט לא שם: שכבות ה-XREF קיימות
    # בטבלת השכבות אבל הגיאומטריה שלהן לא יוצאה. חייבים לדווח על זה
    # ולא להפיק בשקט תוכנית ריקה.
    template = {l.lower() for l in rules["fixture_layers"]} |                {l.lower() for l in rules["fixture_layers_excluded"]} | {"0"}

    def is_studio_layer(name):
        return (name or "").lower() in template

    GEOM = ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "HATCH",
            "ELLIPSE", "SPLINE", "SOLID", "3DFACE")

    # ספירת הגיאומטריה שאפשר לצייר בה רקע: ישויות חופשיות על שכבות
    # שאינן של הסטודיו, ועוד תוכן הבלוקים שמשובצים על שכבות כאלה.
    loose = 0
    inserted = 0
    block_size = {b.name: sum(1 for _ in b) for b in doc.blocks
                  if not b.name.startswith(("*", "_"))}
    for e in msp:
        t = e.dxftype()
        if t in GEOM and not is_studio_layer(e.dxf.layer):
            loose += 1
        elif t == "INSERT" and not is_fixture_layer(e.dxf.layer):
            inserted += block_size.get(e.dxf.name, 0)

    s.arch_loose_entities = loose
    s.arch_inserted_entities = inserted
    s.arch_total = loose + inserted
    # סף שמרני: פחות מ-500 ישויות ניתנות לציור אינו תוכנית אדריכלית.
    # נמדד: 111(2)=עשרות אלפים, 3=אלפים, 1=מאות בודדות, 2=כמעט אפס.
    s.has_architecture = s.arch_total >= 500
    return s
