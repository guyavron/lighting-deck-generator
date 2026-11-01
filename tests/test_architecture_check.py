"""האם יש רקע אדריכלי שיוצג (D-037).

בדיקת השמישות: 3.dxf עבר את הבדיקה הישנה (1,266 ישויות — חזיתות על
שכבה "0", הרחק מהתוכנית ומוסתרות), ויצאו שקופיות שחורות בלי אזהרה.
המספרים כאן הם מפקד השכבות האמיתי של ארבעת השרטוטים.
"""
from types import SimpleNamespace

import server as SRV


def _s(has_arch, layers):
    return {"survey": SimpleNamespace(has_architecture=has_arch),
            "layers": [{"name": n, "n": k, "role": r} for n, k, r in layers]}


def test_111_has_a_background():
    s = _s(True, [("I-FURN", 16744, "show"), ("A-WALL-PATT", 5967, "show"),
                  ("A-FLOR-OVHD", 123974, "hide"), ("light up", 4639, "lighting")])
    assert SRV._shows_architecture(s)


def test_3_is_caught_although_the_file_has_entities():
    s = _s(True, [("light up", 37225, "lighting"), ("0", 4313, "hide")])
    assert not SRV._shows_architecture(s)
    assert SRV._hidden_candidates(s) == [{"name": "0", "n": 4313}]


def test_1_and_2_have_no_background():
    assert not SRV._shows_architecture(_s(False, [("light dim", 45010, "lighting"),
                                                   ("0", 2962, "hide")]))
    assert not SRV._shows_architecture(_s(False, [("light dim", 20047, "lighting")]))
