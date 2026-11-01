"""Build the fictional photo bank: library/*.png + knowledge/asset*.csv.

In the real tool the bank is harvested from the studio's past presentations
(Photoshop files and decks), which is client material and is not in this repo.
Here product images are drawn in code (draw_products.py) with invented brands,
and the "studio photos" are free photos from Unsplash (examples/photos/,
Unsplash License, credited in examples/photos/CREDITS.md) filed under
invented project names.

What the bank demonstrates:
  * two kinds of photo: product cut-outs (with a brand) and "studio photos"
    (a lit interior, no brand)
  * tags on the studio's own axes (install type, style, finish, beam, CCT, room)
  * about a third of the photos have NO install type yet. That is on purpose:
    the real bank was half untagged, which is why the install filter is "soft"
    (untagged photos are shown below a line instead of disappearing).

Run:  python examples/make_demo_library.py   (deterministic)
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import draw_products  # noqa: E402
import glob           # noqa: E402

LIB = os.path.join(ROOT, "library")
KN = os.path.join(ROOT, "knowledge")
STAMP = "2026-10-25 12:00:00"
BY = "demo data"

# Invented brands (checked: no lighting manufacturer by these names).
OSK, COR, TOB = "OSKARI LUX", "CORVELLA", "TOBEK"

# name, kind, brand, drawing, context (floor / space / lighting type),
# install, style, finish, beam, cct, room
PRODUCTS = [
    ("OSKARI LUX Disc 80 white", "downlight", OSK, "לבן", "קרקע / סלון / שקועים",
     "שקוע בתקרה", "מינימליסטי", "לבן", "אור ישיר", "2700K — לבן חם", "סלון"),
    ("OSKARI LUX Disc 80 black", "downlight", OSK, "שחור", "קרקע / מטבח / שקועים",
     "שקוע בתקרה", "מינימליסטי", "שחור מאט", "אור ישיר", "3000K — לבן נעים", "מטבח"),
    ("OSKARI LUX Edge trimless", "trimless", OSK, "לבן מט", "ראשונה / מאסטר / שקועים",
     "שקוע בתקרה", "מינימליסטי", "לבן", "ספוט צר", "2700K — לבן חם", "חדר שינה הורים"),
    # "מערכת" (system) can be any of three track types, so it gets NO install
    # type until a person decides. tests/test_library.py enforces this rule.
    ("CORVELLA Orbit track spot", "trackspot", COR, "שחור", "קרקע / ספריה / מערכת",
     "", "מודרני", "שחור מאט", "זווית מתכווננת", "3000K — לבן נעים", "חדר עבודה"),
    ("CORVELLA Orbit wall spot", "wallspot", COR, "לבן", "קרקע / חלל ראשי / ספוטים",
     "", "מודרני", "לבן", "זווית מתכווננת", "3000K — לבן נעים", "סלון"),
    ("CORVELLA Halo pendant brass", "pendant", COR, "פליז מוברש", "קרקע / שולחן אוכל / תלוי פינת אוכל",
     "גוף תלוי", "מודרני", "פליז מוברש", "אור ישיר", "2700K — לבן חם", "פינת אוכל"),
    ("CORVELLA Halo pendant black", "pendant", COR, "שחור", "קרקע / מטבח / אי מטבח",
     "גוף תלוי", "מינימליסטי", "שחור מאט", "אור ישיר", "2700K — לבן חם", "מטבח"),
    ("CORVELLA Ring 600", "ring", COR, "פליז מוברש", "קרקע / חלל ראשי / אווירה",
     "גוף תלוי", "מודרני", "פליז מוברש", "אור עקיף / מוחזר", "Warm Dim — עמעום חם", "סלון"),
    ("TOBEK Bowl sconce", "sconce", TOB, "לבן", "ראשונה / חדרי שינה / קירי",
     "צמוד קיר", "אורגני", "זכוכית חלבית", "אור עקיף / מוחזר", "2700K — לבן חם", "חדר שינה"),
    ("TOBEK Duo up-down", "updown", TOB, "אפור גרפיט", "קרקע / כניסה / קירי",
     "צמוד קיר", "מינימליסטי", "אלומיניום", "אור ישיר", "3000K — לבן נעים", "כניסה"),
    ("TOBEK Line 40 profile", "profile", TOB, "אלומיניום", "קרקע / מטבח / תחתית נגרות",
     "פס לד לנגרות / ארונות", "מינימליסטי", "אלומיניום", "אור ישיר", "3000K — לבן נעים", "מטבח"),
    ("TOBEK Line 40 floor", "floorprofile", TOB, "אלומיניום", "קרקע / מסדרון / פרופילים",
     "", "מינימליסטי", "אלומיניום", "אור עקיף / מוחזר", "2700K — לבן חם", "מסדרון"),
    ("OSKARI LUX Arc floor lamp", "floorlamp", OSK, "שחור", "קרקע / סלון / עמידה סלון",
     "מנורת רצפה / שולחן", "מודרני", "שחור מאט", "אור ישיר", "2700K — לבן חם", "סלון"),
    ("OSKARI LUX Inground 60", "inground", OSK, "נירוסטה", "קרקע / פרגולה / הארת צמחייה",
     "שקוע רצפה מואר כלפי מעלה", "מינימליסטי", "אלומיניום", "ספוט צר", "3000K — לבן נעים", "מרפסת"),
    ("TOBEK Step 120", "step", TOB, "אפור כהה", "קרקע / כניסה / מאחז יד",
     "", "מינימליסטי", "אלומיניום", "הצפה רחבה", "3000K — לבן נעים", "חדר מדרגות"),
    ("TOBEK Graze 900", "grazer", TOB, "לבן", "קרקע / חלל ראשי / אפלייט",
     "", "מודרני", "לבן", "הצפה רחבה", "3000K — לבן נעים", "סלון"),
]

# Studio photos: fictional past projects (invented names).
SCENES = [
    ("CEDAR_FLAT_012", "downlights", "קרקע / סלון / שקועים",
     "שקוע בתקרה", "מינימליסטי", "לבן", "אור ישיר", "2700K — לבן חם", "סלון"),
    ("CEDAR_FLAT_027", "pendant_table", "קרקע / שולחן אוכל / תלוי פינת אוכל",
     "גוף תלוי", "מודרני", "פליז מוברש", "אור ישיר", "2700K — לבן חם", "פינת אוכל"),
    ("CEDAR_FLAT_031", "island", "קרקע / מטבח / אי מטבח",
     "", "מודרני", "", "אור ישיר", "3000K — לבן נעים", "מטבח"),
    ("HARBOR_LOFT_004", "cove", "קרקע / חלל ראשי / אווירה",
     "פס לינארי", "מינימליסטי", "", "אור עקיף / מוחזר", "2700K — לבן חם", "סלון"),
    ("HARBOR_LOFT_019", "corridor", "קרקע / משותפים / קירי",
     "צמוד קיר", "מינימליסטי", "", "אור עקיף / מוחזר", "3000K — לבן נעים", "מסדרון"),
    ("HARBOR_LOFT_022", "closet", "ראשונה / מאסטר / ארונות",
     "", "מינימליסטי", "עץ", "אור ישיר", "3000K — לבן נעים", "חדר שינה הורים"),
    ("OLIVE_HOUSE_008", "headboard", "ראשונה / מאסטר / נגרות",
     "פס לד לנגרות / ארונות", "אורגני", "עץ", "אור עקיף / מוחזר", "2700K — לבן חם", "חדר שינה הורים"),
    ("OLIVE_HOUSE_015", "mirror", "ראשונה / רחצה / קירי",
     "", "מינימליסטי", "", "אור עקיף / מוחזר", "3000K — לבן נעים", "חדר רחצה"),
    ("OLIVE_HOUSE_033", "uplights", "קרקע / פרגולה / הארת צמחייה",
     "שקוע רצפה מואר כלפי מעלה", "אורגני", "", "ספוט צר", "3000K — לבן נעים", "מרפסת"),
    ("OLIVE_HOUSE_041", "desk", "ראשונה / ספריה / תחתית נגרות",
     "", "מינימליסטי", "עץ", "אור ישיר", "3000K — לבן נעים", "חדר עבודה"),
]


def aid(name):
    return hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


def build():
    os.makedirs(LIB, exist_ok=True)
    assets, tags, cats = [], [], {}
    from PIL import Image

    def add(name, kind, brand, path, context, install, style, finish, beam, cct, room, used):
        a = aid(name)
        w, h = Image.open(path).size
        assets.append([a, name, kind, brand.lower().replace(" ", "-") if brand else "", w, h,
                       context, used, len(used.split("|")), "library/%s.png" % a])
        tags.append([a, install, style, finish, beam, cct, room, 1, STAMP, BY, ""])
        cat = context.split(" / ")[-1]
        cats.setdefault(cat, []).append((name, a, kind, brand.lower() if brand else ""))

    for i, (name, drawing, brand, colour, context, *rest) in enumerate(PRODUCTS):
        buf = io.BytesIO()          # draw_products writes a JPEG; the bank stores PNG
        draw_products.draw(drawing, colour, buf)
        path = os.path.join(LIB, aid(name) + ".png")
        Image.open(buf).save(path)
        add(name, "product", brand, path, context, *rest, used="1|%d" % (2 + i % 3))
    for name, drawing, context, *rest in SCENES:
        a = aid(name)
        src = glob.glob(os.path.join(HERE, "photos", drawing + "_*.jpg"))[0]
        path = os.path.join(LIB, a + ".png")
        Image.open(src).convert("RGB").save(path)
        add(name, "studio_photo", "", path, context, *rest, used=str(1 + len(name) % 3))

    write_csv(os.path.join(KN, "assets.csv"),
              ["asset_id", "name", "kind", "manufacturer", "width", "height", "context",
               "used_in_projects", "n_projects", "file"], assets)
    write_csv(os.path.join(KN, "asset_tags.csv"),
              ["asset_id", "install", "style", "finish", "beam", "cct", "room", "reviewed",
               "reviewed_at", "reviewed_by", "note"], tags)
    write_csv(os.path.join(KN, "category_assets.csv"),
              ["category", "asset_name", "asset_id", "kind", "manufacturer", "times_used"],
              [[c, n, a, k, b, 1] for c, rows in sorted(cats.items()) for n, a, k, b in rows])
    # Logs the tool writes as people work. Empty in a fresh install.
    write_csv(os.path.join(KN, "asset_hidden.csv"), ["asset_id", "hidden_by", "hidden_at", "reason"], [])
    write_csv(os.path.join(KN, "asset_crops.csv"), ["asset_id", "x", "y", "w", "h", "fixed_by", "fixed_at"], [])
    with open(os.path.join(KN, "asset_choices.csv"), "w", newline="", encoding="utf-8") as fh:
        fh.write("category,asset_id,tags,chosen_at,source\n")
    return len(assets)


if __name__ == "__main__":
    print("photos:", build())
