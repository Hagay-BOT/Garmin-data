# שלד המשוב — מסגרת 3 הלולאות

> ספק זה מגדיר **איך** המאמן נותן משוב ומתאים את התוכנית. coach.py קורא קובץ זה ומייצר פלט לפי המבנה כאן.
> שלוש לולאות בקצב שונה — כל אחת עם trigger, input, ו-output מוגדרים.

---

## עקרון העל: חיבור מיקרו ↔ מאקרו

כל פלט של כל לולאה **חייב להתייחס למיקום במאקרו**:
- באיזה שבוע מתוך 14 אנחנו?
- באיזו פאזה? (Base / Build / Peak / Taper)
- מה המטרה של הפאזה הזו?

אימון בודד לא נשפט בפני עצמו — הוא נשפט מול **מה שהפאזה דורשת**.

---

## לולאה 1 — בוקר יומי (Morning Readiness)

**Trigger:** כל בוקר, לפני האימון. אוטומטי.
**Input:**
- מוכנות בוקר מ-Garmin: שינה, HRV, Body Battery, RHR (resting HR)
- האימון המתוכנן להיום (מהתוכנית השבועית המאושרת)
- העומס המצטבר (ATL/TSB)

**Output — `morning_adjustment`:**
```json
{
  "date": "YYYY-MM-DD",
  "readiness_score": 0-100,
  "readiness_level": "ירוק | צהוב | אדום",
  "planned_workout": "<מה שתוכנן>",
  "adjusted_workout": "<מה שיבוצע בפועל>",
  "adjustment_type": "none | easier | shorter | rest",
  "reason": "<הסבר קצר>",
  "auto_pushed": true/false
}
```

**חוקי התאמה (רק להקל, אף פעם לא להחמיר):**
| מוכנות | פעולה |
|--------|-------|
| 🟢 ירוק (>70) | אין שינוי — בצע כמתוכנן |
| 🟡 צהוב (50–70) | אם היום איכות → הורד עצימות / קצר ב-20% |
| 🔴 אדום (<50) | החלף ל-Z2 קל או מנוחה מלאה |

**גבול בטיחות:** רשאי רק להוריד עומס. לעולם לא להוסיף. דחיפה אוטומטית רק במעטפת המאושרת.

---

## לולאה 2 — אחרי אימון (Post-Workout Analysis)

**Trigger:** צהריים/ערב, אחרי שהאימון סונכרן ל-Garmin.
**Input:**
- האימון שבוצע (distance, pace, HR zones, splits, duration)
- האימון שתוכנן (מה היה אמור לקרות)
- ההיסטוריה (4 שבועות אחרונים)

**Output — `post_workout_feedback`:** שלושה חלקים:

### חלק א' — משוב מפורט (`detailed_feedback`)
```json
{
  "executed_vs_planned": {
    "distance_km":   {"planned": X, "actual": Y, "delta_pct": Z},
    "avg_pace":      {"planned": "m:ss", "actual": "m:ss", "delta_sec": Z},
    "target_zone":   {"planned": "Z4", "actual_pct_in_zone": 78},
    "duration_min":  {"planned": X, "actual": Y}
  },
  "compliance_score": 0-100,
  "execution_quality": {
    "hit_target_pace": true/false,
    "hr_drift_bpm": X,
    "split_consistency": "טוב | בינוני | משתנה",
    "pacing_pattern": "negative | even | positive"
  },
  "what_went_well": ["<...>"],
  "what_to_improve": ["<...>"],
  "macro_context": "שבוע X/14, פאזת <name> — האימון <תרם/לא תרם> למטרת הפאזה"
}
```

### חלק ב' — אדפטציה לאימון מחר (`tomorrow_adaptation`)
```json
{
  "tomorrow_planned": "<מה שתוכנן למחר>",
  "recommended_change": "none | easier | harder | swap | rest",
  "adjusted_tomorrow": "<אימון מותאם>",
  "reason": "<בהינתן עומס היום + ATL>"
}
```
**לוגיקה:**
- היום היה קשה מהצפוי (HR גבוה, או לא עמד בקצב) → מחר קל יותר
- היום הוחמץ/קוצר משמעותית → מחר משלים חלקית (לא 100%)
- היום היה קל מהצפוי והרגשה טובה → מחר אפשר כמתוכנן (לא להוסיף!)

### חלק ג' — דגלים אדומים (`red_flags`) 🚩
רשימת התראות שדורשות תשומת לב מיידית:
```json
[
  {
    "flag": "<סוג>",
    "severity": "🔴 קריטי | 🟡 אזהרה",
    "detail": "<מה זוהה>",
    "action": "<מה לעשות>"
  }
]
```
**דגלים שצריך לזהות:**
| דגל | תנאי | חומרה |
|-----|------|-------|
| דופק מנותק מקצב | HR גבוה ב->10 bpm בקצב Z2 רגיל | 🔴 |
| Cardiac drift חריג | drift > 8% בריצת Z2 | 🟡 |
| ACWR spike | ACWR > 1.5 | 🔴 |
| כאב מדווח | המשתמש דיווח כאב ברך/קרסול | 🔴 |
| נפילת ביצועים | קצב ירד >10% מהממוצע ללא סיבה | 🟡 |
| Recovery לקוי | RHR בוקר גבוה מהרגיל יומיים ברצף | 🟡 |
| נפח קופץ | עלייה >10% נפח שבועי | 🟡 |

**כלל מיוחד להגיא:** כל כאב ברך/קרסול אחרי ריצה 10+ ק"מ = 🔴 → long run הבא מוגבל / מוחלף.

---

## לולאה 3 — שבועית (Weekly Review)

**Trigger:** סוף שבוע, אחרי כל האימונים. פעם בשבוע.
**Input:**
- כל האימונים של השבוע שעבר
- הכושר הנמדד מ-4 שבועות אחרונים (לא אימון בודד!)
- כל ה-`post_workout_feedback` של השבוע
- המיקום במאקרו

**Output — `weekly_review`:**
```json
{
  "week_number": "X/14",
  "phase": "Base | Build | Peak | Taper",
  "fitness_assessment": {
    "vdot_4week": X,
    "ctl": X, "atl": X, "tsb": X, "acwr": X,
    "weekly_km": X,
    "trend": "עולה | יציב | יורד",
    "vs_macro_expectation": "מקדים | בקצב | מפגר"
  },
  "week_summary": {
    "planned_sessions": X,
    "completed_sessions": Y,
    "compliance_pct": Z,
    "total_load": X,
    "highlights": ["<...>"],
    "concerns": ["<...>"]
  },
  "next_week_plan": "<תוכנית השבוע הבא — נגזרת מהמאקרו + ביצועי השבוע>",
  "macro_adjustment": "<אם צריך לעדכן את המאקרו — כל 4 שבועות הערכה מחדש>",
  "requires_approval": true
}
```

**חיבור למאקרו:** השבוע הבא **תמיד** נגזר מ-(שלב הפאזה) × (ביצועי השבוע שעבר). אם פיגרת — מאריכים את הפאזה. אם מקדים — מאיצים. הערכה מלאה של המאקרו כל 4 שבועות.

---

## סיכום קצבים

| לולאה | תדירות | אוטומטי? | דורש אישור? |
|-------|---------|----------|-------------|
| בוקר (מוכנות) | יומי, בוקר | ✅ כן | ❌ לא (במעטפת מאושרת, רק הקלה) |
| אחרי אימון | יומי, צה'/ערב | ✅ כן | ❌ לא (ניתוח בלבד, לא דוחף) |
| שבועי | שבועי | חצי | ✅ כן (תוכנית חדשה = שער אישור) |
