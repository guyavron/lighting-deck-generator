"""מה שהעובד רואה על מצגת לפני ואחרי הפקה: רק מה שאפשר לתקן, ובשם.

בדיקת השמישות (13.10): "3 שקופיות ללא תצלום" בלי לומר אילו, והערות
מסגור על כל קומה. עכשיו כל שורה היא שקופית אחת, במספר שלה בשלב 3.
"""
import pytest

import server as SRV


@pytest.fixture
def bank(monkeypatch):
    # לקטגוריה "light up" יש תצלום ברירת מחדל; ל-"light wall" אין
    monkeypatch.setattr(SRV.make_deck, "load_category_assets",
                        lambda: {"light up": [{"asset_name": "a1"}]})
    monkeypatch.setattr(SRV.make_deck, "load_asset_index",
                        lambda: {"a1": "a1.jpg"})


def _spec(*areas):
    return SRV.BuildSpec(drawing="x.dxf", areas=[
        SRV.AreaSpec(name=name, x0=0, y0=0, x1=1, y1=1,
                     slides=[SRV.SlideSpec(**s) for s in slides])
        for name, slides in areas])


def test_only_slides_nobody_meant_to_leave_bare_are_listed(bank):
    spec = _spec(
        ("מטבח", [{"type": "light up"},                  # 1: ברירת מחדל
                  {"type": "light wall"}]),              # 2: חסר
        ("סלון", [{"type": "light wall", "mask": True},  # 3: פתיחה
                  {"type": "light wall", "done": True},  # 4: מאושרת
                  {"type": "light wall"}]))              # 5: חסר
    assert SRV._photo_gaps(spec) == [(0, 1, 2), (1, 2, 5)]


def test_the_check_names_area_and_slide(bank, monkeypatch):
    monkeypatch.setattr(SRV, "load_drawing", lambda name: {})
    monkeypatch.setattr(SRV, "_slide_blocker", lambda *a: None)
    monkeypatch.setattr(SRV, "_area_fixtures", lambda s, a, mask=False: ([], []))
    monkeypatch.setattr(SRV, "_area_box_world", lambda s, a, mask=False: (0, 0, 1, 1))
    spec = _spec(("מטבח", [{"type": "light up"}, {"type": "light wall"}]))
    assert SRV.deck_check(spec) == {"blocked": [], "far": [],
                                    "no_photo": [{"area": 0, "slide": 1}]}


# ── שקופית שלא תצא במצגת (D-045) ──

class _F:
    def __init__(self, layer, code="SH"):
        self.layer, self.code, self.x, self.y = layer, code, 0, 0


def _inside(monkeypatch, fixtures):
    monkeypatch.setattr(SRV, "_area_fixtures", lambda s, a, mask=False: (fixtures, []))


def _block(spec, si=0):
    a = spec.areas[0]
    return SRV._slide_blocker({"survey": None}, a, a.slides[si],
                              SRV.make_deck.load_category_assets(),
                              SRV.make_deck.load_asset_index(), 1)


def test_nothing_lit_and_no_photo_will_not_export(bank, monkeypatch):
    _inside(monkeypatch, [_F("light up")])
    spec = _spec(("מטבח", [{"type": "", "layers_lit": []}]))
    assert _block(spec) == "אין בה גופים מוארים ואין תצלום"


def test_a_photo_alone_is_enough_to_export(bank, monkeypatch):
    # שכבה בלי גופים באזור, אבל לקטגוריה יש תצלום — יוצאת
    _inside(monkeypatch, [_F("light up")])
    spec = _spec(("מטבח", [{"type": "light up", "layers_lit": ["light wall"]}]))
    assert _block(spec) is None


def test_an_empty_area_will_not_export(bank, monkeypatch):
    _inside(monkeypatch, [])
    spec = _spec(("מטבח", [{"type": "light up", "layers_lit": ["light up"]}]))
    assert _block(spec) == "האזור ריק מגופי תאורה"


def test_an_intro_slide_always_exports(bank, monkeypatch):
    _inside(monkeypatch, [_F("light up")])
    spec = _spec(("מטבח", [{"type": "light wall", "mask": True}]))
    assert _block(spec, 0) is None


def test_a_photos_only_slide_with_a_photo_exports(bank, monkeypatch, tmp_path):
    img = tmp_path / "p.jpg"
    img.write_bytes(b"x")
    monkeypatch.setattr(SRV.LIB, "image_path", lambda aid: str(img))
    _inside(monkeypatch, [_F("light up")])
    spec = _spec(("מטבח", [{"type": "light wall", "photos_only": True,
                            "photos": ["a1"]}]))
    assert _block(spec) is None


def test_a_photos_only_slide_without_a_photo_will_not_export(bank, monkeypatch):
    # B-06: יצאה כשקופית ריקה — כותרת וקו בלבד
    _inside(monkeypatch, [_F("light up")])
    spec = _spec(("מטבח", [{"type": "light wall", "photos_only": True},
                           {"type": "light wall", "photos_only": True,
                            "done": True}]))                # גם מאושרת
    assert _block(spec, 0) == "שקופית תצלומים בלבד, ואין בה תצלום"
    assert _block(spec, 1) == "שקופית תצלומים בלבד, ואין בה תצלום"


def test_a_blocked_slide_is_not_also_listed_without_photo(bank, monkeypatch):
    monkeypatch.setattr(SRV, "load_drawing", lambda name: {})
    monkeypatch.setattr(SRV, "_slide_blocker",
                        lambda s, a, sl, *r: "x" if sl.type == "light wall" else None)
    spec = _spec(("מטבח", [{"type": "light wall"}]))
    d = SRV.deck_check(spec)
    assert d["blocked"] == [{"area": 0, "slide": 0, "reason": "x"}]
    assert d["no_photo"] == []


def test_an_issue_says_which_slide_by_number_and_title(bank):
    spec = _spec(("מטבח", [{"type": "light up"},
                           {"type": "light wall", "option": "אופציה א"}]))
    i = SRV._issue(spec, 0, 1, 2, "בלי תצלום")
    assert i["area"] == 0 and i["slide"] == 1
    assert i["text"] == "בלי תצלום: שקופית 2 · מטבח | light wall | אופציה א"


def test_a_typed_title_is_what_the_worker_sees(bank):
    spec = _spec(("מטבח", [{"type": "light wall", "title": "מטבח | קיר"}]))
    assert SRV._issue(spec, 0, 0, 1, "בלי תצלום")["text"].endswith(
        "שקופית 1 · מטבח | קיר")


# ── B-02: שלב 3 מזהיר על גוף רחוק, ולא חותך אותו בשקט ──

class _P:
    kind = "point"

    def __init__(self, x, y):
        self.x, self.y, self.layer, self.code = x, y, "light up", "SH"


def test_deck_check_flags_a_slide_whose_strip_crosses_the_area_edge(bank, monkeypatch):
    # The window is the rectangle the worker cut, so a far fixture can no
    # longer stretch it. What can go wrong now is a lit strip that runs past
    # the edge: it is cut on the slide, and step 3 has to say so.
    monkeypatch.setattr(SRV, "load_drawing", lambda name: {})
    monkeypatch.setattr(SRV, "_slide_blocker", lambda *a: None)
    grid = [_P(x, y) for x in range(100, 2900, 100) for y in range(100, 700, 100)]
    strip = _P(2900, 400)
    strip.kind, strip.pts = "line", ((2800, 400), (3400, 400))
    monkeypatch.setattr(SRV, "_area_fixtures",
                        lambda s, a, mask=False: (grid + [strip], []))
    monkeypatch.setattr(SRV, "_area_box_world", lambda s, a, mask=False: (0, 0, 3000, 800))
    spec = _spec(("מטבח", [{"type": "light up"}]))
    d = SRV.deck_check(spec)
    assert d["far"] == [{"area": 0, "slide": 0, "count": 1}]


def test_deck_check_flags_nothing_for_a_normal_area(bank, monkeypatch):
    monkeypatch.setattr(SRV, "load_drawing", lambda name: {})
    monkeypatch.setattr(SRV, "_slide_blocker", lambda *a: None)
    grid = [_P(x, y) for x in range(0, 3000, 100) for y in range(0, 800, 100)]
    monkeypatch.setattr(SRV, "_area_fixtures", lambda s, a, mask=False: (grid, []))
    monkeypatch.setattr(SRV, "_area_box_world", lambda s, a, mask=False: (0, 0, 3000, 800))
    assert SRV.deck_check(_spec(("מטבח", [{"type": "light up"}])))["far"] == []
