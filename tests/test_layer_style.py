"""עובי ובהירות לכל שכבה, ושקופית פתיחה בלי תצלום (D-031).

גיא: "לדקק ולעבות שכבות... להבהיר ולהכהות שכבות — כדי שיהיה אפשר
לייצר ניגודיות והבדלה בין קירות לרהיטים". נבדק על שרטוט אמיתי
קטן ולא על כוונה: שכבה שעובתה מכסה יותר פיקסלים, ושכבה שהובהרה
בהירה יותר — **והשכנה שלה לא זזה**.
"""
import ezdxf
import numpy as np
import pytest
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing import recorder

import plan_render as PR
import slide as SL

WIDTHS = {"thin": 0.4, "normal": 1.0, "thick": 2.0, "xthick": 3.2}
GREY = (140, 140, 140)


@pytest.fixture(scope="module")
def player():
    """שני קווים אופקיים: קיר למעלה, רהיט למטה."""
    doc = ezdxf.new()
    doc.layers.add("A-WALL")
    doc.layers.add("I-FURN")
    msp = doc.modelspace()
    msp.add_line((0, 70), (100, 70), dxfattribs={"layer": "A-WALL"})
    msp.add_line((0, 30), (100, 30), dxfattribs={"layer": "I-FURN"})
    rec = recorder.Recorder()
    Frontend(RenderContext(doc), rec, config=Configuration()).draw_layout(
        msp, finalize=True)
    return rec.player()


def _render(player, styles=None):
    img, _, _ = PR.render(player, (200, 200), window=(0, 0, 100, 100),
                          line_color=GREY, fill_color=(70, 70, 70),
                          styles=styles, widths=WIDTHS)
    a = np.asarray(img.convert("L")).astype(int)
    return a[:100], a[100:]          # חצי עליון = קיר, תחתון = רהיט


def test_a_thickened_layer_covers_more_and_its_neighbour_does_not_move(player):
    wall0, furn0 = _render(player)
    wall1, furn1 = _render(player, {"A-WALL": {"w": "xthick", "b": 0}})
    assert (wall1 > 20).sum() >= 2 * (wall0 > 20).sum()
    assert np.array_equal(furn0, furn1)


def test_brightness_moves_one_layer_both_ways(player):
    wall0, furn0 = _render(player)
    bright, f_b = _render(player, {"I-FURN": {"w": "normal", "b": 0.8}})[::-1]
    dark, f_d = _render(player, {"I-FURN": {"w": "normal", "b": -0.6}})[::-1]
    assert bright.max() > furn0.max() > dark.max()
    assert np.array_equal(f_b, wall0) and np.array_equal(f_d, wall0)


def test_shade_ends_at_white_and_black():
    assert PR.shade(GREY, 1) == (255, 255, 255)
    assert PR.shade(GREY, -1) == (0, 0, 0)
    assert PR.shade(GREY, 0) == GREY


def test_default_style_is_not_a_style():
    """שכבה שהוחזרה לברירת המחדל אינה נכנסת למפתח המטמון."""
    assert PR.layer_looks({"A": {"w": "normal", "b": 0}}, WIDTHS, 3,
                          GREY, GREY) == {}


def test_lighting_layers_never_take_a_style():
    """הזוהר מכויל מול הייחוס; קו תאורה מעובה היה מתחרה בו."""
    import server as SRV
    st = {"lighting_layers": {"light up"}}
    got = SRV._layer_styles(st, {"light up": {"w": "thick", "b": 0.5},
                                 "A-WALL": {"w": "thick", "b": 9},
                                 "I-FURN": {"w": "bogus", "b": 0}})
    assert got == {"A-WALL": {"w": "thick", "b": 1.0}}


def test_the_widths_live_in_knowledge_not_in_code():
    ls = SL.load_layout()["plan_appearance"]["layer_style"]
    assert ls["widths"]["normal"]["factor"] == 1.0
    assert set(ls["widths"]) == set(WIDTHS)


# ─── שקופית פתיחה ─────────────────────────────────────────────────

def test_an_opening_slide_takes_no_photo_by_itself():
    import server as SRV
    cats = {"light up": [{"asset_name": "x"}]}
    idx = {"x": "x.jpg"}
    plain = SRV.SlideSpec(type="light up")
    opening = SRV.SlideSpec(type="light up", mask=True)
    assert SRV._slide_photos(plain, cats, idx, 1) == ["x.jpg"]
    assert SRV._slide_photos(opening, cats, idx, 1) == []


def test_a_plan_alone_takes_the_whole_width_and_is_centred():
    layout = SL.load_layout()
    beside = SL.plan_panel_box(3.0, layout)
    alone = SL.plan_panel_box(3.0, layout, alone=True)
    assert alone[2] > beside[2]
    right = layout["photo_area"]["x_end"]
    left = layout["plan_panel"]["x"]
    assert abs((alone[0] - left) - (right - alone[0] - alone[2])) <= 1


# ─── הציור המהיר ──────────────────────────────────────────────────

def test_the_fast_render_draws_exactly_what_the_replay_drew(player):
    """הגיאומטריה המוכנה (D-033) אינה רשאית לשנות פיקסל.

    נמדד ב-`111 (2).dxf`: סקירה ואזור זהים לחלוטין, אזור ב-1.5
    שניות במקום 7.4 — ו-0.3 מהפעם השנייה.
    """
    kw = dict(window=(0, 0, 100, 100), line_color=GREY,
              fill_color=(70, 70, 70), widths=WIDTHS,
              styles={"A-WALL": {"w": "thick", "b": 0.4}})
    for layers in (None, {"A-WALL"}):
        a = np.asarray(PR.render(player, (200, 200), layers=layers, **kw)[0])
        b = np.asarray(PR.render_replay(player, (200, 200), layers=layers,
                                        **kw)[0])
        assert np.array_equal(a, b)


def test_a_hidden_layer_is_not_even_prepared(player):
    """הכנה של כל השכבות נמדדה ב-3 דקות; מכינים רק את המוצגות."""
    g = PR.compiled(player, {"A-WALL"})
    assert g.names == ["A-WALL"]


def test_the_darkest_setting_stops_at_sixty_percent():
    """‎-90% העלים את השרטוט כמעט לגמרי (13.10). גם ערך ישן נאכף."""
    import server as SRV
    got = SRV._layer_styles({}, {"A-WALL": {"w": "normal", "b": -0.9}})
    assert got == {"A-WALL": {"w": "normal", "b": -0.6}}
