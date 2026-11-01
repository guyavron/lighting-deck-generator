import dxftext as T  # נתיב src נוסף ב-conftest.py


def test_uplus():
    assert T.decode_uplus(r'\U+05D0\U+05D1') == 'אב'


def test_shx_hebrew_real_samples():
    # דוגמאות אמיתיות מ-1.dxf ו-3.dxf
    assert T.decode(r'vfbv k,turv ctrubu,')['method'] == 'shx_hebrew'
    assert 'הכנה' in T.decode(r'vfbv k,turv ctrubu,')['text']


def test_reversed_latin_real_sample():
    # דוגמה אמיתית מ-2.dxf
    d = T.decode('THGIL STESOLC ROF NOITAREPERP')
    assert d['method'] == 'reversed_latin'
    assert 'LIGHT' in d['text'] and 'CLOSETS' in d['text']


def test_plain_english_untouched():
    d = T.decode('LIGHT SYSTEM')
    assert d['method'] == 'plain'
    assert d['text'] == 'LIGHT SYSTEM'


def test_plain_hebrew_untouched():
    d = T.decode('הכנה לתאורה')
    assert d['method'] == 'plain'


def test_fixture_code_reversal():
    assert T.normalise_code('HS') == 'SH'
    assert T.normalise_code('SD-HS') == 'SH-DS'
    assert T.normalise_code('PS') == 'SP'


# מחרוזות אמיתיות שחולצו מ-1.dxf ו-3.dxf, עם התרגום הנכון
REAL_SHX = [
    ('vfbv k,turv ctrubu,', 'הכנה לתאורה בארונות'),
    ('nheuo gp"h tsrhfk', 'מיקום עפ"י אדריכל'),
    ('vfbv k,turv naukc, cbdru,', 'הכנה לתאורה משולבת בנגרות'),
    ('vfbv k,turv nmnjhhv', 'הכנה לתאורה מצמחייה'),
    ('vfbv k,turv ehrh,', 'הכנה לתאורה קירית'),
]


def test_shx_real_strings_decode_exactly():
    for raw, expected in REAL_SHX:
        got = T.decode(raw)
        assert got['method'] == 'shx_hebrew', f'{raw!r} classified as {got["method"]}'
        assert got['text'] == expected, f'{raw!r} -> {got["text"]!r}, expected {expected!r}'
