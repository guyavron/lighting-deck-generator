"""תמונה שנוספה למאגר (קישור מהאינטרנט או גרירת קובץ) נכנסת לשקופית
ומוצגת מיד — בלי לבטל וללחוץ שוב (גיא, 25.10).

הבאג: שני המסלולים הוסיפו את המזהה ל-`sl.photos` וקראו רק ל-`loadPhotos`,
שמרענן את רשת התמונות ולא את תצוגת השקופית. לחיצה על תמונה במאגר קוראת
ל-`renderSide` (שמרענן את התצוגה) ופותחת "שקופית". עכשיו שלושתם עוברים
באותה פונקציה.
"""
import os
import re

SRC = open(os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html"),
           encoding="utf-8").read()


def _fn(name):
    return re.search(r"function %s\(.*?\n\}\n" % name, SRC, re.S).group(0)


def test_one_function_adds_a_photo_and_refreshes_the_slide():
    fn = _fn("photoAdded")
    assert "renderSide()" in fn          # מרענן את תצוגת השקופית (previewTouch)
    assert "setView('slide')" in fn      # כמו לחיצה על תמונה
    assert "retitle(a)" in fn and "save()" in fn
    assert "length < 3" in fn            # לא יותר משלושה


def test_link_and_drop_both_use_it():
    wire = _fn("wirePhotos")
    assert wire.count("photoAdded(a, sl, j.id)") == 2, wire.count("photoAdded(a, sl, j.id)")
    # הדרך הישנה (רק loadPhotos אחרי push) לא נשארה
    assert "sl.photos.push(j.id);\n        save(); loadPhotos(a, sl);" not in wire
