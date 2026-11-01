"""כיול מנוע ההארה מול הפרופיל הרדיאלי שנמדד בתמונה מרוכבת אמיתית.

שני פרמטרים חופשיים: רדיוס צורת הסמן, והיחס בין Size של פוטושופ
לסטיית התקן של הגאוסיאן. שאר הערכים מגיעים מ-knowledge/glow.yaml.
"""
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__))
from PIL import Image
import glow as G

# נמדד ב-a deck-A composite סביב מוקד מבודד ב-(170,1004), ערוץ R.
# הרקע שחור, ולכן הערך הוא ישירות תרומת ההארה.
REF = {0: 240, 2: 165, 4: 77, 6: 69, 8: 61, 10: 52, 12: 43, 14: 35,
       16: 27, 18: 21, 20: 15, 22: 10, 24: 6, 26: 3, 28: 1, 30: 0}


def profile(radius, k, preset, stack=1, n=140):
    G.SIZE_TO_SIGMA = k
    im = G.render_glow((n, n), [(n // 2, n // 2)], preset, radius=radius, stack=stack)
    px = im.load()
    return {d: px[n // 2 + d, n // 2][0] for d in REF}


def error(radius, k, preset, stack=1):
    p = profile(radius, k, preset, stack)
    # d=0 ו-d=2 מושמטים: הם בתוך הצורה האטומה ובשפה המוחלקת שלה,
    # ואינם מודדים את ההארה עצמה.
    ds = [d for d in REF if d > 2]
    return (sum((p[d] - REF[d]) ** 2 for d in ds) / len(ds)) ** 0.5


if __name__ == "__main__":
    preset = G.preset_for("deck_a")
    best = None
    for stack in (1, 2, 3):
        for r10 in range(10, 90, 2):        # רדיוס 1.0 .. 8.8
            for k100 in range(15, 95, 2):   # k 0.15 .. 0.94
                e = error(r10 / 10, k100 / 100, preset, stack)
                if best is None or e < best[0]:
                    best = (e, r10 / 10, k100 / 100, stack)
    e, r, k, stack = best
    print(f"best fit: radius={r}px  SIZE_TO_SIGMA={k}  stack={stack}  rms={e:.1f}")
    p = profile(r, k, preset, stack)
    print(f"\n{'r':>3} {'ref':>5} {'fit':>5} {'diff':>5}")
    for d in sorted(REF):
        print(f"{d:>3} {REF[d]:>5} {p[d]:>5} {p[d]-REF[d]:>+5}")
