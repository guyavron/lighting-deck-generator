"""The slide shows the area the worker cut, not just the span of its fixtures.

Framing used to follow the fixtures inside an area. Fixtures sit 50–100 cm
from the walls, so every slide lost its outer walls, and the worker had no way
to get them back. Now the window is the worker's rectangle (sub-areas already
worked this way, by their polygon). The risk that moves with it: a lit fixture
that crosses the rectangle's edge is cut, so step 3 counts those.
"""
import os
from types import SimpleNamespace as NS

import pytest

import server as SRV

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "..", "examples", "demo_apartment.dxf")


def _fx(x, y, kind="point", pts=(), radius=0.0):
    return NS(x=x, y=y, kind=kind, pts=pts, radius=radius, code="SH", layer="light up")


def test_the_rectangle_is_the_frame_not_the_fixtures():
    inside = [_fx(100, 100), _fx(200, 200)]
    box = (20, 20, 280, 280)
    pts = SRV._frame_points(inside, [], box)
    assert (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts)) == box


def test_a_sub_area_polygon_still_wins():
    poly = [(0, 0), (50, 0), (50, 50), (0, 50)]
    assert SRV._frame_points([_fx(10, 10)], poly, (0, 0, 999, 999)) == poly


def test_without_a_rectangle_the_fixtures_are_used():
    line = _fx(0, 0, kind="line", pts=((0, 0), (300, 0)))
    pts = SRV._frame_points([line, _fx(10, 50)], [], None)
    assert (0, 0) in pts and (300, 0) in pts and (10, 50) in pts


def test_a_strip_crossing_the_edge_is_counted():
    box = (0, 0, 100, 100)
    crossing = _fx(90, 50, kind="line", pts=((80, 50), (140, 50)))
    inside_strip = _fx(50, 50, kind="line", pts=((20, 50), (80, 50)))
    big_disc = _fx(95, 50, kind="circle", radius=20)
    small_disc = _fx(50, 50, kind="circle", radius=5)
    point = _fx(99, 99)
    assert SRV._cut_at_edge([crossing, inside_strip, big_disc, small_disc, point], box) == 2


@pytest.mark.skipif(not os.path.exists(DEMO), reason="run examples/make_demo_dxf.py")
def test_the_demo_living_room_keeps_its_outer_walls(monkeypatch, tmp_path):
    monkeypatch.setenv("LIGHTING_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(SRV, "DXF_DIR", os.path.dirname(DEMO), raising=False)
    s = SRV.load_drawing(os.path.basename(DEMO))
    x0w, y0w, x1w, y1w = s["window"]
    sx = SRV.OVERVIEW_W / (x1w - x0w)
    sy = SRV.OVERVIEW_H / (y1w - y0w)
    # The living room + kitchen, cut generously to include the 25 cm shell (cm)
    wx0, wy0, wx1, wy1 = -30, 540, 1010, 1030
    a = SRV.AreaSpec(name="living", x0=(wx0 - x0w) * sx, x1=(wx1 - x0w) * sx,
                     y0=(y1w - wy1) * sy, y1=(y1w - wy0) * sy)
    layout = SRV.SL.load_layout()
    inside, box, fr, size = SRV._area_geometry(s, None, a, layout)
    win = fr.window
    # the window covers the whole rectangle, outer walls included
    assert win[0] <= wx0 + 1 and win[2] >= wx1 - 1
    assert win[1] <= wy0 + 1 and win[3] >= wy1 - 1
    # and the fixtures alone would have stopped well inside it
    xs = [f.x for f in inside]
    assert min(xs) - wx0 > 50
