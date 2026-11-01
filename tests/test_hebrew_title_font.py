"""כותרת עברית נכתבת ל-PPTX כמו במצגות הסטודיו (גיא, 25.10).

הבאג: ב-PowerPoint, כשהגופן Assistant Light מגיע מהענן של מיקרוסופט (לא
מותקן במחשב), כותרות עבריות יצאו מעוותות — "קומה" הוצג "ק מה", "שקועים"
"שק עי ם". הכלי כתב `lang="he-IL" altLang="en-US"` ובלי `charset` לגופן.
בבדיקה על המצגת של גיא: הורדת `altLang` לבדה תיקנה, וגם הוספת
`charset="-79"` לבדה. מצגות הסטודיו (DECK F, DECK B, שנכתבו ב-PowerPoint)
כותבות בדיוק כך: בלי `altLang`, ועם `pitchFamily="2" charset="-79"`
ב-`<a:latin>` וב-`<a:cs>`. עושים את שניהם.
"""
import os
import sys

from pptx import Presentation

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import slide as SL  # noqa: E402

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _run(text):
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[6])
    tb = s.shapes.add_textbox(0, 0, 100, 100)
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = text
    r.font.name = "Assistant Light"
    SL._hebrew_run(r, "Assistant Light", SL.is_hebrew(text))
    return r._r.find(A + "rPr")


def test_hebrew_title_has_no_alternate_language():
    rPr = _run("קומה א | שקועים")
    assert rPr.get("lang") == "he-IL"
    assert rPr.get("altLang") is None


def test_hebrew_title_marks_the_font_as_hebrew_in_latin_and_cs():
    rPr = _run("קומה א | שקועים")
    for tag in ("latin", "cs"):
        e = rPr.find(A + tag)
        assert e is not None and e.get("typeface") == "Assistant Light", tag
        assert e.get("charset") == "-79" and e.get("pitchFamily") == "2", tag


def test_english_title_is_left_as_it_was():
    rPr = _run("UPPER FLOOR | DOWNLIGHTS")
    assert rPr.get("lang") == "en-US" and rPr.get("altLang") is None
    assert rPr.find(A + "cs").get("charset") is None
    latin = rPr.find(A + "latin")
    assert latin is None or latin.get("charset") is None
