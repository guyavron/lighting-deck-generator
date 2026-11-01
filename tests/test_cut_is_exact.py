"""What the worker cuts is exactly what reaches the slide.

The window around an area is larger than the cut: a margin, and widening to
the shape of the plan panel. Before this, the extra band showed pieces of the
neighbouring rooms the worker had left out. Now everything outside the cut is
background, as it already was for sub-areas (their polygon). Checked on the
demo drawing, on the slide panel and on the step-2 zoom view.
"""
import base64
import io
import os

import pytest
from PIL import Image

import server as SRV

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo_apartment.dxf")
CUT = (-30, 540, 1010, 1030)          # living + kitchen, in drawing units (cm)


def _area(s, cut=CUT, **kw):
    x0w, y0w, x1w, y1w = s["window"]
    sx = SRV.OVERVIEW_W / (x1w - x0w)
    sy = SRV.OVERVIEW_H / (y1w - y0w)
    wx0, wy0, wx1, wy1 = cut
    return SRV.AreaSpec(name="living", x0=(wx0 - x0w) * sx, x1=(wx1 - x0w) * sx,
                        y0=(y1w - wy1) * sy, y1=(y1w - wy0) * sy, **kw)


@pytest.fixture(scope="module")
def drawing(tmp_path_factory):
    if not os.path.exists(DEMO):
        pytest.skip("run examples/make_demo_dxf.py")
    os.environ["LIGHTING_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))
    SRV.DXF_DIR = os.path.dirname(DEMO)
    return SRV.load_drawing(os.path.basename(DEMO))


def _lit_pixels_between(img, to_px, x_from, x_to, y_from, y_to):
    (ax, ay), (bx, by) = to_px(x_from, y_to), to_px(x_to, y_from)
    box = (int(min(ax, bx)) + 2, int(min(ay, by)) + 2, int(max(ax, bx)) - 2, int(max(ay, by)) - 2)
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    band = img.convert("L").crop(box)
    return sum(1 for v in band.tobytes() if v > 30)


def test_a_regular_area_is_cut_to_its_rectangle(drawing):
    sl = SRV.SlideSpec()
    ring = SRV._cut_ring(drawing, _area(drawing), sl)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    assert min(xs) == pytest.approx(CUT[0], abs=2) and max(xs) == pytest.approx(CUT[2], abs=2)
    assert min(ys) == pytest.approx(CUT[1], abs=2) and max(ys) == pytest.approx(CUT[3], abs=2)


def test_a_sub_area_keeps_its_own_polygon(drawing):
    sub = [(0, 600), (400, 600), (400, 900), (0, 900)]
    assert SRV._cut_ring(drawing, _area(drawing), SRV.SlideSpec(), sub) == []


def test_the_slide_shows_nothing_outside_the_cut(drawing):
    layout = SRV.SL.load_layout()
    cal = SRV.G.calibration()
    sl = SRV.SlideSpec(layers_lit=[])          # nothing lit: no glow to spill
    sc = SRV._scene(os.path.basename(DEMO), "", [], _area(drawing), sl, drawing,
                    layout, cal, -1, 1)
    w = sc["fr"].window
    assert w[2] > CUT[2] + 20, "the window is wider than the cut, so there is a band to check"
    to_px, _ = SRV.PR.make_transform(w, sc["panel"].size)
    right_band = _lit_pixels_between(sc["panel"], to_px, CUT[2] + 3, w[2], CUT[1], CUT[3])
    assert right_band == 0, "%d drawn pixels right of the cut" % right_band
    inside = _lit_pixels_between(sc["panel"], to_px, CUT[0], CUT[2], CUT[1], CUT[3])
    assert inside > 1000, "the plan inside the cut is still drawn"


def test_the_step2_zoom_shows_nothing_outside_the_cut(drawing):
    a = _area(drawing)
    res = SRV.area_png(os.path.basename(DEMO), a.x0, a.y0, a.x1, a.y1)
    img = Image.open(io.BytesIO(base64.b64decode(res["png"].split(",", 1)[1])))
    # the zoom keeps a 4% margin around the cut: it must be empty now
    w, h = img.size
    top = img.convert("L").crop((0, 0, w, int(h * 0.02)))
    assert sum(1 for v in top.tobytes() if v > 30) == 0
