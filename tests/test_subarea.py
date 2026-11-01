"""סימון תת-אזור — המסכה הצהובה שנמדדה במצגת ייחוס א.

**הערך היחיד שאסור לו לזוז הוא הצבע מעל שחור.** הוא נמדד על
ארבע שקופיות בייחוס ויצא (72, 64, 26) בכולן. הפירוק לצבע ואטימות
הוא גזירה מתוכו, ולכן הבדיקה נועלת את התוצאה — לא את הפירוק.
"""
import os
import sys

import pytest
from PIL import Image

import subarea as SA

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

SQUARE = [(5, 5), (35, 5), (35, 35), (5, 35)]


def test_mask_over_black_is_exactly_what_was_measured():
    """(72, 64, 26) — נמדד במצגת ייחוס א 6, 44, 97, 105."""
    out = SA.render(Image.new("RGB", (40, 40), (0, 0, 0)), SQUARE)
    assert out.getpixel((20, 20)) == tuple(SA.spec()["over_black"])


def test_the_tint_shift_is_constant_whatever_is_under_it():
    """r-g=8 ו-r-b=46 בכל 150,904 הפיקסלים שנמדדו תחת המסכה.

    זה מה שמוכיח שהמיזוג הוא alpha רגיל ולא Multiply או Overlay —
    ולכן זו הבדיקה ששומרת על מודל המיזוג עצמו.
    """
    for under in ((0, 0, 0), (70, 70, 70), (140, 140, 140), (204, 204, 204)):
        out = SA.render(Image.new("RGB", (40, 40), under), SQUARE)
        r, g, b = out.getpixel((20, 20))
        assert (r - g, r - b) == (8, 46), under


def test_the_plan_stays_readable_under_the_mask():
    """מסכה שמסתירה את התוכנית מפספסת את מטרתה.

    קו התוכנית הוא #8C8C8C. תחת המסכה הוא חייב להישאר בהיר
    משמעותית מהרקע השחור שסביבו, אחרת הסימון בולע את השרטוט.
    """
    img = Image.new("RGB", (40, 40), (0, 0, 0))
    img.putpixel((20, 20), (140, 140, 140))
    out = SA.render(img, SQUARE)
    line = out.getpixel((20, 20))
    ground = out.getpixel((21, 21))
    assert line[1] - ground[1] > 80


def test_every_edge_comes_out_at_a_right_angle():
    """פוליגון אורתוגונלי, לא מצולע חופשי — זה מה שגיא ביקש."""
    ring = SA.close_ring([(0, 0), (10, 3), (12, 20), (2, 24)])
    assert len(ring) >= 4
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        assert x0 == x1 or y0 == y1, ((x0, y0), (x1, y1))


def test_closing_adds_at_most_one_corner():
    """סגירה בזווית ישרה, בלי להמציא צורה שהעובד לא צייר."""
    drawn = [(0, 0), (10, 0), (10, 10), (5, 10), (5, 20)]
    assert len(SA.close_ring(drawn)) == len(drawn) + 1
    already = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert SA.close_ring(already) == [(0.0, 0.0), (10.0, 0.0),
                                      (10.0, 10.0), (0.0, 10.0)]


def test_a_polygon_that_is_not_a_polygon_draws_nothing():
    """שתי נקודות אינן שטח. שקופית לא תקבל מסכה מקו."""
    base = Image.new("RGB", (40, 40), (0, 0, 0))
    assert SA.render(base, [(5, 5), (35, 5)]).getpixel((20, 5)) == (0, 0, 0)


def test_inside_and_outside():
    poly = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert SA.contains(poly, 5, 5)
    assert not SA.contains(poly, 15, 5)
    # ל-L יש פינה שנמצאת מחוץ לצורה אף שהיא בתוך תיבת החסימה
    ell = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]
    assert SA.contains(ell, 2, 8) and not SA.contains(ell, 8, 8)


def test_no_marking_means_everything_is_in():
    """שקופית בלי תת-אזור חייבת להאיר כרגיל.

    אילו פוליגון ריק היה מחזיר False, כל שקופית שלא סומנה הייתה
    יוצאת חשוכה — והתכונה החדשה הייתה שוברת את הישנות.
    """
    assert SA.contains([], 5, 5)
    assert SA.contains([(0, 0), (10, 0)], 500, 500)


def test_the_polygon_narrows_the_area_itself_not_just_the_glow():
    """**זו הנקודה שגיא תיקן.**

    בניתי את תת-האזור כקישוט של שקופית שרק מצמצם הארה. מצגת ייחוס א
    מראה אחרת: שקופית 97 מציגה את התוכנית המלאה עם המסכה, ו-98
    כבר **חתוכה** לגוש שסומן. תת-אזור הוא תחום עבודה — הוא משנה
    את המסגור, ולכן הצמצום חייב לקרות ב-`_area_geometry` ולא
    ב-`_lit_fixtures`.
    """
    import server as SRV
    import slide as SL

    layout = SL.load_layout()
    state = _wide_state()
    whole = SRV.AreaSpec(name="קומה", x0=0, y0=0, x1=1180, y1=760)
    half = SRV.AreaSpec(name="חלק", x0=0, y0=0, x1=1180, y1=760,
                        parent="קומה", parent_box=[0, 0, 1180, 760],
                        poly=[[0, 0], [400, 0], [400, 300], [0, 300]])

    all_in, _, fr_all, _ = SRV._area_geometry(state, None, whole, layout)
    few, _, fr_few, _ = SRV._area_geometry(state, None, half, layout)
    assert 0 < len(few) < len(all_in)
    # והמסגור נגזר מהם — זה מה שהופך את השקופית ל"חתוכה"
    assert (fr_few.window[2] - fr_few.window[0]) < (fr_all.window[2] - fr_all.window[0])


def test_the_opening_slide_shows_the_whole_parent():
    """שקופית הפתיחה מראה איפה תת-האזור יושב בתוך השלם.

    אילו היא הייתה מצטמצמת לפוליגון כמו שאר השקופיות, המסכה הייתה
    מכסה את כל התמונה ולא אומרת דבר.
    """
    import server as SRV
    import slide as SL

    layout = SL.load_layout()
    state = _wide_state()
    half = SRV.AreaSpec(name="חלק", x0=0, y0=0, x1=1180, y1=760,
                        parent="קומה", parent_box=[0, 0, 1180, 760],
                        poly=[[0, 0], [400, 0], [400, 300], [0, 300]])

    work, _, _, _ = SRV._area_geometry(state, None, half, layout)
    intro, _, _, _ = SRV._area_geometry(state, None, half, layout, mask=True)
    assert len(intro) > len(work)


def test_a_manual_pick_still_wins():
    """סדר העדיפויות של D-019 לא השתנה."""
    import server as SRV

    class F:
        def __init__(self, x, y):
            self.x, self.y, self.layer, self.code = x, y, "light up", "SH"

    a, b = F(2, 2), F(50, 50)
    state = {"survey": type("S", (), {"fixtures": [a, b]})()}
    assert SRV._lit_fixtures(state, SRV.SlideSpec(picks=[1]), [a]) == [b]


class _Fx:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.code, self.layer = "SH", "light up"


def _wide_state():
    pts = [_Fx(x, y) for x in range(0, 1001, 25) for y in range(0, 301, 25)]
    return {"window": (0.0, 0.0, 1180.0, 760.0),
            "survey": type("S", (), {"fixtures": pts})()}


# ─── חיתוך לצורה · D-025 ─────────────────────────────────────────


def test_the_working_slide_is_cut_to_the_shape_not_to_a_rectangle():
    """גיא: "הציג את תת האזור כריבוע למרות שבבירור גזרתי אותו לא כריבוע".

    מצגת ייחוס א 106 מראה את גוש החניה בלבד — כל המרתף שסביבו נעלם.
    מסגור לתיבת החוסמת בלבד מחזיר ריבוע, וזה מה שקרה.
    """
    img = Image.new("RGB", (60, 60), (140, 140, 140))
    ell = [(0, 0), (60, 0), (60, 20), (20, 20), (20, 60), (0, 60)]
    out = SA.clip(img, ell)
    assert out.getpixel((5, 5)) == (140, 140, 140)      # בתוך הצורה
    assert out.getpixel((50, 10)) == (140, 140, 140)    # בזרוע העליונה
    assert out.getpixel((50, 50)) == (0, 0, 0)          # בתיבה, מחוץ לצורה


def test_clipping_needs_a_real_polygon():
    """שתי נקודות אינן צורה, ולכן אינן חותכות דבר."""
    img = Image.new("RGB", (20, 20), (9, 9, 9))
    assert SA.clip(img, [(0, 0), (10, 10)]).getpixel((15, 15)) == (9, 9, 9)


def test_the_opening_slide_is_masked_and_the_working_slide_is_clipped():
    """שני מצבים שונים לאותו פוליגון, ואסור שיתחלפו.

    פתיחה: התוכנית המלאה עם מסכה צהובה מעליה.
    עבודה: רק הצורה, בלי מסכה.
    """
    img = Image.new("RGB", (60, 60), (140, 140, 140))
    square = [(0, 0), (30, 0), (30, 30), (0, 30)]
    masked = SA.render(img, square)
    clipped = SA.clip(img, square)
    # בתוך הפוליגון: המסכה צובעת, החיתוך משאיר כמו שהיה
    assert masked.getpixel((10, 10)) != (140, 140, 140)
    assert clipped.getpixel((10, 10)) == (140, 140, 140)
    # מחוץ לו: המסכה משאירה, החיתוך משחיר
    assert masked.getpixel((50, 50)) == (140, 140, 140)
    assert clipped.getpixel((50, 50)) == (0, 0, 0)


def test_the_sub_area_is_framed_by_its_shape_not_by_its_fixtures():
    """**הבאג שגיא דיווח עליו פעמיים.**

    המסגור נגזר מהגופים שבתת-האזור, ולכן החלון נפל **בתוך**
    הפוליגון — נמדד אצלו: פוליגון בגובה 1018 יחידות מול חלון בגובה
    425. במצב כזה החיתוך אינו חותך דבר, והשקופית מציגה פרוסה
    מלבנית שרירותית במקום הצורה שנגזרה.
    """
    import server as SRV
    import slide as SL

    layout = SL.load_layout()
    # גופים מרוכזים בפינה אחת בלבד של פוליגון רחב
    pts = [_Fx(x, y) for x in range(0, 201, 20) for y in range(0, 101, 20)]
    state = {"window": (0.0, 0.0, 1180.0, 760.0),
             "survey": type("S", (), {"fixtures": pts})()}
    wide_poly = [[0, 0], [1000, 0], [1000, 700], [0, 700]]
    area = SRV.AreaSpec(name="חלק", x0=0, y0=0, x1=1180, y1=760,
                        parent="קומה", parent_box=[0, 0, 1180, 760],
                        poly=wide_poly)

    _, _, fr, _ = SRV._area_geometry(state, None, area, layout)
    w = fr.window
    # החלון חייב להכיל את הפוליגון כולו, לא רק את הגופים
    assert w[0] <= 0 and w[2] >= 1000
    assert w[1] <= 0 and w[3] >= 700
