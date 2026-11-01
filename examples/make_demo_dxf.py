"""Build the fictional demo drawing: examples/demo_apartment.dxf.

Everything in this repository is fictional. This script draws an invented
apartment from scratch, in code, so you can read exactly what is in it.

It copies the *structure* of a real lighting-design drawing, not its content:
  * centimetre units ($INSUNITS = 5)
  * architect layers named by the AIA/NCS convention (A-WALL, I-FURN, P-SANR ...)
  * the studio's lighting layers ("light up", "light wall", "light kir", "Strip")
    with fixtures as blocks (SH, SP, SUS, WA, TA, FOIL), linear strips as
    polylines and a large decorative pendant as a circle
  * the traps a real drawing has, on purpose:
      - $EXTMIN/$EXTMAX that lie (declared extents ~1000x too large)
      - a fixture legend drawn far to the side of the building
      - "light text" labels with reversed codes ("HS" = SH) and Hebrew stored
        as Latin keystrokes (old SHX fonts)
      - annotation/dimension layers that must be hidden

Run:  python examples/make_demo_dxf.py   (deterministic: same file every time)
"""
from __future__ import annotations

import math
import os

import ezdxf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "demo_apartment.dxf")

WALL_EXT = 25   # exterior wall thickness, cm
WALL_INT = 12   # interior wall thickness, cm

# Rooms: name, (x0, y0, x1, y1) in cm. Ground floor of an invented flat.
ROOMS = {
    "living":    (0, 550, 520, 1000),
    "kitchen":   (520, 550, 1000, 1000),
    "entry":     (1000, 700, 1200, 1000),
    "wc":        (1200, 820, 1500, 1000),
    "laundry":   (1200, 700, 1500, 820),
    "hall":      (1000, 550, 1200, 700),
    "storage":   (1200, 550, 1500, 700),
    "corridor":  (520, 450, 1500, 550),
    "master":    (0, 0, 520, 550),
    "ensuite":   (520, 0, 780, 250),
    "closet":    (520, 250, 780, 450),
    "kids":      (780, 0, 1100, 450),
    "bath":      (1100, 0, 1300, 450),
    "study":     (1300, 0, 1500, 450),
}
BALCONY = (0, 1000, 520, 1180)

# Openings in walls: (x0, y0, x1, y1) of a gap along a wall line.
# Doors get a leaf + swing arc; windows get glazing lines.
DOORS = [  # (hinge x, hinge y, width, direction of wall: 'h'|'v', swing sign)
    (1060, 1000, 90, "h", -1),   # front door
    (1000, 760, 80, "v", 1),     # entry -> kitchen
    (1260, 820, 70, "h", -1),    # wc
    (1260, 700, 70, "h", 1),     # laundry
    (1080, 550, 80, "h", 1),     # hall -> corridor
    (1300, 550, 80, "h", 1),     # storage
    (520, 460, 80, "v", -1),     # master -> corridor
    (560, 450, 80, "h", -1),     # closet
    (600, 250, 70, "h", -1),     # closet -> ensuite
    (860, 450, 80, "h", -1),     # kids
    (1160, 450, 80, "h", -1),    # bath
    (1360, 450, 80, "h", -1),    # study
]
WINDOWS = [  # on the exterior shell: (x0, y0, x1, y1)
    (120, 0, 400, 0), (860, 0, 1020, 0), (1360, 0, 1460, 0),
    (0, 160, 0, 400), (1500, 120, 1500, 380),
    (600, 1000, 900, 1000),
    (1500, 860, 1500, 960),
]
SLIDING = (60, 1000, 460, 1000)   # living -> balcony glass door
# Open-plan gaps: no door, no glass, just no wall.
OPEN = [(520, 570, 520, 985),     # living <-> kitchen
        (1015, 550, 1185, 550),   # hall <-> corridor
        (1015, 700, 1185, 700)]   # entry <-> hall


def add_layers(doc):
    spec = {
        # architecture (shown)
        "A-WALL": 7, "A-WALL-PATT": 8, "A-DOOR": 3, "A-GLAZ": 4, "A-FLOR": 8, "A-FLOR-HRAL": 8,
        "I-FURN": 9, "P-SANR": 9, "Q-CASE": 8, "S-COLS": 7,
        # architecture (hidden by knowledge/layer_profile.yaml)
        "A-ANNO-TEXT": 2, "G-ANNO-DIMS": 1, "A-FLOR-OVHD": 8,
        # the studio's lighting template
        "light up": 30, "light wall": 40, "light kir": 50, "light floor": 60,
        "Strip": 140, "light text": 2, "light dim": 1,
    }
    for name, color in spec.items():
        doc.layers.add(name, color=color)


def add_blocks(doc):
    """Fixture symbols. The engine draws the glow itself; these only need to
    look plausible if someone opens the file in a CAD viewer."""
    b = doc.blocks.new("SH")            # recessed downlight
    b.add_circle((0, 0), 6)
    b.add_circle((0, 0), 2.5)
    b = doc.blocks.new("SP")            # adjustable spot
    b.add_circle((0, 0), 5)
    b.add_lwpolyline([(-7, 0), (7, 0)])
    b.add_lwpolyline([(0, -7), (0, 7)])
    b = doc.blocks.new("SUS")           # pendant
    b.add_circle((0, 0), 12)
    b.add_circle((0, 0), 4)
    b = doc.blocks.new("WA")            # wall light
    b.add_lwpolyline([(-8, 0), (8, 0), (8, 5), (-8, 5)], close=True)
    b = doc.blocks.new("TA")            # wall light, small
    for r in (9, 5):
        b.add_circle((0, 0), r)
    b = doc.blocks.new("FOIL")          # linear system, block form
    b.add_lwpolyline([(-60, -2), (60, -2), (60, 2), (-60, 2)], close=True)
    b = doc.blocks.new("_ArchTick")     # dimension tick: must be ignored
    b.add_line((-2, -2), (2, 2))
    b = doc.blocks.new("DOOR-LEAF")     # an architect block on a non-light layer
    b.add_line((0, 0), (0, 1))


def _gap_box(x0, y0, x1, y1, depth):
    """A rectangle that cuts an opening through a wall, whatever its thickness."""
    from shapely.geometry import box
    if y0 == y1:
        return box(min(x0, x1), y0 - depth, max(x0, x1), y0 + depth)
    return box(x0 - depth, min(y0, y1), x0 + depth, max(y0, y1))


def wall_geometry():
    """Walls as real solid shapes: a 25 cm exterior shell, 12 cm partitions,
    and every door, window and open-plan gap cut out of them."""
    from shapely.geometry import LineString, box
    from shapely.ops import unary_union
    shell = box(-WALL_EXT, -WALL_EXT, 1500 + WALL_EXT, 1000 + WALL_EXT).difference(box(0, 0, 1500, 1000))
    parts = [shell]
    for x0, y0, x1, y1 in ROOMS.values():
        for a, b in (((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)),
                     ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))):
            parts.append(LineString([a, b]).buffer(WALL_INT / 2, cap_style=3))
    walls = unary_union(parts).intersection(
        box(-WALL_EXT, -WALL_EXT, 1500 + WALL_EXT, 1000 + WALL_EXT))
    cuts = []
    for hx, hy, w, d, _ in DOORS:
        cuts.append(_gap_box(hx, hy, hx + w, hy, 40) if d == "h" else _gap_box(hx, hy, hx, hy + w, 40))
    for g in WINDOWS + [SLIDING] + OPEN:
        cuts.append(_gap_box(*g, 40))
    walls = walls.difference(unary_union(cuts))
    return list(getattr(walls, "geoms", [walls]))


def wall_lines(msp):
    """Outline every wall piece (A-WALL) and hatch it (A-WALL-PATT), the way
    an architect's plan shows cut walls. Real plans carry thousands of hatch
    lines; the tool counts drawn primitives to decide whether a drawing really
    has an architectural background (fewer than 2,000 = no)."""
    for poly in wall_geometry():
        rings = [list(poly.exterior.coords)] + [list(r.coords) for r in poly.interiors]
        for ring in rings:   # single LINEs, as walls usually arrive from Revit/AutoCAD
            for a, b in zip(ring, ring[1:]):
                msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
        h = msp.add_hatch(dxfattribs={"layer": "A-WALL-PATT"})
        h.set_pattern_fill("ANSI31", scale=0.6)
        for k, ring in enumerate(rings):
            h.paths.add_polyline_path(ring, is_closed=True, flags=1 if k == 0 else 16)
    for cx, cy in ((520, 1000), (1000, 1000), (0, 550), (1500, 550)):
        msp.add_lwpolyline([(cx - 15, cy - 15), (cx + 15, cy - 15), (cx + 15, cy + 15),
                            (cx - 15, cy + 15)], close=True, dxfattribs={"layer": "S-COLS"})


def doors_and_windows(msp):
    for hx, hy, w, d, sign in DOORS:
        if d == "h":
            leaf_end = (hx, hy + sign * w)
            msp.add_line((hx, hy), leaf_end, dxfattribs={"layer": "A-DOOR"})
            start, end = (0, 90) if sign > 0 else (270, 360)
            msp.add_arc((hx, hy), w, start, end, dxfattribs={"layer": "A-DOOR"})
        else:
            leaf_end = (hx + sign * w, hy)
            msp.add_line((hx, hy), leaf_end, dxfattribs={"layer": "A-DOOR"})
            start, end = (0, 90) if sign > 0 else (90, 180)
            msp.add_arc((hx, hy), w, start, end, dxfattribs={"layer": "A-DOOR"})
    for x0, y0, x1, y1 in WINDOWS + [SLIDING]:
        # every window is in the exterior shell: frame on both faces + the glass
        if y0 == y1:
            out = -WALL_EXT if y0 == 0 else WALL_EXT
            for off in (0, out / 2, out):
                msp.add_line((x0, y0 + off), (x1, y1 + off), dxfattribs={"layer": "A-GLAZ"})
        else:
            out = -WALL_EXT if x0 == 0 else WALL_EXT
            for off in (0, out / 2, out):
                msp.add_line((x0 + off, y0), (x1 + off, y1), dxfattribs={"layer": "A-GLAZ"})


def rect(msp, x0, y0, x1, y1, layer, r=0):
    if r:
        msp.add_lwpolyline([(x0 + r, y0), (x1 - r, y0), (x1, y0 + r), (x1, y1 - r),
                            (x1 - r, y1), (x0 + r, y1), (x0, y1 - r), (x0, y0 + r)],
                           close=True, dxfattribs={"layer": layer})
    else:
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                           dxfattribs={"layer": layer})


def furniture(msp):
    F, S, Q = "I-FURN", "P-SANR", "Q-CASE"
    # living: L-sofa, coffee table, armchairs, TV unit, rug
    rect(msp, 40, 600, 300, 690, F, 8); rect(msp, 40, 690, 130, 860, F, 8)
    for x in (55, 140, 225):
        rect(msp, x, 610, x + 70, 660, F, 6)        # seat cushions
    rect(msp, 170, 730, 290, 810, F, 4)              # coffee table
    msp.add_circle((230, 770), 120, dxfattribs={"layer": F})   # round rug
    rect(msp, 360, 620, 440, 700, F, 10); rect(msp, 360, 790, 440, 870, F, 10)
    rect(msp, 470, 640, 505, 920, Q)                 # TV unit on the wall
    # kitchen: counters along top + right, sink, cooktop, island, dining
    rect(msp, 640, 935, 990, 990, Q); rect(msp, 935, 700, 990, 935, Q)
    rect(msp, 700, 945, 760, 980, S, 6)              # sink
    for cx in (850, 885):
        for cy in (952, 975):
            msp.add_circle((cx, cy), 9, dxfattribs={"layer": F})
    rect(msp, 760, 740, 900, 820, Q)                 # island
    for x in (775, 815, 855):
        msp.add_circle((x + 10, 725), 14, dxfattribs={"layer": F})   # stools
    rect(msp, 560, 600, 740, 690, F, 4)              # dining table
    for x in (575, 630, 685):
        rect(msp, x, 570, x + 40, 595, F, 4); rect(msp, x, 695, x + 40, 720, F, 4)
    # entry: bench + shoe cabinet
    rect(msp, 1020, 930, 1140, 985, Q); rect(msp, 1150, 720, 1190, 900, Q)
    # wc: toilet + sink
    msp.add_ellipse((1440, 910), (25, 0), 0.7, dxfattribs={"layer": S})
    rect(msp, 1470, 885, 1490, 935, S)
    rect(msp, 1230, 950, 1290, 990, S, 6)
    # laundry: washer + dryer + tub
    for x in (1230, 1300):
        rect(msp, x, 715, x + 60, 775, S, 4)
        msp.add_circle((x + 30, 745), 20, dxfattribs={"layer": S})
    rect(msp, 1420, 715, 1490, 805, S, 6)
    # storage shelves
    for y in (565, 605, 645):
        rect(msp, 1215, y, 1490, y + 30, Q)
    # master: bed, nightstands, desk/dresser
    rect(msp, 120, 230, 300, 440, F, 6)
    rect(msp, 135, 400, 205, 430, F, 6); rect(msp, 215, 400, 285, 430, F, 6)
    rect(msp, 70, 380, 110, 430, F); rect(msp, 310, 380, 350, 430, F)
    rect(msp, 30, 30, 200, 80, Q)
    # ensuite: shower, toilet, double vanity
    rect(msp, 530, 10, 650, 110, S); msp.add_line((530, 10), (650, 110), dxfattribs={"layer": S})
    msp.add_ellipse((740, 70), (0, 25), 0.7, dxfattribs={"layer": S})
    rect(msp, 660, 190, 770, 240, S, 6)
    # closet: wardrobes along both walls
    rect(msp, 530, 260, 580, 440, Q); rect(msp, 720, 260, 770, 440, Q)
    # kids: bed, desk, wardrobe
    rect(msp, 800, 20, 900, 220, F, 6); rect(msp, 810, 185, 890, 212, F, 6)
    rect(msp, 950, 20, 1090, 80, F); msp.add_circle((1010, 105), 22, dxfattribs={"layer": F})
    rect(msp, 1030, 250, 1090, 440, Q)
    # bath: bathtub, toilet, vanity
    rect(msp, 1110, 10, 1290, 90, S, 25); rect(msp, 1125, 22, 1275, 78, S, 20)
    msp.add_ellipse((1260, 200), (25, 0), 0.7, dxfattribs={"layer": S})
    rect(msp, 1110, 330, 1160, 440, S, 6)
    # study: desk, chair, bookshelf
    rect(msp, 1320, 20, 1490, 90, F); msp.add_circle((1405, 120), 22, dxfattribs={"layer": F})
    rect(msp, 1450, 150, 1490, 440, Q)
    # corridor: console
    rect(msp, 700, 460, 900, 490, Q)
    # balcony: railing, floor edge, planters, lounge chairs
    x0, y0, x1, y1 = BALCONY
    msp.add_lwpolyline([(x0, y0), (x0, y1), (x1, y1), (x1, y0)], dxfattribs={"layer": "A-FLOR-HRAL"})
    msp.add_lwpolyline([(x0 + 8, y0), (x0 + 8, y1 - 8), (x1 - 8, y1 - 8), (x1 - 8, y0)],
                       dxfattribs={"layer": "A-FLOR-HRAL"})
    for cx in (60, 260, 460):
        rect(msp, cx - 35, 1115, cx + 35, 1160, Q)
        msp.add_circle((cx, 1137), 28, dxfattribs={"layer": F})
    rect(msp, 120, 1030, 190, 1100, F, 10); rect(msp, 320, 1030, 390, 1100, F, 10)


def floor_tiles(msp):
    """Tile joints in wet rooms (A-FLOR is a shown layer, as in real plans)."""
    for room, step in (("bath", 30), ("ensuite", 30), ("wc", 30), ("laundry", 30),
                       ):
        x0, y0, x1, y1 = ROOMS[room]
        x0, y0, x1, y1 = x0 + 8, y0 + 8, x1 - 8, y1 - 8
        x = x0 + step
        while x < x1:
            msp.add_line((x, y0), (x, y1), dxfattribs={"layer": "A-FLOR"})
            x += step
        y = y0 + step
        while y < y1:
            msp.add_line((x0, y), (x1, y), dxfattribs={"layer": "A-FLOR"})
            y += step


def hidden_annotations(msp):
    """Room names, dimensions and ceiling lines: present in a real drawing,
    hidden by knowledge/layer_profile.yaml so they never reach the slide."""
    names = {"living": "סלון", "kitchen": "מטבח", "master": "חדר מאסטר",
             "kids": "חדר ילדים", "bath": "חדר רחצה", "study": "ספריה",
             "entry": "כניסה", "wc": "שירותי אורחים", "laundry": "חדר כביסה"}
    for key, he in names.items():
        x0, y0, x1, y1 = ROOMS[key]
        msp.add_text(he, dxfattribs={"layer": "A-ANNO-TEXT", "height": 18,
                                     "insert": ((x0 + x1) / 2 - 40, (y0 + y1) / 2)})
    for x0, x1 in ((0, 520), (520, 1000), (1000, 1500)):
        msp.add_line((x0, -80), (x1, -80), dxfattribs={"layer": "G-ANNO-DIMS"})
        msp.add_text(str(x1 - x0), dxfattribs={"layer": "G-ANNO-DIMS", "height": 12,
                                               "insert": ((x0 + x1) / 2, -70)})
        msp.add_blockref("_ArchTick", (x0, -80), dxfattribs={"layer": "G-ANNO-DIMS"})
    # Overhead/ceiling lines: in a real file this layer alone held 124,000
    # primitives and flooded the plan. Here: a 10 cm grid, hidden by the profile.
    for x in range(0, 1501, 10):
        msp.add_line((x, 0), (x, 1000), dxfattribs={"layer": "A-FLOR-OVHD"})
    for y in range(0, 1001, 10):
        msp.add_line((0, y), (1500, y), dxfattribs={"layer": "A-FLOR-OVHD"})


def grid(x0, y0, x1, y1, nx, ny):
    for i in range(nx):
        for j in range(ny):
            yield (x0 + (x1 - x0) * (i + 0.5) / nx, y0 + (y1 - y0) * (j + 0.5) / ny)


def lighting(msp):
    up, wall, kir, floor, strip = "light up", "light wall", "light kir", "light floor", "Strip"

    def blk(code, layer, xy, rot=0.0):
        msp.add_blockref(code, xy, dxfattribs={"layer": layer, "rotation": rot})

    # recessed downlights (SH): the backbone of every ceiling plan
    for room, nx, ny in (("living", 3, 2), ("kitchen", 3, 2), ("master", 2, 2),
                         ("kids", 2, 2), ("study", 1, 2), ("entry", 1, 2),
                         ("hall", 1, 1), ("storage", 2, 1), ("laundry", 2, 1),
                         ("wc", 1, 1), ("bath", 1, 2), ("ensuite", 2, 1),
                         ("closet", 1, 2)):
        x0, y0, x1, y1 = ROOMS[room]
        for xy in grid(x0 + 40, y0 + 40, x1 - 40, y1 - 40, nx, ny):
            blk("SH", up, xy)
    for x in range(600, 1500, 150):                 # corridor line
        blk("SH", up, (x, 500))
    # adjustable spots (SP): art wall in the living room, entry niche
    for y in (650, 770, 890):
        blk("SP", up, (445, y), 90)
    blk("SP", up, (1080, 950)); blk("SP", up, (1120, 950))
    # pendants (SUS): over the island and the dining table
    for x in (790, 830, 870):
        blk("SUS", up, (x, 780))
    for x in (610, 690):
        blk("SUS", up, (x, 645))
    # a large decorative pendant drawn at its real size: CIRCLE = "inflated"
    msp.add_circle((230, 770), 22, dxfattribs={"layer": up})
    # wall lights (WA): bedside reading lights + balcony
    blk("WA", wall, (90, 440)); blk("WA", wall, (330, 440))
    for x in (100, 260, 420):
        blk("WA", wall, (x, 1012), 180)
    blk("WA", wall, (1110, 140), 90); blk("WA", wall, (1110, 300), 90)
    # mirror lights (TA) in the bathrooms, on "light kir"
    for x in (690, 740):
        blk("TA", kir, (x, 244))
    blk("TA", kir, (1106, 385))
    # linear system (FOIL) over the kitchen counter
    blk("FOIL", wall, (815, 930))
    # linear LED strips: polylines on "Strip" and "light wall"
    msp.add_lwpolyline([(478, 630), (478, 930)], dxfattribs={"layer": wall})       # TV cove
    msp.add_lwpolyline([(645, 940), (930, 940), (930, 705)], dxfattribs={"layer": strip})  # under cabinets
    msp.add_lwpolyline([(125, 445), (295, 445)], dxfattribs={"layer": strip})       # headboard
    msp.add_lwpolyline([(1325, 95), (1485, 95)], dxfattribs={"layer": strip})       # under desk shelf
    msp.add_lwpolyline([(705, 494), (895, 494)], dxfattribs={"layer": wall})        # corridor console
    # floor uplights in the balcony planters
    for cx in (60, 260, 460):
        blk("TA", floor, (cx, 1137))


def light_text(msp):
    """Labels the way they appear in real drawings: codes reversed (typed in
    an RTL field), Hebrew as Latin keystrokes of an old SHX font."""
    for x, y, raw in ((200, 520, "HS"), (445, 600, "PS"), (830, 830, "SUS"),
                      (120, 470, "AW"), (700, 270, "AT"),
                      (700, 905, "vfbv k,turv ctrubu,"),          # "הכנה לתאורה בארונות"
                      (300, 1050, "THGIL LLAW")):
        msp.add_text(raw, dxfattribs={"layer": "light text", "height": 10, "insert": (x, y)})


def legend(msp):
    """The fixture legend, drawn far to the left of the building, as studios do.
    Its symbols sit on the lighting layers, so a naive bounding box would
    stretch every slide across 250 metres of empty paper."""
    X, Y = -25000, 300
    rows = [("SH", "light up"), ("SP", "light up"), ("SUS", "light up"),
            ("WA", "light wall"), ("TA", "light kir"), ("FOIL", "light wall")]
    for i, (code, layer) in enumerate(rows):
        y = Y + i * 90
        msp.add_blockref(code, (X, y), dxfattribs={"layer": layer})
        msp.add_text(code[::-1], dxfattribs={"layer": "light text", "height": 14,
                                             "insert": (X + 60, y - 5)})
    rect(msp, X - 60, Y - 60, X + 400, Y + len(rows) * 90, "light text")


def build(path=OUT):
    doc = ezdxf.new("R2018", setup=False)
    doc.header["$INSUNITS"] = 5
    # Declared extents lie on purpose (written after save, see below):
    # real drawings are off by up to 128x.
    add_layers(doc)
    add_blocks(doc)
    msp = doc.modelspace()
    wall_lines(msp)
    doors_and_windows(msp)
    floor_tiles(msp)
    furniture(msp)
    hidden_annotations(msp)
    lighting(msp)
    light_text(msp)
    legend(msp)
    doc.saveas(path)
    _write_lying_extents(path)
    return path


def _write_lying_extents(path):
    """ezdxf resets $EXTMIN/$EXTMAX on save, so the lie is written afterwards,
    straight into the header text. Real drawings arrive like this."""
    import re
    with open(path, encoding="utf-8") as fh:
        txt = fh.read()
    for var, (x, y) in (("$EXTMIN", (-2_000_000, -1_500_000)),
                        ("$EXTMAX", (2_500_000, 1_800_000))):
        txt, n = re.subn(r"(\$%s\n *10\n)[^\n]*(\n *20\n)[^\n]*" % re.escape(var[1:]),
                         lambda m: "%s%s%s%s" % (m.group(1), float(x), m.group(2), float(y)), txt)
        assert n == 1, var
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(txt)


if __name__ == "__main__":
    print("wrote", build())
