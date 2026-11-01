"""הנחת תצלומי גופים — החצי של המערכת שהפרוסה המקורית דילגה עליו."""
import csv
import os

import pytest
import slide as SL

KN = os.path.join(os.path.dirname(__file__), "..", "knowledge")
ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture(scope="module")
def layout():
    return SL.load_layout()


def test_photos_are_on_the_right_never_below(layout):
    """התצלומים תמיד מימין. זו הייתה טעות שלי וצריך שתישאר סגורה."""
    for aspect in (0.378, 1.0, 3.74):
        plan = SL.plan_panel_box(aspect, layout)
        for n in (1, 2, 3):
            for bx, by, bw, bh in SL.photo_boxes(plan, layout, n):
                assert bx >= plan[0] + plan[2], "תצלום חופף לפאנל התוכנית"
                assert by >= layout["photo_area"]["y"] - 1


def test_photos_end_at_the_measured_right_edge(layout):
    """בכל שלוש מצגות הייחוס התצלומים נגמרים ב-x=1921 (96%)."""
    x_end = layout["photo_area"]["x_end"]
    for aspect in (0.378, 3.74):
        plan = SL.plan_panel_box(aspect, layout)
        boxes = SL.photo_boxes(plan, layout, 1)
        assert boxes and boxes[0][0] + boxes[0][2] == x_end


def test_photos_never_overflow_the_slide(layout):
    W, H = layout["canvas"]["width_px"], layout["canvas"]["height_px"]
    for aspect in (0.378, 1.0, 3.74):
        plan = SL.plan_panel_box(aspect, layout)
        for n in (1, 2, 3):
            for bx, by, bw, bh in SL.photo_boxes(plan, layout, n):
                assert bx + bw <= W and by + bh <= H


def test_fit_preserves_aspect_and_never_crops():
    box = (0, 0, 400, 200)
    x, y, w, h = SL._fit(box, (1000, 1000))
    assert w == h == 200                  # התאמה לפי הצלע הקצרה
    assert x + w <= box[0] + box[2] and y + h <= box[1] + box[3]


def test_category_asset_links_exist_and_resolve():
    """הקישור קטגוריה->תצלום נגזר מראיות ב-PSD, לא מניחוש."""
    p = os.path.join(KN, "category_assets.csv")
    if not os.path.exists(p):
        pytest.skip("category_assets.csv טרם נוצר — הרץ src/link_assets.py")
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    assert rows
    cats = {r["category"] for r in rows}
    assert "שקועים" in cats and "מערכת" in cats


def test_seeded_product_images_are_not_blank():
    """שכבות מוסתרות ב-PSD החזירו תמונות שקופות; חייב להישאר מתוקן."""
    from PIL import Image
    p = os.path.join(KN, "assets.csv")
    if not os.path.exists(p):
        pytest.skip("assets.csv טרם נוצר")
    rows = [r for r in csv.DictReader(open(p, encoding="utf-8-sig"))
            if r["kind"] == "product" and r.get("file")]
    if not rows:
        pytest.skip("אין תמונות מוצר במאגר")
    checked = 0
    for r in rows:
        full = os.path.join(ROOT, r["file"])
        if not os.path.exists(full):
            continue
        im = Image.open(full).convert("RGB")
        colours = im.resize((40, 40)).getcolors(40 * 40) or []
        top = max(c[0] for c in colours) if colours else 1600
        assert top / 1600 < 0.95, r["name"] + " ריקה"
        checked += 1
    assert checked, "אף תמונת מוצר לא נבדקה"
