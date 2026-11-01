"""נעילת הכיול של מנוע ההארה מול פרופיל מדוד אמיתי.

אם בדיקה זו נשברת, ההארה שהמערכת מייצרת כבר אינה תואמת את מה
שהסטודיו מפיק בפוטושופ. זו הבדיקה החשובה ביותר בפרויקט.
"""
import glow as G

# נמדד ב-a deck-A composite סביב מוקד מבודד ב-(170,1004), ערוץ R, על שחור
REF = {4: 77, 6: 69, 8: 61, 10: 52, 12: 43, 14: 35,
       16: 27, 18: 21, 20: 15, 22: 10, 24: 6}


def render_profile():
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]
    preset = G.preset_for("deck_a")
    im = G.render_glow((140, 140), [(70, 70)], preset,
                       radius=cal["marker_radius_px"], stack=cal["stack"])
    px = im.load()
    return {d: px[70 + d, 70][0] for d in REF}


def test_profile_matches_reference():
    got = render_profile()
    for d, ref in REF.items():
        assert abs(got[d] - ref) <= 6, (
            f"r={d}px: התקבל {got[d]}, בייחוס {ref}. "
            f"מנוע ההארה סטה מהייחוס.")


def test_rms_error_stays_small():
    got = render_profile()
    rms = (sum((got[d] - REF[d]) ** 2 for d in REF) / len(REF)) ** 0.5
    assert rms < 4.0, f"RMS={rms:.2f} — הכיול התדרדר"


def test_presets_all_load():
    p = G.load_presets()
    for name in p["projects"]:
        pr = G.preset_for(name)
        assert pr["size"] > 0 and 0 < pr["opacity"] <= 100 and pr["color"].startswith("#")


def test_override_applies_for_planting():
    base = G.preset_for("deck_a")
    ov = G.preset_for("deck_a", "הארת צמחייה")
    assert ov["size"] > base["size"]
    assert ov["override"] == "outdoor_planting"


def test_glow_is_additive_between_neighbours():
    """גופים סמוכים חייבים למזג הילות, לא להסתיר זה את זה."""
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]
    preset = G.preset_for("deck_a")
    one = G.render_glow((160, 160), [(60, 80)], preset, stack=cal["stack"])
    two = G.render_glow((160, 160), [(60, 80), (100, 80)], preset, stack=cal["stack"])
    mid_one = one.load()[80, 80][0]
    mid_two = two.load()[80, 80][0]
    assert mid_two > mid_one, "הילות של גופים סמוכים לא התמזגו"


# ─── צורות הגוף · D-024 ──────────────────────────────────────────
#
# שלוש הצורות אינן שלושה אפקטים. אותו Outer Glow חל על כולן, ומה
# שמשתנה הוא רק מה שמצויר במסכת האלפא לפניו.


class _F:
    def __init__(self, kind="point", x=0.0, y=0.0, pts=(), radius=0.0):
        self.kind, self.x, self.y, self.pts, self.radius = kind, x, y, pts, radius


def _ident(x, y):
    return (x, y)


def test_a_linear_fixture_becomes_a_line_not_a_dot():
    """זו כל המשמעות של "ליניארי".

    פס באורך 1425 יחידות שמצויר כנקודה במרכזו הוא שקר על השרטוט.
    """
    sh = G.shape_for(_F("line", pts=((0, 0), (100, 0))), _ident, 1.0, 1.2)
    assert sh[0] == "line" and sh[1] == [(0, 0), (100, 0)]


def test_an_inflated_fixture_keeps_the_radius_the_planner_drew():
    """המעגל בשרטוט הוא גודל הגוף. הרדיוס עובר בקנה המידה של הפאנל."""
    sh = G.shape_for(_F("circle", x=10, y=20, radius=17.5), _ident, 0.4, 1.2)
    assert sh[0] == "disc" and sh[1:3] == (10, 20)
    assert abs(sh[3] - 7.0) < 1e-9

    # גוף זעיר לא נעלם — הוא לא קטן מסמן רגיל
    tiny = G.shape_for(_F("circle", radius=0.5), _ident, 0.01, 1.2)
    assert tiny[3] == 1.2


def test_a_point_fixture_is_untouched():
    """הגופים הנקודתיים הם 272 מתוך 354 ב-111 (2).dxf. הם לא זזו."""
    assert G.shape_for(_F("point", x=5, y=6), _ident, 1.0, 1.2) == (5, 6)


def test_a_line_glows_along_its_whole_run():
    """ההארה מלווה את הפס, ולא מתרכזת בקצה או במרכז."""
    cal = G.calibration()
    G.SIZE_TO_SIGMA = cal["size_to_sigma"]
    preset = G.preset_for("deck_a", None)
    img = G.render_glow((240, 80), [("line", [(20, 40), (220, 40)])], preset,
                        radius=cal["marker_radius_px"], stack=cal["stack"])
    g = img.split()[1]
    mid = g.getpixel((120, 40))
    near_start = g.getpixel((30, 40))
    near_end = g.getpixel((210, 40))
    assert mid > 150 and near_start > 150 and near_end > 150
    # ומחוץ לקצה — חשוך
    assert g.getpixel((235, 40)) < mid / 2


def test_the_cache_key_survives_every_shape():
    """מפתח המטמון חייב להיות בר-מיון לכל הצורות.

    קודם הוא היה `sorted((x, y) ...)`, ופס לינארי היה מפיל אותו —
    כלומר כל שקופית עם פס הייתה קורסת בדרך למטמון.
    """
    keys = [G.shape_key(s) for s in
            [(1.0, 2.0), ("line", [(0, 0), (5, 5)]), ("disc", 3, 4, 7.25)]]
    assert len(set(keys)) == 3
    assert sorted(keys)          # לא זורק
