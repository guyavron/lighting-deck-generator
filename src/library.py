"""מאגר התצלומים — חיתוך תגיות, לא מסלול בעץ.

הטקסונומיה של המשרד מערבבת צירים בכוונה: "שקועים" הוא סוג התקנה,
"אי מטבח" הוא מיקום, "אווירה" היא כוונה. אי אפשר ליישר את זה לעץ בלי
לקבל משהו שנכון לוגית ולא מתאים לאף אחד. לכן כל תגית עומדת בפני
עצמה, והניווט הוא חיתוך.

שני עקרונות שמכתיבים את הקוד כאן:

1. מתחילים ממה שהשרטוט יודע. גוף שהוא בלוק SH על שכבת light up כבר
   מזוהה — אין טעם לשאול "איזה סוג התקנה". יותר מזה: קוד סוג (SH, SP,
   WA, TA) מסמן גוף טכני שאמור להיעלם, ושם מוצר (TACCIA, NULLA) מסמן
   גוף דקורטיבי שאמור להיראות. זו הבחנה שנקראת מהשרטוט, לא נשאלת.

2. שבב שלא מפצל לא מוצג. שאלה שהתשובה שלה כמעט קבועה מרגישה מועילה
   ומבזבזת צעד. הכלל ב-asset_facets.yaml מחושב על התוצאות שעל המסך
   כרגע, ולכן שבבים מופיעים ונעלמים תוך כדי צמצום.
"""
from __future__ import annotations

import csv
import datetime
import functools
import io
import os
import re

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
KNOWLEDGE = os.path.join(ROOT, "knowledge")

ASSETS = os.path.join(KNOWLEDGE, "assets.csv")
FACETS = os.path.join(KNOWLEDGE, "asset_facets.yaml")
CRITERIA = os.path.join(KNOWLEDGE, "asset_criteria.yaml")
ASSET_TAGS = os.path.join(KNOWLEDGE, "asset_tags.csv")
CHOICES = os.path.join(KNOWLEDGE, "asset_choices.csv")
HIDDEN = os.path.join(KNOWLEDGE, "asset_hidden.csv")

HIDDEN_COLS = ["asset_id", "hidden_by", "hidden_at", "reason"]

# השם שנרשם כשהמערכת מתייגת. לעולם לא שם של אדם — זו ההבחנה
# היחידה בין "תויג" לבין "נבדק".
AUTO_REVIEWER = "תיוג אוטומטי"

CHOICE_COLS = ["category", "asset_id", "tags", "chosen_at", "source"]

SPLIT = re.compile("[/|,]")


@functools.lru_cache(maxsize=1)
def facets():
    with io.open(FACETS, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@functools.lru_cache(maxsize=1)
def criteria():
    """אוצר המילים שנבחר, להבדיל מהתגיות שנצפו ב-PSD.

    asset_facets.yaml הוא ראיה; זה החלטה. שניהם מוצגים כשבבים
    באותו אופן, ושניהם כפופים לאותו כלל — ציר שאינו מפצל אינו מוצג.
    ציר שעדיין לא תויג פשוט אינו מפצל, ולכן נעלם מעצמו.
    """
    with io.open(CRITERIA, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@functools.lru_cache(maxsize=1)
def asset_tags():
    if not os.path.exists(ASSET_TAGS):
        return {}
    with io.open(ASSET_TAGS, encoding="utf-8-sig") as fh:
        return {r["asset_id"]: r for r in csv.DictReader(fh)}


@functools.lru_cache(maxsize=1)
def hidden():
    """תמונות שהוסתרו בסקירה.

    הסתרה היא מוצא אחרון, אחרי שתיקון התגיות ותיקון החיתוך לא עזרו.
    **הקובץ נשאר על הדיסק** — הכלי אינו מוחק (חוק ברזל 3), והחזרה
    היא מחיקת שורה אחת מכאן.
    """
    if not os.path.exists(HIDDEN):
        return {}
    with io.open(HIDDEN, encoding="utf-8-sig") as fh:
        return {r["asset_id"]: r for r in csv.DictReader(fh)
                if (r.get("asset_id") or "").strip()}


def image_path(asset_id):
    """הקובץ שמגישים: הגזור אם קיים, אחרת המקור.

    המקור לעולם אינו נדרס (חוק ברזל 2). החיתוך הוא קובץ נפרד
    שנוצר מחדש מ-`asset_crops.csv`, ומחיקת השורה שם מחזירה
    את התמונה המלאה.
    """
    crop = os.path.join(ROOT, "library", "crops", asset_id + ".png")
    if os.path.exists(crop):
        return crop
    return os.path.join(ROOT, "library", asset_id + ".png")


def set_hidden(asset_id, on, by="", reason=""):
    import datetime
    rows = [r for r in hidden().values() if r["asset_id"] != asset_id]
    if on:
        rows.append({"asset_id": asset_id, "hidden_by": by,
                     "hidden_at": datetime.datetime.now()
                     .strftime("%Y-%m-%d %H:%M:%S"), "reason": reason})
    with io.open(HIDDEN, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, HIDDEN_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in HIDDEN_COLS})
    hidden.cache_clear()
    load.cache_clear()


@functools.lru_cache(maxsize=1)
def technical_codes():
    """קודי הסוג מ-taxonomy.yaml. כל שם אחר על גוף הוא שם מוצר."""
    import taxonomy as TX
    codes = set()
    for t in TX.load()["lighting_types"]:
        for c in t.get("dxf_blocks", []) or []:
            codes.add(c.upper())
    return codes


def is_decorative(code):
    """גוף דקורטיבי נושא שם מוצר; טכני נושא קוד סוג.

    זו התשובה של השרטוט על "להיראות או להיעלם", ולכן אינה נשאלת.
    """
    c = (code or "").strip().upper()
    return bool(c) and c not in technical_codes()


def split_tags(context):
    out = []
    for part in SPLIT.split(context or ""):
        t = part.strip()
        if t and t not in out:
            out.append(t)
    return out


@functools.lru_cache(maxsize=1)
def load():
    """כל הנכסים, עם תגיות מפורקות ומקובצות לצירים."""
    cfg = facets()
    noise = set(cfg.get("noise") or [])
    by_tag = {}
    for key, f in cfg["facets"].items():
        for t in f["tags"]:
            by_tag[t] = key

    crit = criteria()["criteria"]
    tagmap = asset_tags()
    hide = hidden()

    rows = []
    if not os.path.exists(ASSETS):
        return rows
    with io.open(ASSETS, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            tags = [t for t in split_tags(r.get("context")) if t not in noise]
            a = dict(r)
            a["tags"] = tags
            a["facet_tags"] = {k: [t for t in tags if by_tag.get(t) == k]
                               for k in cfg["facets"]}
            # תגיות שלא מצאו ציר — נשמרות ומוצגות תחת "אחר", כדי שתגית
            # חדשה לא תיעלם בשקט רק מפני שהיא לא ברשימה
            a["loose_tags"] = [t for t in tags if t not in by_tag]
            try:
                a["n_projects"] = int(r.get("n_projects") or 1)
            except ValueError:
                a["n_projects"] = 1
            a["is_product"] = (r.get("kind") == "product")
            a["is_studio"] = (r.get("kind") == "studio_photo")

            # קריטריונים שתויגו. ערכיהם נכנסים לאותו סל תגיות, כך
            # שהחיתוך אחיד ואין שני מנגנוני סינון שיוצאים מסנכרון.
            t = tagmap.get(a["asset_id"], {})
            a["crit_tags"] = {}
            for key in crit:
                vals = [v.strip() for v in (t.get(key) or "").split("|")
                        if v.strip()]
                a["crit_tags"][key] = vals
                for v in vals:
                    if v not in a["tags"]:
                        a["tags"].append(v)
            a["reviewed"] = bool((t.get("reviewed") or "").strip())
            a["reviewed_by"] = t.get("reviewed_by") or ""
            # אישור אוטומטי אינו אישור. הבנק נראה מלא, אבל מי שסוקר
            # אותו חייב לדעת מה עדיין לא עברה עליו עין אנושית.
            a["by_human"] = (a["reviewed"] and
                             a["reviewed_by"] != AUTO_REVIEWER)
            a["reviewed_at"] = t.get("reviewed_at") or ""
            a["hidden"] = a["asset_id"] in hide
            rows.append(a)
    return rows


# ─── בחירות שנזכרות ───────────────────────────────────────────────

def _choice_rows():
    if not os.path.exists(CHOICES):
        return []
    with io.open(CHOICES, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def preferred(category):
    """מזהי הנכסים שכבר נבחרו לקטגוריה הזו, מהאחרון לראשון.

    זה מה שמצמצם את זמן החיפוש לאורך זמן: תצלום שנבחר פעם אחת
    לא מחופש שוב.
    """
    out = []
    for r in _choice_rows():
        aid = (r.get("asset_id") or "").strip()
        if r.get("category") == category and aid:
            if aid in out:
                out.remove(aid)
            out.insert(0, aid)
    return out


def record_choice(category, asset_id, tags=(), source="library"):
    exists = os.path.exists(CHOICES)
    with io.open(CHOICES, "a", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        if not exists:
            w.writerow(CHOICE_COLS)
        w.writerow([category or "", asset_id, " / ".join(tags),
                    datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    source])


# ─── חיפוש ───────────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def install_for_category():
    """קטגוריה -> סוג התקנה.

    משמשת לשאילתת החיפוש באינטרנט, ומאז D-048 גם לסימון אוטומטי של
    שבב סוג ההתקנה לפי מה שדולק בשקופית (`auto_install`). הסימון
    הוא **הצעה שמסומנת** — העובד רואה אותו ויכול להוריד אותו — והציר
    רך, כך שתצלום שעוד לא תויג אינו נעלם.
    """
    return criteria().get("derive_install_from_category") or {}


def auto_install(categories):
    """סוגי ההתקנה של הקטגוריות שדולקות בשקופית, בלי כפילויות.

    קטגוריה בלי מיפוי חד-משמעי ("ספוטים", "מערכת") לא תורמת כלום —
    עדיף שבב לא מסומן מאשר שבב שגוי.
    """
    m = install_for_category()
    out = []
    for c in categories:
        v = m.get(c)
        if v and v not in out:
            out.append(v)
    return out


def search(tags=(), rooms=(), text="", category=None, limit=2000):
    """נכסים מדורגים לפי מה שהעובד סינן.

    `tags`     ערכי הקריטריונים שנבחרו — חיתוך בין צירים. בציר רך
               (סוג התקנה, D-048) איחוד, ומה שלא תויג עובר עם `untagged`
    `rooms`    חללים שנבחרו. **מקדמים בסדר התצוגה ולעולם לא מסתירים.**
    `text`     חיפוש חופשי בשם, ביצרן ובתגיות
    `category` קטגוריית השקופית — משמשת **רק** לזיכרון בחירות קודמות

    השרטוט לא מסנן, ולא מדרג, ולא מניח. גיא: "אני רוצה שהעובד יסנן
    לפי מה שהוא רוצה." קודם הפאנל נפתח "מסונן לפי שקוע בתקרה
    מהשרטוט" — ניחוש שהעובד לא ביקש והסתיר ממנו את רוב הספריה.

    היחיד ששרד מהעבר הוא `category`, ורק כדי להעלות למעלה תצלום
    שכבר נבחר פעם לאותה קטגוריה. זו בחירה של אדם, לא הנחה.

    **D-048 החזיר את השרטוט — אבל לא לכאן.** הסימון האוטומטי קורה
    בשרת (`photos_search`, `auto_install`) ומגיע לכאן כתגית רגילה
    שהעובד רואה דולקת. הפונקציה הזו עדיין לא מנחשת דבר בעצמה.
    """
    want = [t for t in tags if t]
    want_rooms = {r for r in rooms if r}
    q = (text or "").strip().lower()
    pref = preferred(category) if category else []
    # צירים "רכים" (D-048): ערך שנבחר בהם הוא איחוד, ותצלום שעוד לא
    # תויג בציר עובר — מתחת לקו. רק תיוג **אחר** מסתיר.
    soft = {}
    for key, f in criteria()["criteria"].items():
        if f.get("soft"):
            mine = [t for t in want if t in f["values"]]
            if mine:
                soft[key] = set(mine)
    soft_vals = set().union(*soft.values()) if soft else set()
    hard = [t for t in want if t not in soft_vals]

    scored = []
    for a in load():
        if a.get("hidden"):
            continue          # מוסתר מהחיפוש, קיים בסקירה ועל הדיסק
        if hard and not all(t in a["tags"] for t in hard):
            continue
        untagged = False
        skip = False
        for key, vals in soft.items():
            have = a["crit_tags"].get(key, [])
            if not have:
                untagged = True
            elif not vals & set(have):
                skip = True
        if skip:
            continue
        if q:
            hay = [a["name"].lower(), (a.get("manufacturer") or "").lower()]
            hay += [t.lower() for t in a["tags"]]
            if not any(q in h for h in hay):
                continue

        score = 0.0
        if a["asset_id"] in pref:
            score += 100 - pref.index(a["asset_id"])   # נבחר כבר — ראשון
        if want_rooms & set(a["crit_tags"].get("room", [])):
            score += 25              # קידום בלבד. חלל לעולם לא מסתיר.
        score += min(a["n_projects"], 4) * 3           # חזר בין פרויקטים
        if a.get("manufacturer"):
            score += 2
        if untagged:
            a = dict(a, untagged=True)
        scored.append((score, a["name"], a))

    # מה שמתויג למה שביקשו — קודם. מה שעוד לא תויג — אחריו.
    scored.sort(key=lambda p: (bool(p[2].get("untagged")), -p[0], p[1]))
    return [a for _, _, a in scored[:limit]]


def filter_spec(active_tags=(), active_rooms=()):
    """אוצר המילים המלא, תמיד — אבל הספירות על מה שנשאר.

    קודם כל ערך נשא את הספירה שלו בכל הבנק, ולכן "מודרני 145" נשאר
    145 גם אחרי שסיננת ל"שקוע בתקרה". העובד היה ממלא את הסינון,
    יורד למטה, ומגלה שאין אף תמונה. **הספירה חייבת לענות על
    "כמה יישארו אם אלחץ על זה"**, ולכן היא מחושבת על התוצאות
    הנוכחיות ולא על הבנק.

    לציר שכבר נבחר בו ערך, הספירה מחושבת **בלי** הבחירה שלו עצמו —
    אחרת כל שאר הערכים באותו ציר היו מראים אפס, ואי אפשר היה
    להחליף בחירה בלחיצה אחת.

    אפס עדיין מוצג. הוא אומר "אין כזה בשילוב הנוכחי", וזו תשובה.
    """
    crit = criteria()["criteria"]
    active = [t for t in active_tags if t]
    rooms = [r for r in active_rooms if r]

    out = []
    for key, f in crit.items():
        filters = f.get("filter") is not False
        # מבטלים את הציר הנוכחי מהסינון לצורך הספירה שלו
        others = [t for t in active
                  if t not in f["values"]] if filters else active
        base = search(tags=others, rooms=rooms)
        counts = {}
        for a in base:
            for v in a["crit_tags"].get(key, []):
                counts[v] = counts.get(v, 0) + 1
        out.append({
            "facet": key,
            "label": f["label"],
            "multi": bool(f.get("multi")),
            "filters": filters,
            "tagged": sum(counts.values()),
            "values": [{"tag": v, "n": counts.get(v, 0),
                        "on": (v in rooms) if not filters else (v in active)}
                       for v in f["values"]],
        })
    return out


def search_query(tags=(), rooms=(), category=None):
    """שאילתה באנגלית לחיפוש באינטרנט, מהשבבים שנבחרו.

    מורכבת בסדר שמחפשים בו בפועל: מה הגוף, אחר כך איך הוא נראה,
    ולבסוף איפה. "lighting" בסוף כדי שגוגל לא יחזיר רהיטים.

    באנגלית, כי אתרי היצרנים והתוצאות הטובות באנגלית — חיפוש
    בעברית מחזיר חנויות מקומיות.
    """
    en = criteria().get("search_terms_en") or {}
    crit = criteria()["criteria"]
    order = ("install", "finish", "style", "beam", "cct", "room")
    chosen = list(tags) + list(rooms)
    if category:
        inst = install_for_category().get(category)
        if inst and inst not in chosen:
            chosen.append(inst)

    parts, seen = [], set()
    for key in order:
        for v in crit.get(key, {}).get("values", []):
            if v in chosen:
                t = en.get(v)
                if t and t not in seen:
                    seen.add(t)
                    parts.append(t)
    if not parts:
        return ""
    return " ".join(parts) + " lighting"
