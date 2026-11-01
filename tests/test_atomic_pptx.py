"""B-03 (QA 21-22.10): קריסה באמצע כתיבת מצגת לא משאירה קובץ שבור.

`prs.save` כתב ישירות לשם הסופי. מחשב שנכבה באמצע השאיר
`deck_….pptx` שלא נפתח ("File is not a zip file"), בשם שנראה כמו כל
מצגת. עכשיו כותבים לשם זמני ורק בסוף מחליפים — או מצגת שלמה או כלום.
"""
import os

import pytest
from pptx import Presentation
from pptx.presentation import Presentation as _Prs

import slide as SL

LAYOUT = SL.load_layout("black")


def test_crash_while_saving_leaves_no_file_under_the_final_name(tmp_path, monkeypatch):
    def crashing_save(self, path):
        with open(path, "wb") as fh:
            fh.write(b"PK\x03\x04 half a presentation")
        raise OSError("disk unplugged")
    monkeypatch.setattr(_Prs, "save", crashing_save)

    out = tmp_path / "deck_20261024-100000.pptx"
    with pytest.raises(OSError):
        SL.build_pptx(str(out), [], LAYOUT)
    assert not out.exists()
    # גם לא קובץ ששמו נראה כמו מצגת
    assert [f for f in os.listdir(tmp_path) if f.endswith(".pptx")] == []


def test_a_good_save_gives_one_openable_file_and_no_leftovers(tmp_path):
    out = tmp_path / "deck_20261024-100001.pptx"
    SL.build_pptx(str(out), [], LAYOUT)
    Presentation(str(out))                      # נפתח בלי שגיאה
    assert os.listdir(tmp_path) == [out.name]   # בלי קובץ זמני
