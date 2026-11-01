"""ייצור מצגת שלמה מקובץ אפיון.

ההלבשה — הרכבת כל שקופית בנפרד — היא ~48% מזמן העבודה (ראה D-012),
ולכן יחידת התוצר היא המצגת ולא השקופית.

    python src/make_deck.py --init "DXF/111 (2).dxf" > project.yaml
    # עורכים את project.yaml: שמות חדרים, אילו שקופיות, סדר
    python src/make_deck.py project.yaml

התצלומים אינם מולבשים אוטומטית בשלב זה — הצד הימני נשאר פנוי
והמתכנן גורר לשם תמונות ב-PowerPoint. זה מכוון: החיפוש הוא בעיה
נפרדת (~40% מהזמן) והוא תלוי במאגר.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import time

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dxf_read
import framing
import glow as G
import plan_render as PR
import profile_match as PM
import slide as SL
import taxonomy as TX


KNOWLEDGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "knowledge")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def load_asset_index():
    """שם נכס -> נתיב הקובץ במאגר. המאגר נזרע מקבצי ה-PSD הקיימים."""
    idx = {}
    p = os.path.join(KNOWLEDGE, "assets.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r.get("file"):
                full = os.path.join(ROOT, r["file"])
                if os.path.exists(full):
                    idx[r["name"]] = full
                    idx[r["asset_id"]] = full
    return idx


def load_category_assets():
    """קטגוריית תאורה -> תצלומים ששימשו לה בפועל, לפי ראיות מה-PSD."""
    out = {}
    p = os.path.join(KNOWLEDGE, "category_assets.csv")
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            out.setdefault(r["category"], []).append(r)
    return out


def sha1_of(path, limit=8 << 20):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
            limit -= len(chunk)
            if limit <= 0:
                break
    return h.hexdigest()[:16]


def pctl(sorted_vals, q):
    i = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[max(0, min(len(sorted_vals) - 1, i))]


def areas_of(survey, verbose=False):
    """אזורי השרטוט (קומות/אגפים), מהעליון לתחתון.

    מקרא הגופים מצויר לעיתים עשרות אלפי יחידות מהבניין, והוא משבש
    את החלוקה. לכן מסירים חריגים מרחביים לפני האשכול.
    """
    pts = [(f.x, f.y) for f in survey.fixtures]
    keep, dropped = framing.main_body(pts)
    if verbose and dropped:
        # ל-stderr: stdout שמור לפלט ה-YAML של --init
        print("  הוסרו " + str(len(dropped)) +
              " גופים חריגים הרחק מהבניין (כנראה מקרא גופים)",
              file=sys.stderr)
    return sorted(framing.clusters(keep, axis=1),
                  key=lambda g: -min(p[1] for p in g))


def init_spec(dxf_path):
    """טיוטת אפיון מתוך השרטוט: אילו אזורים יש, ואילו קטגוריות בכל אזור.

    העובד עורך את הטיוטה — משנה שמות חדרים, מוחק שקופיות, מוסיף
    אופציות. עדיף להתחיל ממשהו מלא מאשר מדף ריק.
    """
    survey = dxf_read.survey(dxf_path)
    areas = areas_of(survey, verbose=True)
    by_pt = {(f.x, f.y): f for f in survey.fixtures}

    code_to_type = {}
    for t in TX.load()["lighting_types"]:
        for c in t.get("dxf_blocks", []):
            code_to_type[c.upper()] = t["he"]

    # אזור עם מעט מדי גופים אינו קומה אלא שארית אשכול. שקופית ממנו
    # יוצאת ריקה כמעט, ולכן היא מסומנת ולא נוצרת כברירת מחדל.
    MIN_FIXTURES_PER_AREA = 8

    slides = []
    skipped = []
    for i, area in enumerate(areas):
        fixtures = [by_pt[p] for p in area if p in by_pt]
        if len(fixtures) < MIN_FIXTURES_PER_AREA:
            skipped.append((i, len(fixtures)))
            continue
        cats = {}
        for f in fixtures:
            key = code_to_type.get(f.code.upper(), f.code)
            cats.setdefault(key, []).append(f.code)
        for cat, codes in sorted(cats.items(), key=lambda kv: -len(kv[1])):
            slides.append({
                "area": i,
                "room": "אזור " + str(i + 1),
                "type": cat,
                "codes": sorted(set(codes)),
                "n_fixtures": len(codes),
            })
    for i, n in skipped:
        print("  אזור " + str(i) + " דולג: " + str(n) +
              " גופים בלבד (מתחת ל-" + str(MIN_FIXTURES_PER_AREA) + ")",
              file=sys.stderr)

    return {
        "dxf": dxf_path,
        "project": "deck_a",
        "title": os.path.splitext(os.path.basename(dxf_path))[0],
        "areas_detected": len(areas),
        "areas_skipped_as_too_small": [{"area": i, "n": n} for i, n in skipped],
        "slides": slides,
    }


def build(spec_path, outdir="out"):
    with open(spec_path, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)

    dxf_path = spec["dxf"]
    layout = SL.load_layout()
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]

    print("קורא " + dxf_path + " ...")
    survey = dxf_read.survey(dxf_path)
    if not survey.has_architecture:
        print("  ⚠ אין רקע אדריכלי בקובץ — השקופיות יכילו גופי תאורה בלבד.")

    player = PR.record_cached(dxf_path)
    prof = PM.load()
    shown = {l for l in PR.census(player) if PM.classify(l, prof) == "show"}
    app = layout["plan_appearance"]

    def rgb(h):
        return tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    areas = areas_of(survey, verbose=True)
    by_pt = {(f.x, f.y): f for f in survey.fixtures}

    asset_idx = load_asset_index()
    cat_assets = load_category_assets()
    max_photos = int(spec.get("photos_per_slide", 1))

    plan_cache = {}       # אותה קומה חוזרת בשקופיות רבות — מרנדרים פעם אחת
    slides_out = []
    warnings_all = []
    t0 = time.time()
    total = len(spec["slides"])

    for n, sl in enumerate(spec["slides"], 1):
        area_idx = sl.get("area", 0)
        if area_idx >= len(areas):
            print("  ⚠ שקופית " + str(n) + ": אזור " + str(area_idx) + " לא קיים, מדלג")
            continue
        area_fixtures = [by_pt[p] for p in areas[area_idx] if p in by_pt]

        codes = [c.upper() for c in sl.get("codes", [])]
        lit = [f for f in area_fixtures if not codes or f.code.upper() in codes]
        if not lit:
            print("  ⚠ שקופית " + str(n) + ": אין גופים תואמים, מדלג")
            continue

        # המסגור נגזר מכל גופי האזור ולא רק מהמוארים, כדי שהתוכנית
        # תישאר יציבה בין שקופיות של אותה קומה — כמו בייחוס.
        fr_pts = [(f.x, f.y) for f in area_fixtures]
        xs = sorted(p[0] for p in fr_pts)
        ys = sorted(p[1] for p in fr_pts)
        aspect = (max(pctl(xs, .98) - pctl(xs, .02), 1e-9) /
                  max(pctl(ys, .98) - pctl(ys, .02), 1e-9))
        px, py, pw, ph = SL.plan_panel_box(aspect, layout)
        fr = framing.frame_for(fr_pts, (pw, ph))
        for w in fr.warnings:
            msg = "אזור " + str(area_idx) + ": " + w
            if msg not in warnings_all:
                warnings_all.append(msg)

        key = (area_idx, pw, ph)
        if key not in plan_cache:
            plan_cache[key] = PR.render(
                player, (pw, ph), window=fr.window, supersample=3,
                line_color=rgb(app["architecture_line"]),
                fill_color=rgb(app["wall_fill"]), layers=shown)[0]

        t, tscale = PR.make_transform(fr.window, (pw, ph))
        preset = G.preset_for(spec.get("project", "deck_a"), sl.get("type"))
        # דרך `shape_for`, כמו הממשק — אחרת פס לינארי היה יוצא נקודה
        # ב-CLI ופס בממשק (D-024).
        shapes = [G.shape_for(f, t, tscale, cal["marker_radius_px"]) for f in lit]
        panel = G.render_glow((pw, ph), shapes, preset,
                              radius=cal["marker_radius_px"], stack=cal["stack"],
                              base=plan_cache[key])
        os.makedirs(outdir, exist_ok=True)
        # נשמר פאנל התוכנית בלבד, לא קנבס מלא — הוא מונח כאובייקט נפרד
        img = os.path.join(outdir, ".deck_%03d.png" % n)
        panel.save(img)

        # ── תצלומי הגופים ──
        # מפורש באפיון, ואם לא — הצעה מהמאגר לפי קטגוריית התאורה.
        wanted = list(sl.get("photos") or [])
        if not wanted and max_photos:
            for r in cat_assets.get(sl.get("type", ""), [])[:max_photos]:
                if r["asset_name"] in asset_idx:
                    wanted.append(r["asset_name"])
        paths = [asset_idx[w] for w in wanted if w in asset_idx][:max_photos]
        missing = [w for w in wanted if w not in asset_idx]
        for m in missing:
            note = "תצלום לא נמצא במאגר: " + str(m)
            if note not in warnings_all:
                warnings_all.append(note)
        title = [x for x in (sl.get("room"), sl.get("type"), sl.get("option")) if x]
        # התיבות נגזרות ב-`slide.resolve`, אותה פונקציה שהממשק קורא לה
        slides_out.append({"plan": img, "plan_box": (px, py, pw, ph),
                           "title_lines": title, "photos": paths})
        label = " | ".join(title)
        ph_note = ("  +%d תצלום" % len(paths)) if paths else ""
        print("  [%3d/%3d] %-46s %3d גופים%s" %
              (n, total, label[:46], len(lit), ph_note))

    pptx = SL.stamped(outdir, "deck", ".pptx")
    SL.build_pptx(pptx, slides_out, layout)
    SL.write_manifest(os.path.splitext(pptx)[0] + ".manifest.json", {
        "spec": os.path.basename(spec_path),
        "dxf": os.path.basename(dxf_path),
        "dxf_sha1": sha1_of(dxf_path),
        "slides": len(slides_out),
        "glow_project": spec.get("project"),
        "glow_calibration": cal,
        "layer_profile_shown": sorted(shown),
        "plans_rendered": len(plan_cache),
        "photos_placed": sum(len(s.get("photos", [])) for s in slides_out),
        "warnings": warnings_all,
        "seconds": round(time.time() - t0, 1),
    })
    elapsed = time.time() - t0
    print("")
    print("%d שקופיות, %d רינדורי תוכנית, %.0f שניות" %
          (len(slides_out), len(plan_cache), elapsed))
    if warnings_all:
        print("")
        print(str(len(warnings_all)) + " אזהרות:")
        for w in warnings_all[:8]:
            print("  ⚠ " + w[:110])
    print("")
    print("נוצר: " + pptx)
    return pptx


def main(argv=None):
    ap = argparse.ArgumentParser(description="הפקת מצגת תאורה שלמה")
    ap.add_argument("target", help="קובץ אפיון YAML, או DXF עם --init")
    ap.add_argument("--init", action="store_true", help="יצירת טיוטת אפיון מהשרטוט")
    ap.add_argument("--outdir", default="out")
    args = ap.parse_args(argv)
    if args.init:
        print(yaml.safe_dump(init_spec(args.target),
                             allow_unicode=True, sort_keys=False))
        return None
    return build(args.target, args.outdir)


if __name__ == "__main__":
    main()
