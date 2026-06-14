"""
שיבוץ אימוני כוח (Push/Pull/Legs) ללוח של גרמין — שיבוץ זמן בלבד.

הספרייה garminconnect לא מספקת בונה לאימוני כוח (רק סיבולת), לכן בונים JSON גולמי
עם sportType=strength_training ובלוק זמן יחיד, ומעלים דרך upload_workout(raw_json).
המטרה: שהשעון יציג "היום כוח A/B/C" כמשבצת בלוח — בלי פירוט תרגילים.

מצבי הרצה:
  python push_strength.py --build-only        → בונה ומדפיס JSON לכל A/B/C (בלי חיבור/סיסמה)
  python push_strength.py --schedule-week     → מעלה ומתזמן את כל אימוני הכוח לשבוע (דורש אישור!)
  python push_strength.py --cleanup <id>      → מוחק אימון לפי מזהה

סיסמה נקראת ממשתני סביבה GARMIN_EMAIL / GARMIN_PASSWORD (GitHub Secrets בלבד).
"""
import os
import sys
import json
from datetime import date

sys.stdout.reconfigure(encoding="utf-8")

# sportType של כוח בגרמין (לא קיים ב-enum של הספרייה — מוזן ידנית)
STRENGTH_SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}

# הגדרות 3 אימוני הכוח (פיצול PPL של הגיא)
STRENGTH_WORKOUTS = {
    "A": {"name": "💪 כוח A — Push (חזה/יד אחורית/כתפיים)", "minutes": 45,
          "desc": "Push: חזה, יד אחורית, כתפיים. פלג גוף עליון."},
    "B": {"name": "💪 כוח B — Pull (גב/יד קדמית)", "minutes": 45,
          "desc": "Pull: גב, יד קדמית. פלג גוף עליון."},
    "C": {"name": "🦵 כוח C — Legs (רגליים)", "minutes": 50,
          "desc": "רגליים: סקוואט, hip thrust, calf raises, חיזוק ברך/קרסול."},
}


def build_time_step(seconds: float, order: int = 1) -> dict:
    """צעד זמן יחיד, sport-agnostic — משבצת זמן ללא יעד."""
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time",
                         "displayOrder": 2, "displayable": True},
        "endConditionValue": seconds,
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target",
                       "displayOrder": 1},
    }


def build_strength_slot(key: str) -> dict:
    """בונה JSON גולמי לאימון כוח כמשבצת זמן בלוח."""
    w = STRENGTH_WORKOUTS[key]
    secs = float(w["minutes"] * 60)
    return {
        "workoutName": w["name"],
        "description": w["desc"],
        "sportType": STRENGTH_SPORT,
        "estimatedDurationInSecs": int(secs),
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": STRENGTH_SPORT,
                "workoutSteps": [build_time_step(secs, order=1)],
            }
        ],
    }


# שיבוץ הכוח לשבוע 1 (לפי הסידור הנעול): {תאריך: מפתח אימון}
WEEK1_STRENGTH_SCHEDULE = {
    "2026-06-15": "B",   # ראשון
    "2026-06-17": "A",   # שלישי
    "2026-06-18": "C",   # רביעי
    "2026-06-19": "B",   # חמישי
    "2026-06-20": "A",   # שישי (קליל)
}


def login():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("שגיאה: GARMIN_EMAIL / GARMIN_PASSWORD לא מוגדרים.")
        sys.exit(1)
    client = Garmin(email, password)
    client.login()
    print("✅ התחברות לגרמין הצליחה")
    return client


def main():
    args = sys.argv[1:]

    # מצב בנייה בלבד — בלי חיבור, בלי סיסמה, בלי דחיפה
    if "--build-only" in args:
        for key in ("A", "B", "C"):
            slot = build_strength_slot(key)
            print(f"=== כוח {key}: {slot['workoutName']} ===")
            print(json.dumps(slot, ensure_ascii=False, indent=2))
            print()
        print("✅ הבנייה תקינה. שיבוץ השבוע:")
        for d, k in WEEK1_STRENGTH_SCHEDULE.items():
            print(f"  {d} → כוח {k} ({STRENGTH_WORKOUTS[k]['name']})")
        return

    # מצב ניקוי
    if "--cleanup" in args:
        idx = args.index("--cleanup")
        workout_id = args[idx + 1]
        client = login()
        client.delete_workout(workout_id)
        print(f"🗑️  אימון {workout_id} נמחק.")
        return

    # מצב מלא — העלאה + תזמון לכל השבוע (דורש אישור מפורש מהמשתמש!)
    if "--schedule-week" in args:
        client = login()
        created = []
        for target_date, key in WEEK1_STRENGTH_SCHEDULE.items():
            slot = build_strength_slot(key)
            print(f"מעלה כוח {key} לתאריך {target_date}...")
            result = client.upload_workout(slot)
            wid = result.get("workoutId") or result.get("workoutid")
            client.schedule_workout(wid, target_date)
            created.append((target_date, key, wid))
            print(f"  ✅ תוזמן. מזהה: {wid}")
        print("\n🎯 כל אימוני הכוח שובצו בלוח גרמין:")
        for d, k, wid in created:
            print(f"  {d} → כוח {k} (id {wid})")
        print("\nלמחיקה: python push_strength.py --cleanup <id>")
        return

    print("בחר מצב: --build-only | --schedule-week | --cleanup <id>")


if __name__ == "__main__":
    main()
