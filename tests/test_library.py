"""מאגר התצלומים — הכללים שהוגדרו על החומר האמיתי.

הבדיקות כאן שומרות על שני דברים שקל לשבור בלי לשים לב: שהקטגוריה
באמת מסננת ולא רק מדרגת, ושבב שאינו מפצל אינו מוצג.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import library as LIB


@pytest.fixture(scope="module")
def assets():
    return LIB.load()


def test_library_is_seeded(assets):
    # The real bank (harvested from the studio's decks) holds 400+ photos.
    # The demo bank in this repository holds 26 (examples/make_demo_library.py).
    assert len(assets) >= 20, "המאגר נראה ריק — הרץ examples/make_demo_library.py"


def test_context_splits_into_independent_tags(assets):
    """הטקסונומיה מערבבת צירים בכוונה — היא מפורקת לתגיות, לא לעץ."""
    tagged = [a for a in assets if a["tags"]]
    assert len(tagged) >= 20, "כמעט לכל נכס יש הקשר; הפירוק כנראה נשבר"
    multi = [a for a in tagged if len(a["tags"]) > 1]
    assert multi, "נכס נושא כמה תגיות מצירים שונים בו-זמנית"


def test_structural_psd_layers_are_not_tags(assets):
    """'תוכנית' ו'סימון' הן שכבות מבנה ב-PSD, לא תוכן."""
    for a in assets:
        for noise in ("תוכנית", "סימון", "לייואט שחור"):
            assert noise not in a["tags"], "%s דלפה כתגית" % noise


def test_type_code_is_technical_product_name_is_decorative():
    """השרטוט עונה על 'להיראות או להיעלם' — זו לא שאלה שנשאלת."""
    for code in ("SH", "SP", "WA", "TA"):
        assert not LIB.is_decorative(code), "%s הוא קוד סוג" % code
    for name in ("TACCIA", "NULLA", "OZONE"):
        assert LIB.is_decorative(name), "%s הוא שם מוצר" % name


def test_narrowing_by_tag_shrinks_the_result_set():
    wide = LIB.search()
    tag = next((t for a in wide for t in a["crit_tags"]["install"]), None)
    assert tag, "אין תיוג סוג התקנה בכלל"
    narrow = LIB.search(tags=[tag])
    assert 0 < len(narrow) < len(wide)


def test_every_asset_has_an_image_on_disk(assets):
    missing = [a["name"] for a in assets
               if not os.path.exists(os.path.join(LIB.ROOT, "library",
                                                  a["asset_id"] + ".png"))]
    assert not missing, "נכסים בלי קובץ תמונה: %s" % missing[:5]


# ─── קריטריוני הסינון שנבחרו ──────────────────────────────────────

def test_criteria_vocabulary_loads():
    c = LIB.criteria()["criteria"]
    assert "install" in c and "room" in c
    assert c["install"]["multi"] is True, "סוג התקנה הוא בחירה מרובה (D-048)"
    assert c["install"].get("soft") is True, "סוג התקנה רך — לא מתויג אינו נעלם"
    assert c["style"]["multi"] is True, "סגנון הוא בחירה מרובה"


def test_evidence_backed_axes_are_filled(assets):
    """סוג התקנה וחלל נגזרים משם הקבוצה ב-PSD — זו ראיה."""
    assert sum(1 for a in assets if a["crit_tags"]["install"]) >= 10
    assert sum(1 for a in assets if a["crit_tags"]["room"]) >= 20


def test_visual_tags_are_proposals_until_a_person_approves(assets):
    """סגנון, גימור, אופי אור וגוון נקבעים בעין ולא מטקסט.

    הכלל הישן היה "הם חייבים להישאר ריקים". גיא ביקש במפורש שהמערכת
    תסתכל על התמונות ותתייג, ושהעובד רק יאשר או יתקן. לכן הם כן
    מתמלאים — **אבל תמיד כהצעה**, ו-`reviewed` נשאר ריק עד שאדם נוגע.

    מה שהבדיקה שומרת עליו הוא ההבחנה: ערך שהמערכת שיערה לא ייראה
    כמו ערך שאדם אישר. בלי זה ניחוש שגוי מקבל אישור בהיסח הדעת.
    """
    tagged = [a for a in assets
              if any(a["crit_tags"][k] for k in ("style", "finish", "beam", "cct"))]
    assert tagged, "התיוג החזותי לא רץ בכלל"
    for a in tagged:
        if not a["reviewed"]:
            assert not a["reviewed_by"], \
                "%s לא אושר אבל יש לו מאשר" % a["name"]


def test_every_visual_value_is_in_the_vocabulary(assets):
    """תיוג בעין חייב להישאר בתוך אוצר המילים שגיא בחר.

    ערך חופשי שנכתב בטעות לא יופיע כשבב ולכן ייעלם בשקט.
    """
    crit = LIB.criteria()["criteria"]
    for a in assets:
        for key in ("style", "finish", "beam", "cct", "install", "room"):
            allowed = set(crit[key]["values"])
            for v in a["crit_tags"][key]:
                assert v in allowed, \
                    "%s: %s אינו באוצר המילים של %s" % (a["name"], v, key)


def test_ambiguous_categories_are_not_forced(assets):
    """'מערכת' היא שלוש מסילות שאי אפשר להכריע ביניהן מהשם."""
    for a in assets:
        if "מערכת" in a["tags"] and not any(
                t in a["tags"] for t in ("שקועים", "נגרות", "קירי")):
            assert not a["crit_tags"]["install"], \
                "'מערכת' קיבלה סוג התקנה בלי ראיה: %s" % a["name"]


# ─── פאנל הסינון ─────────────────────────────────────────────────

def test_the_drawing_never_filters_the_library():
    """גיא: "הוא מניח מהשרטוט ואני לא רוצה את זה."

    פאנל שנפתח מסונן מראש מסתיר את רוב הספריה על סמך ניחוש
    שהעובד לא ביקש. מוסתרים אינם חלק מהחשבון — הם הוסתרו בידי
    אדם, וזו החלטה ולא הנחה.
    """
    visible = [a for a in LIB.load() if not a.get("hidden")]
    assert len(LIB.search()) == len(visible)
    assert len(LIB.search(category="שקועים")) == len(visible), \
        "הקטגוריה מהשרטוט סיננה את הספריה"


def test_the_whole_vocabulary_is_always_offered():
    """פאנל סינון מראה מה עומד לרשות העובד, לא חושף בהדרגה."""
    spec = {g["label"]: g for g in LIB.filter_spec()}
    want = LIB.criteria()["criteria"]
    assert len(spec) == len(want)
    for key, f in want.items():
        g = next(x for x in LIB.filter_spec() if x["facet"] == key)
        assert [v["tag"] for v in g["values"]] == f["values"], \
            "%s לא הציג את כל אוצר המילים" % key


def test_untagged_axes_report_zero_rather_than_vanish():
    """אפס אינו תקלה אלא מצב התיוג. ציר שנעלם נראה כאילו התעלמו."""
    spec = {g["facet"]: g for g in LIB.filter_spec()}
    assert spec["style"]["tagged"] >= 0
    assert spec["style"]["values"], "הציר נעלם במקום לדווח אפס"
    assert spec["install"]["tagged"] > 0


def test_single_and_multi_choice_match_the_spec():
    spec = {g["facet"]: g for g in LIB.filter_spec()}
    # D-048: שקופית של שקועים ופסים מסומנת בשני הסוגים
    assert spec["install"]["multi"] is True
    assert spec["cct"]["multi"] is False
    assert spec["style"]["multi"] is True
    assert spec["finish"]["multi"] is True


def test_room_promotes_and_never_hides(assets):
    """גוף ששימש בחדר שינה חייב להופיע גם כשמתכננים סלון."""
    spec = {g["facet"]: g for g in LIB.filter_spec()}
    assert spec["room"]["filters"] is False

    every = LIB.search()
    picked = LIB.search(rooms=["חדר שינה"])
    assert len(picked) == len(every), "החלל הסתיר תוצאות"
    assert "חדר שינה" in picked[0]["crit_tags"]["room"], \
        "החלל לא קידם לראש הרשימה"


def test_tags_intersect_and_do_narrow():
    every = LIB.search()
    narrow = LIB.search(tags=["מינימליסטי"])
    assert 0 < len(narrow) < len(every)
    assert all("מינימליסטי" in a["crit_tags"]["style"] for a in narrow)


# ─── סוג התקנה רך · D-048 ────────────────────────────────────────

def test_install_hides_only_what_is_tagged_as_something_else():
    """216 מתוך 417 לא תויגו (18.10). סינון קשיח היה מסתיר אותם."""
    every = LIB.search()
    got = LIB.search(tags=["שקוע בתקרה"])
    assert 0 < len(got) < len(every)
    for a in got:
        mine = a["crit_tags"]["install"]
        assert ("שקוע בתקרה" in mine) or (not mine and a.get("untagged"))
    hidden = [a for a in every if a["crit_tags"]["install"] and
              "שקוע בתקרה" not in a["crit_tags"]["install"]]
    assert hidden and not {a["asset_id"] for a in hidden} & {a["asset_id"] for a in got}


def test_untagged_come_after_the_matches():
    got = LIB.search(tags=["שקוע בתקרה"])
    flags = [bool(a.get("untagged")) for a in got]
    assert flags == sorted(flags), "לא מתויג הופיע לפני מתויג"


def test_two_install_types_are_a_union():
    one = LIB.search(tags=["שקוע בתקרה"])
    two = LIB.search(tags=["שקוע בתקרה", "גוף תלוי"])
    assert len(two) > len(one)


def test_auto_install_only_from_unambiguous_categories():
    assert LIB.auto_install(["שקועים", "פס לינארי", "שקועים"]) == ["שקוע בתקרה", "פס לינארי"]
    # "ספוטים" שקועים או על מסילה; "מערכת" אחת משלוש מסילות
    assert LIB.auto_install(["ספוטים", "מערכת"]) == []
    vocab = LIB.criteria()["criteria"]["install"]["values"]
    for v in LIB.install_for_category().values():
        assert v in vocab, "מיפוי לסוג התקנה שאינו באוצר המילים: " + v
