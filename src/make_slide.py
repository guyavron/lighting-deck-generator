"""שלב 1 — פרוסה אנכית: מקובץ DXF לשקופית PPTX אחת.

    python src/make_slide.py "DXF/111 (2).dxf" --room "חלל ראשי" --type שקועים

זהו ה-CLI. ממשק גרפי ייבנה מעליו אחרי שהצינור יוכיח את עצמו על
פרויקט אמיתי — ראה DECISIONS.md, D-005.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dxf_read
import framing
import glow as G
import plan_render as PR
import profile_match as PM
import taxonomy as TX
import slide as SL


def sha1_of(path, limit=8 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
            limit -= len(chunk)
            if limit <= 0:
                break
    return h.hexdigest()[:16]


def pick_fixtures(survey, codes=None, y_range=None):
    fx = survey.fixtures
    if codes:
        want = {c.upper() for c in codes}
        fx = [f for f in fx if f.code.upper() in want]
    if y_range:
        lo, hi = y_range
        fx = [f for f in fx if lo <= f.y <= hi]
    return fx


def main(argv=None):
    ap = argparse.ArgumentParser(description="הפקת שקופית תאורה מקובץ DXF")
    ap.add_argument("dxf")
    ap.add_argument("--project", default="deck_a", help="פריסט הארה מ-knowledge/glow.yaml")
    ap.add_argument("--room", default="", help="שם החלל לכותרת")
    ap.add_argument("--type", dest="ltype", default="", help="קטגוריית תאורה לכותרת")
    ap.add_argument("--codes", default="", help="קודי בלוקים להארה, מופרדים בפסיק")
    ap.add_argument("--floor", type=int, default=None,
                    help="אינדקס האזור (0 = התחתון)")
    ap.add_argument("--list-floors", action="store_true", help="מציג את האזורים שזוהו ויוצא")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--supersample", type=int, default=3)
    args = ap.parse_args(argv)

    print(f"קורא {args.dxf} ...")
    survey = dxf_read.survey(args.dxf)
    print(f"  {len(survey.fixtures)} גופי תאורה, {len(survey.annotations)} תוויות")
    if not survey.has_architecture:
        print("  ⚠ לא נמצא רקע אדריכלי בקובץ. השקופית תכיל גופי תאורה בלבד.")
        print("    ייתכן שה-XREF לא עבר BIND לפני הייצוא.")

    # בחירת הגופים להארה. כל שקופית מאירה תת-קבוצה אחרת — אלה
    # שמדברים עליהם בה. ראה knowledge/taxonomy.yaml.
    codes = [c.strip() for c in args.codes.split(",") if c.strip()]
    if not codes and args.ltype:
        resolved = TX.resolve(args.ltype)
        if resolved is None:
            print(f"  ⚠ קטגוריית תאורה '{args.ltype}' אינה מוכרת בטקסונומיה.")
        elif not resolved:
            print(f"  ⚠ לקטגוריה '{args.ltype}' אין מיפוי לקודי בלוקים. "
                  f"יש לציין --codes ידנית.")
        else:
            codes = resolved
            print(f"  קטגוריה '{args.ltype}' -> קודים {codes}")

    all_codes = sorted({f.code for f in survey.fixtures})
    unmapped = TX.describe_unmapped(all_codes)
    if unmapped:
        print(f"  קודים בשרטוט שאינם ממופים לקטגוריה: {', '.join(unmapped)}")

    chosen = pick_fixtures(survey, codes=codes or None)
    if not chosen:
        print(f"  ⚠ לא נמצאו גופים בקודים {codes}. נעשה שימוש בכולם.")
        chosen = survey.fixtures
    print(f"  {len(chosen)} גופים נבחרו להארה")

    # ── פיצול לאזורים/קומות ──
    groups = framing.clusters([(f.x, f.y) for f in chosen], axis=1)
    groups = sorted(groups, key=lambda g: min(p[1] for p in g))
    if len(groups) > 1 or args.list_floors:
        print(f"\n  זוהו {len(groups)} אזורים נפרדים (קומות או חדרים):")
        for i, g in enumerate(groups):
            ys = [p[1] for p in g]; xs = [p[0] for p in g]
            print(f"    [{i}] {len(g):3d} גופים   Y {min(ys):9.0f}..{max(ys):9.0f}"
                  f"   רוחב {max(xs)-min(xs):7.0f}")
        if args.list_floors:
            return None
        if args.floor is None:
            biggest = max(range(len(groups)), key=lambda i: len(groups[i]))
            print(f"    לא נבחר אזור (--floor). נבחר האזור הגדול ביותר: [{biggest}]")
            args.floor = biggest
    if args.floor is not None and len(groups) > 1:
        keep = set(map(tuple, groups[args.floor]))
        chosen = [f for f in chosen if (f.x, f.y) in keep]
        print(f"  אזור [{args.floor}]: {len(chosen)} גופים")

    layout = SL.load_layout()

    # ── מסגור ──
    pts = [(f.x, f.y) for f in chosen]
    xs = sorted(p[0] for p in pts); ys = sorted(p[1] for p in pts)
    def pct(a, q): return a[max(0, min(len(a) - 1, int(round(q * (len(a) - 1)))))]
    aspect = max(pct(xs, .98) - pct(xs, .02), 1e-9) / max(pct(ys, .98) - pct(ys, .02), 1e-9)
    px, py, pw, ph = SL.plan_panel_box(aspect, layout)
    fr = framing.frame_for(pts, (pw, ph))
    for w in fr.warnings:
        print(f"  ⚠ {w}")

    # ── רינדור התוכנית ──
    print("מרנדר תוכנית ...")
    player = PR.record_cached(args.dxf)
    prof = PM.load()
    shown = [l for l in PR.census(player) if PM.classify(l, prof) == "show"]
    app = layout["plan_appearance"]
    def rgb(h): return tuple(int(h.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    plan, counts, _ = PR.render(
        player, (pw, ph), window=fr.window, supersample=args.supersample,
        line_color=rgb(app["architecture_line"]), fill_color=rgb(app["wall_fill"]),
        layers=set(shown))
    print(f"  {counts}  |  {len(shown)} שכבות מוצגות")

    # ── הארה ──
    t, _scale = PR.make_transform(fr.window, (pw, ph))
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]
    preset = G.preset_for(args.project, args.ltype or None)
    shapes = [G.shape_for(f, t, _scale, cal["marker_radius_px"]) for f in chosen]
    panel = G.render_glow((pw, ph), shapes, preset,
                          radius=cal["marker_radius_px"], stack=cal["stack"],
                          base=plan)

    # ── ייצוא ──
    # פאנל התוכנית נשמר לבדו ומונח כאובייקט PPTX נפרד, כדי שניתן
    # יהיה להזיז אותו ולשנות את גודלו בלי לגעת בשאר השקופית.
    img_path = SL.stamped(args.outdir, "plan", ".png")
    panel.save(img_path)

    title = [x for x in (args.room, args.ltype) if x] or ["תאורה"]
    pptx_path = SL.stamped(args.outdir, "presentation", ".pptx")
    SL.build_pptx(pptx_path, [{"plan": img_path, "plan_box": (px, py, pw, ph),
                               "title_lines": title, "photos": []}], layout)

    SL.write_manifest(os.path.splitext(pptx_path)[0] + ".manifest.json", {
        "dxf": os.path.basename(args.dxf),
        "dxf_sha1": sha1_of(args.dxf),
        "fixtures_total": len(survey.fixtures),
        "fixtures_lit": len(chosen),
        "codes": codes,
        "has_architecture": survey.has_architecture,
        "glow_preset": {"project": args.project, **{k: v for k, v in preset.items() if k != "label"}},
        "glow_calibration": cal,
        "layer_profile": {"shown": sorted(shown)},
        "framing": {"window": list(fr.window), "panel_px": [pw, ph],
                    "fill_ratio": round(fr.fill_ratio, 3), "warnings": fr.warnings},
        "title": title,
    })
    print(f"\nנוצר: {pptx_path}")
    print(f"       {img_path}")
    return pptx_path


if __name__ == "__main__":
    main()
