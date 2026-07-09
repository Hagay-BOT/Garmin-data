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

# הגדרות 3 אימוני הכוח — מקור-אמת יחיד ב-athlete.py.
# (הגרסה הישנה כאן החזיקה A=Push הפוך — בדיוק ה-drift ש-athlete.py מחסל.)
import athlete
STRENGTH_WORKOUTS = {k: {"name": athlete.STRENGTH_NAMES[k], "minutes": athlete.STRENGTH_MINUTES,
                         "desc": athlete.STRENGTH_DESCS[k]} for k in ("A", "B", "C")}


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


# ── אימון ברמת-תרגיל (סטים/חזרות/מנוחה) מתוך strength_workouts.json ──────────────
from pathlib import Path
import re as _re

def _first_int(s, default=3):
    m = _re.search(r"\d+", str(s))
    return int(m.group()) if m else default

def _load_strength_db():
    db = json.loads((Path(__file__).parent / "strength_workouts.json").read_text(encoding="utf-8"))
    # M9.3: ולידציה רועשת — מאגר חסר/פגום היה נופל בשקט למשבצת-זמן בלי פירוט תרגילים.
    wos = db.get("workouts") or {}
    bad = [k for k in ("A", "B", "C")
           if not (wos.get(k, {}).get("name") and wos.get(k, {}).get("exercises"))]
    if bad:
        raise ValueError(f"strength_workouts.json — אימונים פגומים/חסרים: {bad} "
                         f"(חובה name + exercises לכל A/B/C)")
    return db

def build_reps_step(order: int, reps: int, name: str) -> dict:
    """צעד תרגיל יחיד — יעד חזרות, עם שם התרגיל כתיאור."""
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
        "endCondition": {"conditionTypeId": 10, "conditionTypeKey": "reps",
                         "displayOrder": 10, "displayable": True},
        "endConditionValue": float(reps),
        "description": name,
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target",
                       "displayOrder": 1},
    }

def build_rest_step(order: int, seconds: int) -> dict:
    """צעד מנוחה בין סטים — יעד זמן."""
    return {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": {"stepTypeId": 5, "stepTypeKey": "rest", "displayOrder": 5},
        "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time",
                         "displayOrder": 2, "displayable": True},
        "endConditionValue": float(seconds),
        "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target",
                       "displayOrder": 1},
    }

def build_strength_workout_full(key: str) -> dict:
    """בונה אימון כוח מלא ברמת-תרגיל: לכל תרגיל N סטים (חזרות + מנוחה).
    שמות התרגילים נכנסים כ-description לכל צעד (גם בלי קטלוג גרמין → ממוספר)."""
    db = _load_strength_db()
    wo = db["workouts"][key]
    steps, order = [], 1
    for ex in wo["exercises"]:
        sets = _first_int(ex.get("sets"), 3)
        reps = _first_int(ex.get("reps"), 10)
        rest = int(ex.get("rest_sec") or 90)
        name = ex["name"]
        for st in range(sets):
            steps.append(build_reps_step(order, reps, f"{name} (סט {st+1}/{sets})")); order += 1
            if st < sets - 1 or ex is not wo["exercises"][-1]:
                steps.append(build_rest_step(order, rest)); order += 1
    return {
        "workoutName": wo["name"],
        "description": f"{len(wo['exercises'])} תרגילים · {wo.get('duration_min',60)} דק'",
        "sportType": STRENGTH_SPORT,
        "estimatedDurationInSecs": int(wo.get("duration_min", 60) * 60),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": STRENGTH_SPORT,
            "workoutSteps": steps,
        }],
    }


# שיבוץ הכוח לשבוע 1 (לפי הסידור הנעול): {תאריך: מפתח אימון}
WEEK1_STRENGTH_SCHEDULE = {
    "2026-06-14": "B",   # ראשון
    "2026-06-16": "A",   # שלישי
    "2026-06-17": "C",   # רביעי
    "2026-06-18": "B",   # חמישי
    "2026-06-19": "A",   # שישי (קליל)
}


def login():
    # M9.2: דרך garmin_client — retry/backoff אחיד לכל הנתיבים.
    from garmin_client import login as _login
    return _login()


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

    # בניית אימון מלא ברמת-תרגיל — בלי חיבור (בדיקה מקומית)
    if "--build-one" in args:
        idx = args.index("--build-one")
        key = args[idx + 1] if len(args) > idx + 1 else "B"
        wo = build_strength_workout_full(key)
        print(f"=== {wo['workoutName']} — {len(wo['workoutSegments'][0]['workoutSteps'])} צעדים ===")
        print(json.dumps(wo, ensure_ascii=False, indent=2))
        return

    # דחיפת אימון בודד מלא ברמת-תרגיל + תזמון (דורש אישור! רץ ב-Actions)
    if "--push-one" in args:
        idx = args.index("--push-one")
        key = args[idx + 1] if len(args) > idx + 1 else "B"
        target = args[idx + 2] if len(args) > idx + 2 and not args[idx + 2].startswith("--") else date.today().isoformat()
        client = login()
        wo = build_strength_workout_full(key)
        nsteps = len(wo["workoutSegments"][0]["workoutSteps"])
        print(f"מעלה {key}: {wo['workoutName']} ({nsteps} צעדים) ל-{target}...")
        result = client.upload_workout(wo)
        wid = result.get("workoutId") or result.get("workoutid")
        client.schedule_workout(wid, target)
        print(f"✅ הועלה ותוזמן ל-{target}. מזהה: {wid}")
        print(f"למחיקה: python push_strength.py --cleanup {wid}")
        return

    print("בחר מצב: --build-only | --build-one <KEY> | --push-one <KEY> [date] | --schedule-week | --cleanup <id>")


if __name__ == "__main__":
    main()
