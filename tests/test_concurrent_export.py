"""B-01 (QA 21-22.10): שתי הפקות בו-זמניות לא מערבבות תוכניות.

תמונות הביניים נשמרו בשמות קבועים (`out/.ui_001.png`) ומשותפות לכל
ההפקות, ו-`stamped()` נתן אותו שם לשתי הפקות באותה שנייה. מצגת של
לקוח אחד יצאה עם התוכנית של לקוח אחר, בלי שום אזהרה.
"""
import os
from datetime import datetime

from PIL import Image

import server as SRV
import slide as SL


def test_stamped_never_gives_the_same_name_twice(tmp_path, monkeypatch):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 22, 19, 16, 1)
    monkeypatch.setattr(SL, "datetime", _Fixed)
    names = {SL.stamped(str(tmp_path), "deck", ".pptx") for _ in range(5)}
    assert len(names) == 5


def test_stamped_skips_a_name_that_already_exists(tmp_path, monkeypatch):
    class _Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 22, 19, 16, 1)
    monkeypatch.setattr(SL, "datetime", _Fixed)
    first = SL.stamped(str(tmp_path), "deck", ".pptx")
    open(first, "wb").write(b"x")
    assert SL.stamped(str(tmp_path), "deck", ".pptx") != first


def test_two_exports_keep_their_own_plan_images(tmp_path, monkeypatch):
    colors = iter([(255, 0, 0), (0, 0, 255)])
    monkeypatch.setattr(SRV, "OUT_DIR", str(tmp_path))
    monkeypatch.setattr(SRV, "load_drawing",
                        lambda name: {"shown": set(), "path": "p.dxf"})
    monkeypatch.setattr(SRV.make_deck, "sha1_of", lambda p: "0")
    monkeypatch.setattr(SRV, "_slide_blocker", lambda *a: None)
    monkeypatch.setattr(SRV, "_remember_exported_photos", lambda spec: [])
    monkeypatch.setattr(SRV, "_layer_styles", lambda s, ls: None)
    monkeypatch.setattr(SRV.make_deck, "load_category_assets", lambda: {})
    monkeypatch.setattr(SRV.make_deck, "load_asset_index", lambda: {})
    monkeypatch.setattr(SRV, "_photo_gaps", lambda spec: [])

    def scene(*a, **k):
        return {"panel": Image.new("RGB", (4, 4), next(colors)),
                "fr": None, "geom": {}, "photos": [], "cards": []}
    monkeypatch.setattr(SRV, "_scene", scene)

    built = []
    monkeypatch.setattr(SRV.SL, "build_pptx",
                        lambda path, slides, layout: built.append(slides) or path)

    def spec():
        return SRV.BuildSpec(drawing="x.dxf", areas=[
            SRV.AreaSpec(name="א", x0=0, y0=0, x1=1, y1=1,
                         slides=[SRV.SlideSpec(type="light up")])])
    SRV.build(spec())          # הפקה ראשונה: אדום
    SRV.build(spec())          # הפקה שנייה: כחול

    def pixel(plan):
        if isinstance(plan, str):
            return Image.open(plan).convert("RGB").getpixel((0, 0))
        plan.seek(0)
        return Image.open(plan).convert("RGB").getpixel((0, 0))
    assert [pixel(b[0]["plan"]) for b in built] == [(255, 0, 0), (0, 0, 255)]
    assert not [f for f in os.listdir(tmp_path) if f.startswith(".ui_")]
