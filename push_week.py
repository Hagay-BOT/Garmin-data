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
    "A": {"name": "💪 כוח A — Pull/משיכה (גב/יד קדמית)", "minutes": 60,
          "desc": "Pull: גב, יד קדמית. פלג גוף עליון."},
    "B": {"name": "💪 כוח B — Push/דחיפה (חזה/כתפיים/יד אחורית)", "minutes": 60,
          "desc": "Push: חזה, כתפיים, יד אחורית. פלג גוף עליון."},
    "C": {"name": "🦵 כוח C — Legs (רגליים)", "minutes": 60,
          "desc": "רגליים: סקוואט, hip thrust, calf raises, חיזוק ברך/קרסול."},
}

STEP_BUILDERS = {
    "warmup": create_warmup_step,
    "interval": create_interval_step,
    "cooldown": create_cooldown_step,
}


def load_plan() -> dict:
    if not PLAN_FILE.exists():
        print("שגיאה: week_plan.json לא קיים — אין תוכנית לדחוף.")
        sys.exit(1)
    try:
        return json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"שגיאה: week_plan.json פגום ({e}).")
        sys.exit(1)


VALID_STEP_KINDS = {"warmup", "interval", "cooldown"}
MAX_TOTAL_SECONDS = 4 * 3600
MIN_TOTAL_SECONDS = 5 * 60


def validate_workout(session: dict) -> None:
    """ולידציה אחרונה לפני העלאה לגרמין. זורק ValueError עם התאריך הבעייתי."""
    d = session.get("date", "?")
    if session.get("type") == "strength":
        if session.get("key") not in STRENGTH_DEFS:
            raise ValueError(f"{d}: מפתח כוח לא תקין '{session.get('key')}'")
        return
    steps = session.get("steps") or []
    if not steps:
        raise ValueError(f"{d}: ריצה ללא steps")
    total = 0
    for st in steps:
        if st.get("kind") not in VALID_STEP_KINDS:
            raise ValueError(f"{d}: סוג step לא מוכר '{st.get('kind')}'")
        secs = float(st.get("seconds") or 0)
        if secs <= 0:
            raise ValueError(f"{d}: step עם משך לא חיובי")
        total += secs
    if not (MIN_TOTAL_SECONDS <= total <= MAX_TOTAL_SECONDS):
        raise ValueError(f"{d}: משך כולל לא סביר ({int(total)} שנ')")


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
    """אימון כוח ברמת-תרגיל (סטים · חזרות · מנוחה) מ-strength_workouts.json —
    אותו builder שנבדק ועבד בשעון. נופל חזרה למשבצת-זמן אם ה-DB חסר/שבור,
    כדי שתקלה במאגר לא תפיל את כל האישור השבועי."""
    try:
        import push_strength
        wo = push_strength.build_strength_workout_full(key)
        if wo.get("workoutSegments", [{}])[0].get("workoutSteps"):
            return wo
    except Exception as e:
        print(f"⚠️ build_strength ברמת-תרגיל נכשל ({e}) — נופל למשבצת-זמן.")

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
    try:
        from garminconnect import (
            GarminConnectAuthenticationError,
            GarminConnectConnectionError,
        )
    except Exception:  # pragma: no cover - older lib without named errors
        GarminConnectAuthenticationError = GarminConnectConnectionError = Exception
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("שגיאה: GARMIN_EMAIL / GARMIN_PASSWORD לא מוגדרים (Secrets).")
        sys.exit(1)
    try:
        client = Garmin(email, password)
        client.login()
    except GarminConnectAuthenticationError as e:
        print(f"שגיאה: אימות גרמין נכשל — {e}")
        sys.exit(1)
    except GarminConnectConnectionError as e:
        print(f"שגיאה: חיבור לגרמין נכשל — {e}")
        sys.exit(1)
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
        force = "--force" in args
        # ── שער אישור: לא דוחפים תוכנית שלא אושרה במפורש ──────────────────
        if not plan.get("approved"):
            print("🛑 התוכנית לא אושרה (approved=true חסר) — סנכרון לגרמין נחסם.")
            print("   אשר דרך confirm_week.py / approve-week workflow לפני דחיפה.")
            sys.exit(1)

        # ── ולידציה של כל האימונים לפני כל חיבור/העלאה ───────────────────
        try:
            for s in sessions:
                validate_workout(s)
        except ValueError as e:
            print(f"🛑 ולידציה נכשלה — לא נדחף כלום: {e}")
            sys.exit(1)

        # ── מניעת כפילויות: דלג על מה שכבר נוצר (אלא אם --force) ──────────
        already = {}
        if CREATED_FILE.exists():
            try:
                already = {(c["date"], c["name"]): c
                           for c in json.loads(CREATED_FILE.read_text(encoding="utf-8"))}
            except Exception:
                already = {}

        client = login()
        created = list(already.values()) if not force else []
        failures = []
        for s in sessions:
            name = s["name"] if s["type"] == "run" else STRENGTH_DEFS[s["key"]]["name"]
            if not force and (s["date"], name) in already:
                print(f"⏭️  {s['date']} · {name} · כבר קיים — דילוג")
                continue
            try:
                if s["type"] == "run":
                    res = client.upload_running_workout(build_run(s))
                else:
                    res = client.upload_workout(build_strength(s["key"]))
                wid = res.get("workoutId") or res.get("workoutid")
                if not wid:
                    raise ValueError(f"תגובת העלאה ללא workoutId: {res}")
                client.schedule_workout(wid, s["date"])
                created.append({"date": s["date"], "name": name, "workout_id": wid})
                print(f"✅ {s['date']} · {name} · id {wid}")
            except Exception as e:
                failures.append({"date": s["date"], "name": name, "error": str(e)})
                print(f"⚠️  כשל ב-{s['date']} · {name}: {e}")

        # תמיד שומרים את מה שהצליח — אין אימונים יתומים שלא מתועדים
        CREATED_FILE.write_text(json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = len(created) - (0 if force else len(already))
        print(f"\n🎯 {ok} אימונים חדשים שובצו · {len(failures)} כשלונות.")
        if failures:
            print("⚠️ כשלונות (לא שובצו):")
            for f in failures:
                print(f"   • {f['date']} · {f['name']} — {f['error']}")
        print("למחיקה: python push_week.py --cleanup")
        return

    print("בחר מצב: --build-only | --push [--force] | --cleanup")


if __name__ == "__main__":
    main()
