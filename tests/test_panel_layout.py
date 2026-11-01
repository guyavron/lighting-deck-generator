"""B-18 (QA 21-22.10): מסך לפטופ. הפאנל הימני היה ארוך (245 תמונות ברצף,
סינון של 540px, חמישה כפתורים גדולים), והפקדים של השקופית ירדו מתחת לקו.

גיא בחר (אפשרות א): רשימת השקופיות למעלה, כפתורי התחלה בשורה קטנה, שכבות
השרטוט בתחתית. הבדיקות כאן סורקות את המבנה ב-index.html.
"""
import os
import re

SRC = open(os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html"),
           encoding="utf-8").read()


def _work_mode():
    return re.search(r"function renderWorkMode\(box\)\{.*?\n\}\n", SRC, re.S).group(0)


def test_slide_list_comes_before_the_start_buttons_and_layers_come_last():
    fn = _work_mode()
    i_list = fn.index("שקופיות באזור (")
    i_btns = fn.index('<div class="mk">')
    i_layers = fn.index("html += layersPanel();")
    i_photos = fn.index("photoPanel(a, sl)")
    assert i_list < i_btns < i_photos < i_layers
    assert "layersPanel()" not in fn[:i_list]


def test_start_buttons_are_one_compact_row():
    css = re.search(r"\.mk\{[^}]*\}", SRC).group(0)
    assert "flex-wrap:wrap" in css and "flex-direction:column" not in css
    for key in ("data-addslide", "data-submode", "data-pickmode", "data-photoslide", "data-pvopen"):
        assert key in _work_mode()


def test_photo_filters_are_folded_and_the_grid_is_paged():
    fn = re.search(r"function renderPhotos\(a, sl\)\{.*?\n\}\n", SRC, re.S).group(0)
    assert '<details class="f-fold" data-ffold' in fn and "</details>`;" in fn
    assert "const PH_PAGE = 24;" in SRC
    assert "data-phmore" in fn
    # מה שנבחר מוצג תמיד, גם אם הוא מעבר לעמוד הראשון
    assert "chosen.indexOf(r.id) >= 0" in fn


def test_a_new_search_starts_again_from_the_first_page():
    fn = re.search(r"function loadPhotos\(a, sl\)\{.*?\n\}\n", SRC, re.S).group(0)
    assert "S.phLimit = PH_PAGE" in fn


def test_slide_controls_sit_above_the_slide_and_stay_visible():
    inner = re.search(r"\.pv-inner\{[^}]*\}", SRC).group(0)
    assert "column-reverse" in inner
    foot = re.search(r"\.pv-foot\{[^}]*\}", SRC).group(0)
    assert "position:sticky" in foot and "top:0" in foot


def test_the_slide_shrinks_to_fit_the_window_height():
    stage = re.search(r"\.pv-stage\{[^}]*\}", SRC).group(0)
    assert "100vh" in stage and "min(100%" in stage


def test_every_glow_colour_has_a_name_on_hover():
    assert 'title="${c.name}" aria-label="${c.name}"' in SRC
