"""אימות שהמצגת שנוצרת תואמת את מפרט הייחוס — נמדד, לא בעין.

הערכים הנדרשים חולצו מ-5 מצגות הייחוס (295 שקופיות).
"""
import glob
import json
import os
import re
import struct
import zipfile
from xml.etree import ElementTree as ET

import pytest
import yaml

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
OUT = os.path.join(os.path.dirname(__file__), "..", "out")
KN = os.path.join(os.path.dirname(__file__), "..", "knowledge")

PNG_MAGIC = bytes([137, 80, 78, 71, 13, 10, 26, 10])


def _style_of(pptx_path):
    """סגנון המצגת לפי המניפסט. בלי שדה — שחור, כמו כל מה שלפני D-050."""
    man = os.path.splitext(pptx_path)[0] + ".manifest.json"
    try:
        with open(man, encoding="utf-8") as fh:
            return json.load(fh).get("deck_style") or "black"
    except Exception:
        return "black"


def _was_arranged_by_hand(pptx_path):
    """האם מישהו סידר את המצגת הזו ידנית (D-020).

    המניפסט רושם `manual_layout` לכל שקופית שהעובד הזיז בה משהו.
    מניפסט ישן בלי השדה = פריסה אוטומטית, וזה נכון.
    """
    man = os.path.splitext(pptx_path)[0] + ".manifest.json"
    if not os.path.exists(man):
        return False
    try:
        with open(man, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return False
    # `make_deck.py` כותב מניפסט בצורה אחרת — שם "areas" ו-"slides"
    # הם ספירות ולא רשימות. מבנה שאינו מוכר פירושו שלא נרשמה פריסה
    # ידנית, ולכן — אוטומטי.
    for a in data.get("areas") or []:
        if not isinstance(a, dict):
            continue
        rows = a.get("slides")
        if not isinstance(rows, list):
            continue
        for sl in rows:
            if isinstance(sl, dict) and sl.get("manual_layout"):
                return True
    return False


def newest_pptx():
    """המצגת האחרונה שנוצרה **בפריסה האוטומטית**.

    הבדיקות במודול הזה מאמתות את הפריסה שנמדדה ב-5 מצגות הייחוס:
    התוכנית ב-4%, הכותרת ב-96.7%. מאז D-020 העובד רשאי לגרור כל
    רכיב לאן שהוא רוצה, ומצגת מסודרת ידנית **אמורה** לסטות מהמפרט
    הזה — נפילה עליה אינה רגרסיה אלא הצלחה של תכונה.

    לכן מדלגים על מצגות שסודרו ביד, במקום לרכך את הסף ולאבד את
    היכולת לתפוס סטייה אמיתית בפריסה האוטומטית.
    """
    files = (glob.glob(os.path.join(OUT, "deck_*.pptx")) +
             glob.glob(os.path.join(OUT, "presentation_*.pptx")))
    # מצגת בסגנון אחר (האפור, D-050) אינה נמדדת מול המצגות השחורות
    auto = [f for f in files if not _was_arranged_by_hand(f) and _style_of(f) == "black"]
    if not auto:
        pytest.skip("אין מצגת בפריסה אוטומטית — הרץ src/make_deck.py"
                    if files else
                    "לא נוצרה מצגת עדיין — הרץ src/make_deck.py")
    return max(auto, key=os.path.getmtime)


DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo_apartment.dxf")


def _build_demo_deck(outdir):
    """No deck in out/ (a fresh clone): build one from the demo drawing with
    the CLI, in the automatic layout these tests measure."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    import make_deck
    spec = make_deck.init_spec(DEMO)
    spec_path = os.path.join(outdir, "spec.yaml")
    with open(spec_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(spec, fh, allow_unicode=True)
    return make_deck.build(spec_path, outdir)


@pytest.fixture(scope="module")
def deck(tmp_path_factory):
    try:
        return zipfile.ZipFile(newest_pptx())
    except pytest.skip.Exception:
        if not os.path.exists(DEMO):
            raise
        return zipfile.ZipFile(_build_demo_deck(str(tmp_path_factory.mktemp("deck"))))


@pytest.fixture(scope="module")
def layout():
    with open(os.path.join(KN, "layout.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def box(el):
    for x in el.iter("{%s}xfrm" % NS["a"]):
        o, e = x.find("a:off", NS), x.find("a:ext", NS)
        if o is not None and e is not None and e.get("cx"):
            return (int(o.get("x")), int(o.get("y")),
                    int(e.get("cx")), int(e.get("cy")))
    return None


def slides(deck):
    names = [n for n in deck.namelist()
             if re.match(r"ppt/slides/slide\d+\.xml$", n)]
    names.sort(key=lambda s: int(re.search(r"(\d+)", s).group(1)))
    return [ET.fromstring(deck.read(n)) for n in names]


def pics(slide):
    tree = slide.find(".//p:cSld/p:spTree", NS)
    return [e for e in tree if e.tag.endswith("}pic")]


def shapes(slide):
    tree = slide.find(".//p:cSld/p:spTree", NS)
    return [e for e in tree if e.tag.endswith("}sp")]


# ─── מפרט שנמדד בייחוס ────────────────────────────────────────────

def test_slide_size_matches_reference(deck, layout):
    pres = ET.fromstring(deck.read("ppt/presentation.xml"))
    sz = pres.find("p:sldSz", NS)
    assert [int(sz.get("cx")), int(sz.get("cy"))] == layout["canvas"]["slide_emu"]


def test_background_is_black_on_every_slide(deck):
    for s in slides(deck):
        bg = s.find(".//p:bg", NS)
        assert bg is not None, "לשקופית אין רקע מוגדר"
        clr = bg.find(".//a:schemeClr", NS)
        assert clr is not None and clr.get("val") == "tx1", \
            "רקע השקופית חייב להיות tx1 (שחור), כמו בכל 295 שקופיות הייחוס"


def test_title_right_edge_matches_reference(deck, layout):
    W = layout["canvas"]["slide_emu"][0]
    want = layout["title"]["right_edge_pct"]
    for s in slides(deck):
        texts = [e for e in shapes(s)
                 if "".join(t.text or "" for t in e.findall(".//a:t", NS)).strip()]
        assert texts, "אין כותרת בשקופית"
        b = box(texts[0])
        # כותרת באנגלית יושבת משמאל (גיא והסטודיו, 18.10) — הקצה הימני
        # נמדד רק על עברית. הצד השמאלי נבדק ב-test_preview.
        text = "".join(t.text or "" for t in texts[0].findall(".//a:t", NS))
        if not re.search("[֐-׿]", text):
            continue
        right_pct = (b[0] + b[2]) / W * 100
        assert abs(right_pct - want) < 0.5, \
            "קצה ימני %.1f%%, בייחוס %s%%" % (right_pct, want)


def test_title_is_rtl_and_right_aligned(deck):
    for s in slides(deck):
        for pPr in s.iter("{%s}pPr" % NS["a"]):
            if pPr.get("algn") == "r":
                assert pPr.get("rtl") == "1", \
                    "טקסט מעורב עברית/אנגלית נשבר בלי rtl=1"
                return
            if pPr.get("algn") == "l":
                # כותרת אנגלית: משמאל, ובלי rtl — אחרת הפיסוק קופץ
                assert pPr.get("rtl") == "0", "כותרת אנגלית עם rtl=1 נשברת"
                return
    pytest.fail("לא נמצאה פסקת כותרת מיושרת")


def test_font_matches_studio(deck, layout):
    want = layout["title"]["font"]
    fonts = set()
    for s in slides(deck):
        for latin in s.iter("{%s}latin" % NS["a"]):
            fonts.add(latin.get("typeface"))
    assert want in fonts, "גופן %s לא נמצא; נמצאו %s" % (want, fonts)


# ─── סטייה מכוונת ממבנה הייחוס ────────────────────────────────────

def test_components_are_separate_objects_not_one_baked_image(deck, layout):
    """בייחוס השקופית היא תמונה מרוכבת אחת, מפני שפוטושופ מחייב זאת.

    כאן התוכנית וכל תצלום הם אובייקטים נפרדים, כדי שהמתכנן יוכל
    להזיז ולשנות גודל של כל אחד בנפרד. אפשרי מפני ששני הרקעים
    שחורים טהורים וההרכבה זהה פיקסלית.
    """
    W, H = layout["canvas"]["slide_emu"]
    for s in slides(deck):
        for p in pics(s):
            b = box(p)
            full_bleed = (b[0] == 0 and b[1] == 0 and
                          b[2] >= W * 0.97 and b[3] >= H * 0.97)
            assert not full_bleed, \
                "נמצאה תמונה מלאת-פריים — הרכיבים אמורים להיות נפרדים"


def test_plan_starts_at_the_measured_left_margin(deck, layout):
    W = layout["canvas"]["slide_emu"][0]
    px_w = layout["canvas"]["width_px"]
    want_pct = layout["plan_panel"]["x"] / px_w * 100
    for s in slides(deck):
        p = pics(s)
        if not p:
            continue
        b = box(p[0])
        assert abs(b[0] / W * 100 - want_pct) < 0.5, \
            "התוכנית לא מתחילה בשוליים שנמדדו (%.1f%%)" % want_pct
        return


def test_header_rule_is_an_editable_shape(deck, layout):
    """קו הכותרת חייב להיות ניתן לעריכה, לא צרוב בתמונה."""
    hr = layout["header_rule"]
    W = layout["canvas"]["slide_emu"][0]
    H = layout["canvas"]["slide_emu"][1]
    px_w = layout["canvas"]["width_px"]
    px_h = layout["canvas"]["height_px"]
    want_x = hr["x"] / px_w * 100
    for s in slides(deck):
        found = []
        for e in shapes(s):
            b = box(e)
            if not b:
                continue
            if (abs(b[0] / W * 100 - want_x) < 0.5 and
                    b[3] / H * px_h < hr["height"] * 3):
                found.append(b)
        assert found, "קו הכותרת לא נמצא כצורה נפרדת"
        return


def test_plan_raster_matches_its_placement_box(deck, layout):
    """הפאנל מרונדר בדיוק בגודל שבו הוא מונח, בלי דגימה מחדש.

    בעבר נבדק כאן שהתמונה היא 2000x1125, כי השקופית הייתה תמונה
    מרוכבת אחת. עכשיו הרכיבים נפרדים, והאינווריאנט המשמעותי הוא
    שהרסטר תואם את תיבת ההנחה 1:1 — אחרת קווי השיער מטשטשים.
    """
    W, H = layout["canvas"]["slide_emu"]
    px_w = layout["canvas"]["width_px"]
    px_h = layout["canvas"]["height_px"]

    sizes = []
    for m in deck.namelist():
        if not m.startswith("ppt/media/"):
            continue
        d = deck.read(m)
        if d[:8] == PNG_MAGIC:
            sizes.append(struct.unpack(">II", d[16:24]))
    assert sizes, "אין תמונות PNG במצגת"

    for s in slides(deck):
        p = pics(s)
        if not p:
            continue
        b = box(p[0])
        bw = b[2] / W * px_w
        bh = b[3] / H * px_h
        assert any(abs(w - bw) < 3 and abs(h - bh) < 3 for w, h in sizes), \
            "אין רסטר שתואם את תיבת התוכנית %dx%d; נמצאו %s" % (bw, bh, sizes[:4])
        return
