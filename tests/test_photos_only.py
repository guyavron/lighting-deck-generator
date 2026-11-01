"""שקופית תצלומים בלבד (D-035) — הפריסה שנמדדה במצגת ייחוס א.

גיא: "עד 3 תצלומים — מיושרים למרכז ובמרחקים שווים". במצגת ייחוס א (12, 14,
52, 57, 61, 63, 65, 93, 96, 102): אותו גובה לכולם, כל תצלום ביחס שלו,
רווחים שווים, שוליים שווים משני הצדדים.
"""
import pytest

import slide as SL


@pytest.fixture(scope="module")
def layout():
    return SL.load_layout()


def _check_row(boxes, layout):
    po = layout["photos_only"]
    assert len({b[3] for b in boxes}) == 1                        # גובה אחד
    gaps = [boxes[i + 1][0] - (boxes[i][0] + boxes[i][2])
            for i in range(len(boxes) - 1)]
    assert all(abs(g - po["gap"]) <= 1 for g in gaps)             # רווחים שווים
    left = boxes[0][0] - po["x"]
    right = po["x_end"] - (boxes[-1][0] + boxes[-1][2])
    assert abs(left - right) <= 2                                 # ממורכז
    assert left >= 0 and right >= 0


@pytest.mark.parametrize("sizes", [
    [(1600, 1000)],
    [(800, 1000), (1200, 1000)],
    [(600, 900), (900, 900), (700, 1000)],
])
def test_a_row_is_centred_with_equal_gaps(sizes, layout):
    boxes = SL.photos_only_boxes(sizes, layout)
    assert len(boxes) == len(sizes)
    _check_row(boxes, layout)
    for (w, h), b in zip(sizes, boxes):                           # בלי מתיחה
        assert abs(b[2] / b[3] - w / h) < 0.01


def test_a_wide_row_shrinks_to_fit_and_stays_centred(layout):
    boxes = SL.photos_only_boxes([(3000, 1000)] * 3, layout)
    po = layout["photos_only"]
    assert boxes[0][3] < po["height"]
    _check_row(boxes, layout)
    mid = po["y"] + po["height"] / 2
    assert abs((boxes[0][1] + boxes[0][3] / 2) - mid) <= 1


def test_no_more_than_three(layout):
    assert len(SL.photos_only_boxes([(1000, 1000)] * 5, layout)) == 3


def test_resolve_without_a_plan(layout):
    g = SL.resolve(None, layout, [(1000, 800), (800, 1000)])
    assert g["plan"] is None and g["auto_plan"] is None
    assert len(g["photos"]) == 2
    moved = SL.resolve(None, layout, [(1000, 800)],
                       override={"photos": [[100, 200, 500, 400]]})
    assert moved["photos"][0] == (100, 200, 500, 400)


def test_a_photos_only_slide_takes_no_photo_by_itself():
    import server as SRV
    sl = SRV.SlideSpec(type="light up", photos_only=True)
    assert SRV._slide_photos(sl, {"light up": [{"asset_name": "x"}]},
                             {"x": "x.jpg"}, 1) == []
