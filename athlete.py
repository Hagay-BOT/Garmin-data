# -*- coding: utf-8 -*-
"""
athlete.py — מקור-אמת יחיד לקבועי המתאמן (M2.1).

כל מספר "של הגיא" חי כאן ורק כאן: זונות, קצבים, יעדים, קדנס, שמות פיצול הכוח.
קוד ופרומטים מייבאים מכאן — כך אי-אפשר שהם יסתרו (ה-drift שגרם ל-A/B הפוכים
ולקצב-Z2 שגוי בתוכנית). לשנות ערך = לשנות שורה אחת כאן.

עדכון ערכים: מותר ידנית או דרך שער ההערכה (VDOT gate, שבוע 4/8/12 במאקרו).
"""

# ── זהות ומרוץ ────────────────────────────────────────────────────────────────
NAME = "הגיא"
RACE = {"distance_km": 15, "goal_pace": "5:20", "date": "2026-09-20"}
GOAL_RACE_LABEL = f"{RACE['distance_km']}K @ {RACE['goal_pace']}"
LONG_TERM_PACE_GOAL = "4:10"     # יעד-העל (6–12 חודשים), לא יעד הבלוק

# ── דופק וזונות (Max HR נמדד; העדכון נכנס מ-data.json כשנשבר שיא) ─────────────
MAX_HR_FALLBACK = 201            # בשימוש רק אם data.json לא זמין
Z2_LOW, Z2_HIGH = 121, 141       # בסיס אירובי — הריצות הקלות נשלטות לפי זה
Z4_LOW, Z4_HIGH = 161, 181       # סף

# ── קצבים בפועל (נמדדו 06–07.2026) ──────────────────────────────────────────
EASY_PACE_RANGE = "6:45–7:00"    # קצב Z2 אמיתי לפי דופק — לא לתכנן מהיר מזה
THRESHOLD_PACE = "4:50"          # סף נוכחי (יכויל ב-5K Time Trial, שבוע 4)
STRIDES_PACE_RANGE = "3:50–4:10"

# ── טכניקת ריצה — יעדים ──────────────────────────────────────────────────────
CADENCE_TARGET = 180             # spm — היעד
CADENCE_MIN_OK = 175             # מתחת לזה = דגש שיפור
VERTICAL_RATIO_MAX = 8.0         # % — מעל = "קופץ" במקום לגלוש
GCT_MAX_MS = 250                 # ms — פגיעה בקרקע

# ── מבנה שבוע (הכללים של הגיא, "עושה סדר" 22.06) ────────────────────────────
WEEK_ANCHOR = "sunday"           # השבוע = ראשון–שבת, בכל המערכת
LONG_RUN_CAP_KM = 12             # תקרת ברך/קרסול עד שיפור

# ── פיצול כוח (PPL) — השמות הרשמיים, מקור-אמת יחיד ───────────────────────────
STRENGTH_NAMES = {
    "A": "💪 כוח A — Pull/משיכה (גב/יד קדמית)",
    "B": "💪 כוח B — Push/דחיפה (חזה/כתפיים/יד אחורית)",
    "C": "🦵 כוח C — Legs (רגליים)",
}
STRENGTH_DESCS = {
    "A": "Pull: גב, יד קדמית.",
    "B": "Push: חזה, כתפיים, יד אחורית.",
    "C": "רגליים: סקוואט, hip thrust, calf raises, חיזוק ברך/קרסול.",
}
STRENGTH_MINUTES = 60


def week_start(d=None):
    """תחילת שבוע-האימון (ראשון) עבור תאריך נתון — העוגן היחיד במערכת (M9.4).
    כל חישוב-שבוע בפייתון עובר כאן; המקבילה ב-JS (index.html weekBounds) מתועדת
    ב-ENGINEERING_DECISIONS ומוצמדת לאותה סמנטיקה: ראשון–שבת."""
    import datetime as _dt
    d = d or _dt.date.today()
    return d - _dt.timedelta(days=(d.weekday() + 1) % 7)


def week_start_iso(d=None) -> str:
    return week_start(d).isoformat()


def zone_of(hr: float, max_hr: float | None = None) -> int:
    """זון 1–5 לפי דופק, על גבולות הזונות של הגיא."""
    if not hr:
        return 0
    if hr < Z2_LOW:
        return 1
    if hr <= Z2_HIGH:
        return 2
    if hr < Z4_LOW:
        return 3
    if hr <= Z4_HIGH:
        return 4
    return 5
