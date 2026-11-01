r"""פענוח טקסט מ-DXF — שלוש בעיות קידוד נפרדות שנמדדו בקבצים אמיתיים.

1. SHX: שרטוטים ישנים שומרים עברית כהקשות מקלדת לטיניות.
   'vfbv k,turv ctrubu,'  ->  'הכנה לתאורה בארונות'
2. \U+05D0 escapes: אוטוקאד חדש. 3,683 מהם בקובץ אחד.
3. לטינית הפוכה: הוקלד בשדה RTL.  'THGIL' -> 'LIGHT'
   קודי גופים תמיד הפוכים: 'HS'->SH, 'PS'->SP, '042=H'->H=240
"""
import re

# מיפוי מקלדת עברית סטנדרטית (פריסה ישראלית, מיקומי QWERTY).
# פונטי SHX ישנים שומרים עברית כהקשות הלטיניות עצמן.
SHX_MAP = {
    'q': '/', 'w': "'", 'e': 'ק', 'r': 'ר', 't': 'א', 'y': 'ט',
    'u': 'ו', 'i': 'ן', 'o': 'ם', 'p': 'פ',
    'a': 'ש', 's': 'ד', 'd': 'ג', 'f': 'כ', 'g': 'ע', 'h': 'י',
    'j': 'ח', 'k': 'ל', 'l': 'ך', ';': 'ף',
    'z': 'ז', 'x': 'ס', 'c': 'ב', 'v': 'ה', 'b': 'נ', 'n': 'מ',
    'm': 'צ', ',': 'ת', '.': 'ץ', '/': '.',
}

UPLUS = re.compile(r'\\U\+([0-9A-Fa-f]{4})')
MTEXT_FMT = re.compile(r'\\[A-Za-z][^;\\]*;|[{}]|\\[PpLlOoKkXx]')

HEB = re.compile(r'[\u0590-\u05FF]')
# מילים לטיניות שמופיעות הפוכות בשרטוטי הסטודיו
REV_HINTS = ('THGIL', 'NOITARAPERP', 'NOITAREPERP', 'RORRIM', 'TEKCOS',
             'METSYS', 'LLAW', 'DELLOTNOC', 'STESOLC', 'YTINAV', 'DEDNPSUS')


def decode_uplus(s: str) -> str:
    return UPLUS.sub(lambda m: chr(int(m.group(1), 16)), s)


def strip_mtext(s: str) -> str:
    return MTEXT_FMT.sub('', s)


def looks_shx_hebrew(s: str) -> bool:
    """טקסט לטיני שהוא למעשה עברית שהוקלדה בפונט SHX."""
    if HEB.search(s):
        return False
    letters = [c for c in s.lower() if c.isalpha()]
    if len(letters) < 4:
        return False
    mapped = sum(1 for c in letters if c in SHX_MAP)
    # עברית-כלטינית משתמשת כמעט רק בתווים שיש להם מיפוי,
    # ובצירופים שאינם אנגלית תקינה
    return mapped / len(letters) > 0.92 and not _is_englishish(s)


_COMMON_EN = {'light', 'wall', 'floor', 'ceiling', 'spot', 'system', 'plan',
              'the', 'and', 'for', 'a', 'of', 'to', 'in', 'mirror', 'socket'}


def _is_englishish(s: str) -> bool:
    w = re.findall(r'[A-Za-z]{2,}', s.lower())
    return bool(w) and sum(1 for x in w if x in _COMMON_EN) / len(w) > 0.3


def from_shx(s: str) -> str:
    return ''.join(SHX_MAP.get(c, SHX_MAP.get(c.lower(), c)) for c in s)


def looks_reversed_latin(s: str) -> bool:
    up = s.upper()
    return any(h in up for h in REV_HINTS)


def decode(raw: str) -> dict:
    """מחזיר את הטקסט המפוענח ואת השיטה ששימשה — השיטה חשובה לניפוי."""
    s = strip_mtext(decode_uplus(raw)).strip()
    method = 'plain'
    if looks_reversed_latin(s):
        # היפוך המחרוזת כולה. סדר המילים מתקן את עצמו:
        # 'THGIL STESOLC ROF NOITAREPERP' -> 'PREPERATION FOR CLOSETS LIGHT'
        s = s[::-1]
        method = 'reversed_latin'
    elif looks_shx_hebrew(s):
        s = from_shx(s)
        method = 'shx_hebrew'
    return {'text': s, 'method': method, 'raw': raw}


def normalise_code(raw: str) -> str:
    """קוד גוף בטקסט שמור הפוך: 'HS'->'SH', 'SD-HS'->'SH-DS'."""
    s = raw.strip()
    return s[::-1] if s else s
