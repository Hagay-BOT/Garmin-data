"""
דחיפת תוכנית השבוע המלאה (ריצות + כוח) ללוח של גרמין.
קורא את week_plan.json — מקור-אמת יחיד — ובונה אימון לכל סשן.

מצבי הרצה:
  python push_week.py --build-only     → בונה ומדפיס הכל (בלי חיבור/סיסמה/דחיפה)
  python push_week.py --push           → מעלה ומתזמן את כל השבוע (דורש אישור + Secrets)
  python push_week.py --cleanup        → מוחק את כל האימונים שנוצרו (לפי created_workouts.json)

סיסמה: GARMIN_EMAIL / GARMIN_PASSWORD ממשתני סביבה (GitHub Secrets בלבד).
הדחיפה רצה דרך GitHub Actions בלבד — לא מקומית.
"""
import os
import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from garminconnect.workout import (
    RunningWorkout,
    WorkoutSegment,
    create_warmup_step,
    create_interval_step,
    create_cooldown_step,
)

BASE = Path(__file__).parent
PLAN_FILE = BASE / "week_plan.json"
CREATED_FILE = BASE / "created_workouts.json"

STRENGTH_SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
STRENGTH_DEFS = {
    "A": {"name": "💪 כוח A — Push (חזה/יד אחורית/כתפיים)", "minutes": 45,
          "desc": "Push: חזה, יד אחורית, כתפיים. פלג גוף עליון."},
    "B": {"name": "💪 כוח B — Pull (גב/יד קדמית)", "minutes": 45,
          "desc": "Pull: גב, יד קדמית. פלג גוף עליון."},
    "C": {"name": "🦵 כוח C — Legs (רגליים)", "minutes": 50,
          "desc": "רגליים: סקוואט, hip thrust, calf raises, חיזוק ברך/קרסול."},
}

STEP_BUILDERS = {
    "warmup": create_warmup_step,
    "interval": create_interval_step,
    "cooldown": create_cooldown_step,
}


def load_plan() -> dict:
    return json.loads(PLAN_FILE.read_text(encoding="utf-8"))


def build_run(session: dict) -> RunningWorkout:
    """בונה RunningWorkout מובנה (נתיב מוכח) מהצעדים שב-week_plan.json."""
    steps = []
    total = 0
    for i, st in enumerate(session["steps"], start=1):
        builder = STEP_BUILDERS[st["kind"]]
        secs = float(st["seconds"])
        total += secs
        # warmup builder uses step_order kw default; pass positionally where needed
        if st["kind"] == "warmup":
            steps.append(builder(secs, step_order=i))
        else:
            steps.append(builder(secs, step_order=i))
    return RunningWorkout(
        workoutName=session["name"],
        estimatedDurationInSecs=int(total),
        description=session.get("desc", ""),
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                workoutSteps=steps,
            )
        ],
    )


def build_strength(key: str) -> dict:
    d = STRENGTH_DEFS[key]
    secs = float(d["minutes"] * 60)
    return {
        "workoutName": d["name"],
        "description": d["desc"],
        "sportType": STRENGTH_SPORT,
        "estimatedDurationInSecs": int(secs),
        "workoutSegments": [{
            "segmentOrder": 1,
            "sportType": STRENGTH_SPORT,
            "workoutSteps": [{
                "type": "ExecutableStepDTO", "stepOrder": 1,
                "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time",
                                 "displayOrder": 2, "displayable": True},
                "endConditionValue": secs,
                "targetType": {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target",
                               "displayOrder": 1},
            }],
        }],
    }


def login():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("שגיאה: GARMIN_EMAIL / GARMIN_PASSWORD לא מוגדרים (Secrets).")
        sys.exit(1)
    client = Garmin(email, password)
    client.login()
    print("✅ התחברות לגרמין הצליחה")
    return client


def main():
    args = sys.argv[1:]
    plan = load_plan()
    sessions = plan["sessions"]

    if "--build-only" in args:
        print(f"=== תוכנית שבוע {plan['week_of']} · {plan['phase']} (שבוע {plan['macro_week']}) ===\n")
        for s in sessions:
            if s["type"] == "run":
                wk = build_run(s)
                mins = wk.estimatedDurationInSecs // 60
                print(f"{s['date']} ({s['day']}) · ריצה · {s['name']} · ~{mins} דק' · {len(s['steps'])} צעדים")
            else:
                d = STRENGTH_DEFS[s["key"]]
                print(f"{s['date']} ({s['day']}) · כוח · {d['name']} · {d['minutes']} דק'")
        runs = sum(1 for s in sessions if s["type"] == "run")
        strength = sum(1 for s in sessions if s["type"] == "strength")
        km = sum(s.get("est_km", 0) for s in sessions if s["type"] == "run")
        print(f"\nסה\"כ: {runs} ריצות ({km} ק\"מ) · {strength} אימוני כוח")
        print("✅ הבנייה תקינה.")
        return

    if "--cleanup" in args:
        if not CREATED_FILE.exists():
            print("אין created_workouts.json — אין מה למחוק.")
            return
        ids = json.loads(CREATED_FILE.read_text(encoding="utf-8"))
        client = login()
        for item in ids:
            try:
                client.delete_workout(item["workout_id"])
                print(f"🗑️  נמחק {item['workout_id']} ({item['name']})")
            except Exception as e:
                print(f"⚠️  כשל במחיקת {item['workout_id']}: {e}")
        CREATED_FILE.unlink(missing_ok=True)
        return

    if "--push" in args:
        client = login()
        created = []
        for s in sessions:
            if s["type"] == "run":
                wk = build_run(s)
                res = client.upload_running_workout(wk)
                name = s["name"]
            else:
                slot = build_strength(s["key"])
                res = client.upload_workout(slot)
                name = STRENGTH_DEFS[s["key"]]["name"]
            wid = res.get("workoutId") or res.get("workoutid")
            client.schedule_workout(wid, s["date"])
            created.append({"date": s["date"], "name": name, "workout_id": wid})
            print(f"✅ {s['date']} · {name} · id {wid}")
        CREATED_FILE.write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n🎯 כל {len(created)} האימונים שובצו בלוח גרמין.")
        print("בדוק: Garmin Connect → Calendar → שבוע 14–20.06")
        print("למחיקה: python push_week.py --cleanup")
        return

    print("בחר מצב: --build-only | --push | --cleanup")


if __name__ == "__main__":
    main()
