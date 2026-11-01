"""השקופית הנוכחית בולטת ברשימה (גיא, 25.10, אפשרות א).

קודם ההבלטה הייתה רק מסגרת כחולה לשדה, ו-`.slide.done input` (ירוק) בא
אחריה ב-CSS ודרס אותה. כשכל השקופיות מאושרות לא היה אפשר לדעת איפה אתה.
"""
import os
import re

SRC = open(os.path.join(os.path.dirname(__file__), "..", "src", "web", "index.html"),
           encoding="utf-8").read()


def _rule(sel):
    m = re.search(re.escape(sel) + r"\{[^}]*\}", SRC)
    assert m, sel
    return m.group(0), m.start()


def test_the_current_row_gets_a_blue_band_and_bar():
    rule, _ = _rule(".slide.cur")
    assert "background:" in rule and "box-shadow:inset" in rule


def test_the_current_title_stays_blue_and_bold_even_when_approved():
    rule, pos = _rule(".slide.cur input,\n  .slide.done.cur input")
    assert "border-color:var(--accent)" in rule and "font-weight:600" in rule
    _, done_pos = _rule(".slide.done input")
    assert pos > done_pos          # בא אחרי הירוק, ולכן גובר עליו
