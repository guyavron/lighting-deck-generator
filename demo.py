#!/usr/bin/env python3
"""
End-to-end demo on FICTIONAL data: from a DXF lighting plan to an editable
PowerPoint deck, without any client file and without an AI account.

    pip install -r requirements.txt
    python demo.py              # builds the demo data and a sample deck (~30 s)
    python demo.py --serve      # ...then opens the web interface on it

What it does, in the order a designer would:
  1. prepare the inputs: an invented apartment as a DXF (committed; drawn by
     examples/make_demo_dxf.py) and a photo bank (examples/make_demo_library.py)
  2. load the drawing the way the app does: fixtures by layer, the legend set
     aside, the architect's annotation layers hidden
  3. mark two areas (living + kitchen, master bedroom), as a worker does in step 1
     of the interface, and pick what is lit on each slide (step 2)
  4. render the plans, the glow and the photos, and write the PPTX (step 3)

Output: out/demo_apartment_<time>.pptx (git-ignored). Every element in it is a
separate PowerPoint object: the plan, each photo and the title can be moved.
"""
import argparse
import csv
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "examples"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DXF_NAME = "demo_apartment.dxf"

# Two areas in drawing units (cm), cut to include the outer walls, and what is
# lit on each slide. Photos are named as they are in the demo bank.
AREAS = [
    ("סלון ומטבח", (-30, 540, 1010, 1030), -1, [
        ("סלון ומטבח | שקועים", ["light up"], ["SH"],
         ["CEDAR_FLAT_012", "OSKARI LUX Disc 80 white"]),
        ("מטבח | תלוי", ["light up"], ["SUS"],
         ["CEDAR_FLAT_031", "CORVELLA Halo pendant black"]),
        ("סלון | פס לינארי", ["light wall", "Strip"], ["LINE"],
         ["HARBOR_LOFT_004", "TOBEK Line 40 profile"]),
    ]),
    ("חדר מאסטר", (-30, -30, 790, 560), 1, [
        ("חדר מאסטר | קירי", ["light wall", "light kir", "Strip"], [],
         ["OLIVE_HOUSE_008", "TOBEK Bowl sconce", "OLIVE_HOUSE_015"]),
    ]),
]


def step(n, text):
    print("\n[%d] %s" % (n, text))


def build_inputs(rebuild_dxf=False):
    import make_demo_library
    step(1, "Drawing the fictional inputs")
    path = os.path.join(ROOT, "examples", DXF_NAME)
    if rebuild_dxf or not os.path.exists(path):
        import make_demo_dxf              # needs shapely (requirements-dev.txt)
        path = make_demo_dxf.build()
    print("    drawing: " + os.path.relpath(path, ROOT))
    print("    photo bank: %d photos in library/" % make_demo_library.build())
    os.makedirs(os.path.join(ROOT, "DXF"), exist_ok=True)
    shutil.copyfile(path, os.path.join(ROOT, "DXF", DXF_NAME))


def build_deck():
    import library as LIB
    import server as SRV

    step(2, "Loading the drawing (first time ~10 s, then cached)")
    s = SRV.load_drawing(DXF_NAME)
    sv = s["survey"]
    print("    %d fixtures, %d set aside as the legend, background: %s" %
          (len(sv.fixtures), s["dropped"], "yes" if SRV._shows_architecture(s) else "NO"))

    # areas are stored in overview pixels, like the rectangle a worker drags
    x0w, y0w, x1w, y1w = s["window"]
    sx, sy = SRV.OVERVIEW_W / (x1w - x0w), SRV.OVERVIEW_H / (y1w - y0w)
    ids = {r["name"]: r["asset_id"] for r in
           csv.DictReader(open(os.path.join(ROOT, "knowledge", "assets.csv"), encoding="utf-8-sig"))}

    step(3, "Marking the areas and choosing what is lit")
    areas = []
    for name, (wx0, wy0, wx1, wy1), wide, slides in AREAS:
        areas.append(SRV.AreaSpec(
            name=name,
            x0=(wx0 - x0w) * sx, x1=(wx1 - x0w) * sx,
            y0=(y1w - wy1) * sy, y1=(y1w - wy0) * sy,
            plan_lock={"align": "center", "wide": wide},
            slides=[SRV.SlideSpec(title=t, layers_lit=lay, codes=codes,
                                  photos=[ids[p] for p in photos])
                    for t, lay, codes, photos in slides]))
        print("    %s: %d slide(s)" % (name, len(slides)))
    spec = SRV.BuildSpec(drawing=DXF_NAME, photos_per_slide=3, areas=areas)

    step(4, "Rendering and writing the deck")
    # The app remembers which photos were used, to suggest them first next
    # time (knowledge/asset_choices.csv). A demo run should not change that file.
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    tmp.close()
    os.remove(tmp.name)
    LIB.CHOICES = tmp.name
    res = SRV.build(spec)
    out = os.path.join(SRV.OUT_DIR, res["file"])
    print("    %d slides -> %s" % (res["slides"], os.path.relpath(out, ROOT)))
    for w in res.get("issues") or []:
        print("    ! %s" % w)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--serve", action="store_true",
                    help="after the demo, open the web interface on http://127.0.0.1:8000")
    ap.add_argument("--rebuild-dxf", action="store_true",
                    help="redraw examples/demo_apartment.dxf (needs shapely)")
    args = ap.parse_args()
    build_inputs(args.rebuild_dxf)
    out = build_deck()
    print("\nDone. Open %s in PowerPoint." % os.path.relpath(out, ROOT))
    if args.serve:
        import uvicorn
        import webbrowser
        print("\nWeb interface: http://127.0.0.1:8000  (Ctrl+C to stop)")
        webbrowser.open("http://127.0.0.1:8000")
        uvicorn.run("server:app", app_dir=os.path.join(ROOT, "src"),
                    host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
