import taxonomy as TX


def test_hebrew_category_resolves_to_block_codes():
    assert "SH" in TX.resolve("שקועים")
    assert "SP" in TX.resolve("ספוטים")
    assert "SUS" in TX.resolve("תלוי")


def test_english_key_also_resolves():
    assert TX.resolve("recessed") == TX.resolve("שקועים")


def test_alias_resolves():
    assert TX.resolve("תלוי פינת אוכל") == TX.resolve("תלוי")


def test_unknown_category_returns_none():
    assert TX.resolve("קטגוריה שלא קיימת") is None


def test_known_category_without_mapping_returns_empty_not_none():
    """אפלייט מוכרת אבל אין לה עדיין מיפוי — חייב להיות מובחן מ'לא מוכרת'."""
    assert TX.resolve("אפלייט") == []


def test_unmapped_codes_are_reported():
    seen = ["SH", "SP", "ZB", "659", "AURA 24"]
    un = TX.describe_unmapped(seen)
    assert "SH" not in un and "SP" not in un
    assert "ZB" in un and "659" in un
