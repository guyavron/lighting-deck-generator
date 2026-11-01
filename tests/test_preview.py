"""התצוגה המקדימה חייבת לשקר פחות מהמצגת, לא יותר.

היא נבנתה כדי שהעובד יראה מה ייצא לפני שהוא מייצא. ברגע שהיא
מציגה פריסה משלה — היא גרועה מכלום, כי היא מייצרת ביטחון שגוי.

הבדיקות כאן נועלות את מה שנשבר בפועל: כפיית "רחבה" מתחה את התוכנית
במקום לרנדר אותה מחדש, הייצוא חישב תיבת כותרת בנוסחה משלו, והמטמון
של פאנל התוכנית הוא מה שהופך שינוי בשקופית מ-6 שניות ל-0.5.

ומאז D-020 גם: **פריסה שאדם הזיז חייבת להגיע לייצוא.** סידור
שנשאר בתצוגה בלבד גרוע מאין סידור, כי העובד כבר האמין לו.
"""
import os
import sys

import pytest
from PIL import Image

import preview as PV
import slide as SL

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope="module")
def layout():
    return SL.load_layout()


def test_canvas_is_the_measured_size(layout):
    """2000x1125 — כל 228 התמונות המרוכבות בייחוס, וגם קנבס ה-PSD."""
    geom = SL.resolve(SL.plan_panel_box(489 / 738.0, layout), layout, [])
    img = PV.render(Image.new("RGB", (489, 738)), "בדיקה", [], layout, geom)
    assert img.size == (layout["canvas"]["width_px"],
                        layout["canvas"]["height_px"])


def test_plan_lands_exactly_in_the_box(layout):
    """התיבה מגיעה מבחוץ, ולכן היא זו שנקבעת — לא יחס התמונה."""
    box = SL.plan_panel_box(1.6, layout)
    geom = SL.resolve(box, layout, [])
    plan = Image.new("RGB", (box[2], box[3]), (255, 0, 0))
    img = PV.render(plan, "", [], layout, geom)
    assert img.getpixel((box[0], box[1])) == (255, 0, 0)
    assert img.getpixel((box[0] + box[2] - 1, box[1] + box[3] - 1)) == (255, 0, 0)
    assert img.getpixel((box[0] - 2, box[1] + 4)) == (0, 0, 0)


def test_forcing_wide_changes_the_box_not_only_the_stretch(layout):
    """הכפייה חייבת להגיע לפני הרינדור.

    קודם הפאנל רונדר צר ונמתח לתיבה רחבה, וכפיית "רחבה" עיוותה את
    התוכנית בתצוגה בלבד — בדיוק במקום שבו העובד מבקש עזרה.
    """
    sys.path.insert(0, os.path.join(HERE, "..", "src"))
    import server as SRV

    narrow = SL.plan_panel_box(SRV._forced_aspect(0.66, 0, layout), layout)
    wide = SL.plan_panel_box(SRV._forced_aspect(0.66, 1, layout), layout)
    auto = SL.plan_panel_box(SRV._forced_aspect(0.66, -1, layout), layout)
    assert wide[2] > narrow[2]
    assert auto == narrow          # 0.66 צר מטבעו


def test_panel_cache_returns_the_same_image_object():
    """המטמון הוא מה שהופך את התצוגה לשמישה.

    נמדד: רינדור 111 (2).dxf = 5.5 שניות, כי כל קריאה מריצה מחדש
    את ההקלטה כולה. הפאנל אינו תלוי בתצלום, בכותרת או בפריסה.
    """
    import server as SRV

    calls = []

    class FakePlayer:
        pass

    def fake_render(player, size, **kw):
        calls.append(size)
        return (Image.new("RGB", size), None, 1.0)

    real = SRV.PR.render
    SRV.PR.render = fake_render
    try:
        look = {"architecture_line": "#e0e0e0", "wall_fill": "#c0c0c0"}
        args = ("d.dxf", FakePlayer(), {"A", "B"}, (0, 0, 10, 10), (40, 30), look)
        a = SRV._plan_panel(*args)
        b = SRV._plan_panel(*args)
        assert a is b and len(calls) == 1
        # שכבה אחרת = תמונה אחרת, ולא פגיעה במטמון
        SRV._plan_panel("d.dxf", args[1], {"A"}, (0, 0, 10, 10), (40, 30), look)
        assert len(calls) == 2
    finally:
        SRV.PR.render = real


# ─── פריסה ידנית · D-020 ─────────────────────────────────────────


def test_a_moved_box_wins_over_the_measured_layout(layout):
    """מה שאדם הזיז גובר. זו כל המשמעות של "לסדר כמו שאני רוצה"."""
    auto = SL.plan_panel_box(0.66, layout)
    g = SL.resolve(auto, layout, [(1600, 900)],
                   override={"plan": [300, 210, 600, 908],
                             "photos": [[1400, 300, 420, 236]]})
    assert g["plan"] == (300, 210, 600, 908)
    assert g["photos"][0] == (1400, 300, 420, 236)
    # והאוטומטית נשמרת, כדי שאפשר יהיה לחזור אליה
    assert g["auto_plan"] == auto


def test_a_box_in_the_wrong_proportion_is_not_stretched_into(layout):
    """גיא, 12.10: אחרי סיבוב התוכנית "נמרחה", ושתיים מתשע שקופיות
    במצגת יצאו מעוותות — רסטר 1212x330 בתיבה ביחס 0.27.

    תיבה שנשמרה ביחס אחר מזה של הרסטר מתוקנת: אותו מרכז, אותו שטח,
    היחס של הרסטר. ותיבה כזו לעולם אינה יוצאת מהשקופית.
    """
    auto = SL.plan_panel_box(1.9, layout)               # 1212x637
    want = auto[2] / auto[3]
    g = SL.resolve(auto, layout, [], override={"plan": [100, 50, 330, 1212]})
    x, y, w, h = g["plan"]
    assert abs((w / h) / want - 1) < 0.01
    c = layout["canvas"]
    assert x >= 0 and y >= 0
    assert x + w <= c["width_px"] and y + h <= c["height_px"]
    # תיבה ביחס הנכון אינה זזה בפיקסל
    ok = [200, 300, 606, 318]
    assert SL.resolve(auto, layout, [], override={"plan": ok})["plan"] == tuple(ok)


def test_untouched_elements_still_flow(layout):
    """דריסה של רכיב אחד אינה מקפיאה את השאר.

    מי שמצר את התוכנית מצפה שהתצלומים יתרחבו לתוך המקום שהתפנה.
    """
    auto = SL.plan_panel_box(1.9, layout)          # תוכנית רחבה
    wide_photo = SL.resolve(auto, layout, [(1000, 1000)])["photos"][0]
    narrowed = SL.resolve(auto, layout, [(1000, 1000)],
                          override={"plan": [81, 167, 300, 220]})["photos"][0]
    assert narrowed[2] > wide_photo[2]


def test_a_plan_dragged_out_of_the_way_does_not_delete_the_photos(layout):
    """תוכנית שנגררה ימינה אינה משאירה מקום לתצלומים.

    בלי הנפילה חזרה לפריסה האוטומטית הם היו נעלמים מהשקופית בלי
    שום הסבר, והעובד היה מגלה את זה רק ב-PowerPoint.
    """
    auto = SL.plan_panel_box(0.66, layout)
    g = SL.resolve(auto, layout, [(1600, 900)],
                   override={"plan": [1700, 167, 220, 330]})
    assert g["photos"][0] is not None


def test_the_title_box_is_computed_once(layout):
    """נוסחה אחת לכותרת, לא אחת לייצוא ואחת לתצוגה.

    קודם הייצוא בנה תיבה והתצוגה ציירה טקסט ב-`hr.y - size*1.35`.
    שתי נוסחאות לאותו דבר נפרדות ביום שמישהו נוגע באחת מהן.
    """
    box, sizes = SL.title_layout(1, layout)
    hr = layout["header_rule"]
    assert box[1] + box[3] <= hr["y"] + 1        # לא חוצה את הקו
    right = box[0] + box[2]
    assert abs(right / layout["canvas"]["width_px"] * 100 - 96.7) < 0.1
    assert sizes == [14.0]

    big, sizes2 = SL.title_layout(1, layout, {"pt": 24})
    assert sizes2 == [24.0] and big[3] > box[3]


def test_export_places_what_the_preview_shows(tmp_path, layout):
    """אותה גיאומטריה, שני מוצאים. זו הבדיקה שכל השאר משרתות.

    כאן זה נבדק על ה-XML של ה-PPTX ולא על כוונה: המיקומים שנקראים
    חזרה מהקובץ הם המיקומים שהתצוגה קיבלה.
    """
    from pptx import Presentation

    photo = tmp_path / "p.png"
    Image.new("RGB", (800, 600), (9, 9, 9)).save(photo)
    plan = tmp_path / "plan.png"
    Image.new("RGB", (489, 740), (7, 7, 7)).save(plan)

    auto = SL.plan_panel_box(0.66, layout)
    override = {"plan": [140, 160, 500, 757],
                "photos": [[1200, 300, 480, 360]],
                "title": {"x": 900, "y": 30, "w": 1000, "pt": 20}}
    geom = SL.resolve(auto, layout, [(800, 600)], override=override)

    out = tmp_path / "d.pptx"
    SL.build_pptx(str(out), [{"plan": str(plan), "geom": geom,
                              "title_lines": ["חדר | שקועים"],
                              "photos": [str(photo)]}], layout)

    prs = Presentation(str(out))
    c = layout["canvas"]
    cx = prs.slide_width / c["width_px"]
    cy = prs.slide_height / c["height_px"]
    pics = [sh for sh in prs.slides[0].shapes if sh.shape_type == 13]
    got = sorted([(round(p.left / cx), round(p.top / cy),
                   round(p.width / cx), round(p.height / cy)) for p in pics])
    assert got == sorted([tuple(override["plan"]),
                          tuple(override["photos"][0])])

    # 17 = תיבת טקסט. קו הכותרת הוא מלבן, ולמלבן ב-PPTX יש גם הוא
    # מסגרת טקסט — סינון לפי has_text_frame היה תופס אותו ראשון.
    tb = [sh for sh in prs.slides[0].shapes if sh.shape_type == 17][0]
    assert (round(tb.left / cx), round(tb.top / cy)) == (900, 30)
    assert tb.text_frame.paragraphs[0].runs[0].font.size.pt == 20


# ─── צד הכותרת והפס מתחת לה · D-046 ─────────────────────────────

def test_title_side_follows_its_language():
    assert SL.title_is_rtl("סלון | שקועים")
    assert SL.title_is_rtl("Kitchen | TACCIA | אופציה ב")   # עברית = ימין
    assert not SL.title_is_rtl("Living room | Recessed")
    assert SL.title_is_rtl("")                              # בלי אותיות: כמו קודם


def test_english_title_starts_at_the_rule_margin(layout):
    """במצגת ייחוס א, שכולה אנגלית, הכותרות מתחילות בשוליים השמאליים."""
    auto = SL.plan_panel_box(0.66, layout)
    heb = SL.resolve(auto, layout, [], title_rtl=True)
    eng = SL.resolve(auto, layout, [], title_rtl=False)
    assert eng["title"]["box"][0] == layout["header_rule"]["x"]
    assert heb["title"]["box"][0] > eng["title"]["box"][0]
    assert (eng["title"]["rtl"], heb["title"]["rtl"]) == (False, True)


def test_a_moved_title_stays_where_it_was_put(layout):
    auto = SL.plan_panel_box(0.66, layout)
    g = SL.resolve(auto, layout, [], override={"title": {"x": 700, "y": 30}},
                   title_rtl=False)
    assert g["title"]["box"][:2] == (700, 30)


def test_english_title_exports_left_aligned_and_rule_can_be_off(tmp_path, layout):
    from pptx import Presentation
    plan = tmp_path / "plan.png"
    Image.new("RGB", (489, 740), (7, 7, 7)).save(plan)
    auto = SL.plan_panel_box(0.66, layout)
    on = SL.resolve(auto, layout, [], title_rtl=False)
    off = SL.resolve(auto, layout, [], title_rtl=False, rule=False)
    assert on["rule"] and off["rule"] is None
    out = tmp_path / "d.pptx"
    SL.build_pptx(str(out), [
        {"plan": str(plan), "geom": on, "title_lines": ["Kitchen | Recessed"], "photos": []},
        {"plan": str(plan), "geom": off, "title_lines": ["Kitchen | Recessed"], "photos": []},
    ], layout)
    prs = Presentation(str(out))
    for s, want_rules in zip(prs.slides, (1, 0)):
        rules = [sh for sh in s.shapes if sh.shape_type == 1]
        assert len(rules) == want_rules
        tb = [sh for sh in s.shapes if sh.shape_type == 17][0]
        pPr = tb.text_frame.paragraphs[0]._p.pPr
        assert (pPr.get("algn"), pPr.get("rtl")) == ("l", "0")


# ─── זוהר לכל שקופית · D-051 ─────────────────────────────────────

def test_slide_glow_choice_only_from_the_measured_list():
    import glow as G
    base = G.preset_for("deck_a")
    assert G.apply_slide_choice(base, {}) == base               # בלי בחירה — כמו קודם
    got = G.apply_slide_choice(base, {"color": "#F9F2D1", "size": "large", "power": "soft"})
    assert got["color"] == "#F9F2D1"
    assert got["size"] == base["size"] * 1.5
    assert got["opacity"] == base["opacity"] * 0.6
    # צבע שלא נמדד ודרגה שלא קיימת — מתעלמים, לא ממציאים
    odd = G.apply_slide_choice(base, {"color": "#FF0000", "size": "huge"})
    assert odd["color"] == base["color"] and odd["size"] == base["size"]


def test_slide_glow_power_on_grey_scales_gain():
    import glow as G
    grey = dict(G.preset_for("deck_a"), **SL.load_layout("grey")["glow"])
    got = G.apply_slide_choice(grey, {"power": "strong"})
    assert got["gain"] == grey["gain"] * 1.6 and got["opacity"] == grey["opacity"]


# ─── הסגנון האפור · D-050 ────────────────────────────────────────

def test_grey_overrides_only_what_it_changes(layout):
    g = SL.load_layout("grey")
    assert g["canvas"]["background"] == "#E1E1E1"
    assert g["plan_panel"]["x"] == layout["plan_panel"]["x"]     # לא נגע — נשאר
    assert g["plan_panel"]["y"] == 208
    assert SL.load_layout("black") == layout                    # שחור = הבסיס כמו שהוא
    assert "glow" not in layout and "photo_card" not in layout


def test_grey_glow_matches_deck_f():
    """נמדד במצגת ייחוס ו שקופית 2, גוף מבודד: ערוץ R מעל רקע 225."""
    import glow as G
    G.SIZE_TO_SIGMA = 0.39
    pre = SL.load_layout("grey")["glow"]
    base = Image.new("RGB", (300, 300), (225, 225, 225))
    out = G.render_glow((300, 300), [(139, 150), (161, 150)], pre, base=base, stack=2)
    want = {4: (241, 217), 22: (238, 219), 46: (230, 223), 70: (226, 225)}
    for r, (R, B) in want.items():
        got = out.getpixel((150, 150 - r))
        assert abs(got[0] - R) <= 2 and abs(got[2] - B) <= 2, (r, got)
    assert out.getpixel((139, 150)) == (221, 198, 87)          # הנקודה הזהובה


def test_grey_export_background_title_and_product_card(tmp_path):
    from pptx import Presentation
    g = SL.load_layout("grey")
    photo = tmp_path / "p.png"
    Image.new("RGB", (800, 600), (250, 250, 250)).save(photo)
    plan = tmp_path / "plan.png"
    Image.new("RGB", (489, 740), (225, 225, 225)).save(plan)
    geom = SL.resolve(SL.plan_panel_box(0.66, g), g, [(800, 600)], title_rtl=False)
    out = tmp_path / "d.pptx"
    SL.build_pptx(str(out), [{"plan": str(plan), "geom": geom, "title_lines": ["Kitchen"],
                              "photos": [str(photo)], "cards": [True]}], g)
    xml = open(out, "rb").read()
    prs = Presentation(str(out))
    s = prs.slides[0]
    bg = s._element.find(".//{http://schemas.openxmlformats.org/presentationml/2006/main}bg")
    assert b'srgbClr val="E1E1E1"' in __import__("lxml.etree", fromlist=["x"]).tostring(bg)
    rects = [sh for sh in s.shapes if sh.shape_type == 1]
    cols = sorted(str(r.fill.fore_color.rgb) for r in rects)
    assert cols == ["7F7F7F", "CCCCCC"]                       # הפס והריבוע
    tb = [sh for sh in s.shapes if sh.shape_type == 17][0]
    assert str(tb.text_frame.paragraphs[0].runs[0].font.color.rgb) == "7F7F7F"


def test_hebrew_title_has_hebrew_font_and_language(tmp_path, layout):
    """נתפס בפתיחה ב-PowerPoint: בלי <a:cs> האותיות העבריות נכתבו בגופן
    אחר, ובלי lang המספר קפץ מעבר ל-"|"."""
    from pptx import Presentation
    geom = SL.resolve(SL.plan_panel_box(0.66, layout), layout, [])
    out = tmp_path / "d.pptx"
    SL.build_pptx(str(out), [{"plan": None, "geom": geom, "title_lines": ["אזור 1 | שקועים"],
                              "photos": []},
                             {"plan": None, "geom": SL.resolve(SL.plan_panel_box(0.66, layout),
                                                               layout, [], title_rtl=False),
                              "title_lines": ["Kitchen | Recessed"], "photos": []}], layout)
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    prs = Presentation(str(out))
    for s, lang in zip(prs.slides, ("he-IL", "en-US")):
        tb = [sh for sh in s.shapes if sh.shape_type == 17][0]
        rPr = tb.text_frame.paragraphs[0].runs[0]._r.rPr
        assert rPr.get("lang") == lang
        assert rPr.find(A + "cs").get("typeface") == layout["title"]["font"]
        assert rPr.find(A + "latin").get("typeface") == layout["title"]["font"]


def test_grey_glow_on_a_long_strip_never_passes_the_measured_peak():
    """פס לינארי הציף חדר שלם בשמנת אטום לפני התקרה (הדמיית עובד)."""
    import glow as G
    G.SIZE_TO_SIGMA = 0.39
    pre = SL.load_layout("grey")["glow"]
    base = Image.new("RGB", (400, 200), (225, 225, 225))
    out = G.render_glow((400, 200), [("line", [(40, 100), (360, 100)])], pre,
                        base=base, stack=2)
    # 25 פיקסלים מהפס — הזוהר, לא הנקודה. שיא מצגת ייחוס ו: R 241 (alpha 0.6)
    r = out.getpixel((200, 75))[0]
    assert r <= 241, r


def test_black_export_has_no_card_even_when_asked(tmp_path, layout):
    from pptx import Presentation
    photo = tmp_path / "p.png"
    Image.new("RGB", (800, 600), (250, 250, 250)).save(photo)
    geom = SL.resolve(SL.plan_panel_box(0.66, layout), layout, [(800, 600)])
    out = tmp_path / "d.pptx"
    SL.build_pptx(str(out), [{"plan": None, "geom": geom, "title_lines": ["חדר"],
                              "photos": [str(photo)], "cards": [True]}], layout)
    s = Presentation(str(out)).slides[0]
    assert len([sh for sh in s.shapes if sh.shape_type == 1]) == 1   # הפס בלבד


# ─── נעילת התוכנית לאזור · D-047 ────────────────────────────────

def _lock_area(lock):
    import server as SRV
    return SRV.AreaSpec(name="בדיקה", x0=0, y0=0, x1=10, y1=10, plan_lock=lock)


def test_a_locked_slide_takes_the_areas_plan_not_its_own():
    import server as SRV
    a = _lock_area({"plan": [100, 200, 300, 400], "rot": 90, "wide": 1})
    sl = SRV.SlideSpec(geom={"plan": [5, 5, 50, 50], "rot": 180,
                             "title": {"x": 9}}, wide=0)
    ov, wide, align, locked = SRV._plan_layout(a, sl, 0)
    assert locked and wide == 1 and align == "left"
    assert ov["plan"] == [100, 200, 300, 400] and ov["rot"] == 90
    assert ov["title"] == {"x": 9}          # הכותרת נשארת של השקופית


def test_released_opening_and_photos_only_slides_keep_their_own():
    import server as SRV
    a = _lock_area({"plan": [100, 200, 300, 400]})
    for sl in (SRV.SlideSpec(geom={"plan": [5, 5, 50, 50]}, plan_free=True),
               SRV.SlideSpec(geom={"plan": [5, 5, 50, 50]}, mask=True),
               SRV.SlideSpec(geom={"plan": [5, 5, 50, 50]}, photos_only=True)):
        ov, _, _, locked = SRV._plan_layout(a, sl, -1)
        assert not locked and ov["plan"] == [5, 5, 50, 50]


def test_an_area_without_a_lock_behaves_as_before():
    """פרויקט שנשמר לפני D-047 ועוד לא נפתח בממשק החדש."""
    import server as SRV
    sl = SRV.SlideSpec(geom={"plan": [5, 5, 50, 50]}, wide=1)
    ov, wide, _, locked = SRV._plan_layout(_lock_area({}), sl, 1)
    assert not locked and wide == 1 and ov["plan"] == [5, 5, 50, 50]


def test_centre_is_the_middle_of_the_left_part(layout):
    p = layout["plan_panel"]
    left = SL.plan_panel_box(0.5, layout)
    mid = SL.plan_panel_box(0.5, layout, align="center")
    assert left[:2] == (p["x"], p["y"])
    assert mid[2:] == left[2:]                       # אותו גודל
    assert abs((mid[0] + mid[2] / 2) - (p["x"] + p["max_width_narrow"] / 2)) <= 1
    assert abs((mid[1] + mid[3] / 2) - (p["y"] + p["height"] / 2)) <= 1


# ─── סיבוב התוכנית · D-020 ───────────────────────────────────────


class _Fx:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.code, self.layer = "SH", "light up"


class _Survey:
    def __init__(self, fixtures):
        self.fixtures = fixtures


def _fake_state():
    """אזור רחב: 1000 יחידות לרוחב, 200 לגובה. יחס ~5."""
    pts = [_Fx(x, y) for x in range(0, 1001, 25) for y in range(0, 201, 25)]
    return {"window": (0.0, 0.0, 1180.0, 760.0), "survey": _Survey(pts)}


def _area():
    import server as SRV
    return SRV.AreaSpec(name="בדיקה", x0=0, y0=0, x1=1180, y1=760)


def test_rotating_ninety_flips_which_panel_shape_is_chosen(layout):
    """סיבוב חייב להיכנס לפני בחירת התיבה, לא אחריה.

    אזור רחב מקבל פאנל רחב. אחרי סיבוב של 90 מעלות הוא **מוצג**
    כפורטרט, ולכן הוא צריך את העמודה הצרה — בדיוק כמו DECK B.
    אילו הסיבוב היה מוחל על התמונה בסוף, התוכנית הייתה מסתובבת
    לתוך תיבה רחבה ומאבדת את רוב גובהה.
    """
    import server as SRV
    s, a = _fake_state(), _area()

    _, box0, _, size0 = SRV._area_geometry(s, None, a, layout, rot=0)
    _, box90, _, size90 = SRV._area_geometry(s, None, a, layout, rot=90)

    assert box0[2] > box0[3]            # רחב מטבעו
    assert box90[3] > box90[2]          # ואחרי הסיבוב — פורטרט
    assert box90[2] < box0[2]
    # הרינדור נעשה בגודל המוחלף, והתמונה מסתובבת אליו בדיוק 1:1.
    # רסטר שאינו תואם את תיבת ההנחה מטשטש את קווי השיער.
    assert size90 == (box90[3], box90[2])
    assert size0 == (box0[2], box0[3])


def test_half_turn_keeps_the_shape(layout):
    """180 מעלות אינן משנות את היחס, ולכן גם לא את התיבה."""
    import server as SRV
    s, a = _fake_state(), _area()
    _, box0, _, size0 = SRV._area_geometry(s, None, a, layout, rot=0)
    _, box180, _, size180 = SRV._area_geometry(s, None, a, layout, rot=180)
    assert box180 == box0 and size180 == size0


def test_only_right_angles_are_accepted():
    """זווית שאינה כפולה של 90 הייתה מחייבת פינות שחורות וחישוב
    תיבה תוחמת. עד שיהיה צורך מוכח — היא נדחית לאפס בשקט."""
    import server as SRV
    assert SRV._rot_of({"rot": 90}) == 90
    assert SRV._rot_of({"rot": 270}) == 270
    assert SRV._rot_of({"rot": 360}) == 0
    assert SRV._rot_of({"rot": 45}) == 0
    assert SRV._rot_of({"rot": "לא מספר"}) == 0
    assert SRV._rot_of(None) == 0
