import pytest
import framing as F


PANEL = (332, 878)          # עמודת התוכנית בשקופית, מ-knowledge/layout.yaml


def test_never_crops_content():
    """החלון חייב להכיל את כל הנקודות שנבחרו."""
    pts = [(0, 0), (100, 0), (100, 400), (0, 400)]
    f = F.frame_for(pts, PANEL)
    x0, y0, x1, y1 = f.window
    for x, y in pts:
        assert x0 <= x <= x1 and y0 <= y <= y1


def test_window_matches_panel_aspect():
    pts = [(0, 0), (500, 0), (500, 100)]
    f = F.frame_for(pts, PANEL)
    x0, y0, x1, y1 = f.window
    assert abs(((x1 - x0) / (y1 - y0)) - PANEL[0] / PANEL[1]) < 0.01


def test_wide_sparse_selection_is_flagged():
    """אזור רחב ושטוח בעמודה פורטרטית — בדיוק מקרה הכישלון."""
    pts = [(x, 0) for x in range(0, 2000, 50)]
    f = F.frame_for(pts, PANEL)
    assert f.fill_ratio < 0.18
    assert any("דליל" in w for w in f.warnings)


def test_compact_room_is_not_flagged():
    pts = [(x, y) for x in range(0, 300, 30) for y in range(0, 800, 40)]
    f = F.frame_for(pts, PANEL)
    assert not any("דליל" in w for w in f.warnings), f.warnings


def test_far_outlier_does_not_blow_up_the_window():
    pts = [(x, y) for x in range(0, 300, 30) for y in range(0, 800, 40)]
    pts.append((2_000_000, 2_000_000))          # החריג האמיתי מ-1.dxf
    f = F.frame_for(pts, PANEL)
    assert f.window[2] - f.window[0] < 5000
    assert any("חריגים" in w for w in f.warnings)


def test_empty_selection_raises():
    with pytest.raises(ValueError):
        F.frame_for([], PANEL)


def test_multi_floor_selection_is_flagged():
    """שלוש קומות זו מעל זו — תיבה חוסמת מלאה, אבל התוצאה חסרת תועלת."""
    pts = []
    for base in (0, 5000, 10000):
        pts += [(x, base + y) for x in range(0, 300, 40) for y in range(0, 300, 40)]
    f = F.frame_for(pts, PANEL)
    assert any("אזורים מרוחקים" in w for w in f.warnings), f.warnings


def test_single_dense_room_not_flagged_as_multi():
    pts = [(x, y) for x in range(0, 300, 20) for y in range(0, 700, 20)]
    f = F.frame_for(pts, PANEL)
    assert not any("אזורים נפרדים" in w for w in f.warnings), f.warnings


def test_rows_within_one_room_are_not_separate_floors():
    """שורות שקועים בחדר אחד: הפער בין שורות קטן בהרבה מרוחב החדר."""
    pts = [(x, y) for x in range(0, 400, 50) for y in (0, 120, 240, 360, 480)]
    assert len(F.clusters(pts, axis=1)) == 1


def test_real_floors_are_separated():
    """פער בין קומות מסדר גודל של רוחב הבניין."""
    pts = []
    for base in (0, 6000, 12000):
        pts += [(x, base + y) for x in range(0, 400, 50) for y in (0, 120, 240)]
    assert len(F.clusters(pts, axis=1)) == 3


def test_cluster_threshold_matches_real_dxf_geometry():
    """המספרים האמיתיים מ-111 (2).dxf: רוחב ~2470, פער בין קומות ~2834,
    מרווח בין שורות בתוך קומה ~200."""
    floor_a = [(x, y) for x in range(0, 2470, 200) for y in (0, 200, 400, 660)]
    floor_b = [(x, y + 3494) for x, y in floor_a]
    assert len(F.clusters(floor_a, axis=1)) == 1
    assert len(F.clusters(floor_a + floor_b, axis=1)) == 2


# ── מקרא ליד הבניין אינו מוצע כאזור (D-044) ──

def _building():
    # קומה: רשת גופים מסוג אחד או שניים, ברוחב 3000
    return ([(1000 + 150 * i, 100 * j) for i in range(20) for j in range(10)],
            ["SH" if (i + j) % 3 else "SP" for i in range(20) for j in range(10)])


def test_a_legend_column_next_to_the_building_is_found():
    pts, codes = _building()
    kinds = ["SH", "SP", "TA", "LINE", "zb", "FOIL", "CIRCLE", "SH-DS"]
    leg = [(300, 2000 - 150 * k) for k in range(len(kinds))]
    found = F.legend_columns(pts + leg, codes + kinds)
    assert found == set(range(len(pts), len(pts) + len(kinds)))


def test_a_narrow_row_of_one_kind_is_not_a_legend():
    # שורת TA1 ב-3.dxf, פס LINE ב-2.dxf — צרים וגבוהים, אבל מסוג אחד
    pts, codes = _building()
    col = [(300, 2000 - 150 * k) for k in range(8)]
    assert F.legend_columns(pts + col, codes + ["TA1"] * 8) == set()


def test_a_drawing_without_a_legend_loses_nothing():
    pts, codes = _building()
    assert F.legend_columns(pts, codes) == set()


# ── B-02: גוף דולק בקצה האזור לא נחתך ──

def _grid():
    return [(x, y) for x in range(0, 3000, 50) for y in range(0, 800, 50)]


def test_fixtures_at_the_edge_stay_inside_the_window():
    # קודם: אחוזונים 2%–98% חתכו את הקצוות. שני גופי FOIL בקצה לא הופיעו
    pts = _grid() + [(3500, 400), (-450, 790)]
    f = F.frame_for(pts, PANEL)
    x0, y0, x1, y1 = f.window
    assert all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in pts)


def test_every_point_is_inside_even_with_one_far_in_one_axis_only():
    pts = _grid() + [(0, 1800)]        # רחוק, אבל בתוך פי 5 מהפיזור
    f = F.frame_for(pts, PANEL)
    assert f.window[1] <= 0 and f.window[3] >= 1800


def test_a_row_of_fixtures_on_one_line_is_not_called_an_outlier():
    pts = [(x, 500) for x in range(0, 2000, 100)] + [(2050, 505)]
    f = F.frame_for(pts, PANEL)
    assert F.far_outlier_count(pts) == 0
    assert f.window[2] >= 2050


def test_far_outlier_count_names_how_many_are_ignored():
    pts = _grid() + [(2_000_000, 2_000_000), (1_900_000, 1_900_000)]
    assert F.far_outlier_count(pts) == 2
    assert F.far_outlier_count(_grid()) == 0
