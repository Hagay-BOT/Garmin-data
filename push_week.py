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
    create_recovery_step,
    create_repeat_group,
)
import re

BASE = Path(__file__).parent
PLAN_FILE = BASE / "week_plan.json"
CREATED_FILE = BASE / "created_workouts.json"

import athlete
import store

STRENGTH_SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}
# מקור-אמת יחיד לשמות הכוח: athlete.py (A/B היו הפוכים כשהוגדרו בכל קובץ בנפרד)
STRENGTH_DEFS = {k: {"name": athlete.STRENGTH_NAMES[k], "minutes": athlete.STRENGTH_MINUTES,
                     "desc": athlete.STRENGTH_DESCS[k]} for k in ("A", "B", "C")}

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


def _strides_spec(session: dict):
    """מחזיר (count, meters, rest_sec) אם לאימון יש strides, אחרת None.
    קורא קודם שדה מובנה session['strides'], אחרת מפרסר מהשם/תיאור ('6×100מ strides')."""
    s = session.get("strides")
    if isinstance(s, dict) and s.get("count"):
        return int(s["count"]), int(s.get("meters", 100)), int(s.get("rest_sec", 75))
    text = f"{session.get('name','')} {session.get('desc','')}".lower()
    if "stride" not in text and "סטרייד" not in text:
        return None
    m = re.search(r"(\d+)\s*[×x*]\s*(\d+)\s*מ", text)        # "6×100מ"
    if m:
        return int(m.group(1)), int(m.group(2)), 75
    m2 = re.search(r"(\d+)\s*strides", text)                  # "6 strides"
    if m2:
        return int(m2.group(1)), 100, 75
    return None


def build_run(session: dict) -> RunningWorkout:
    """בונה RunningWorkout מובנה (נתיב מוכח) מהצעדים שב-week_plan.json.
    אם יש strides — מוסיף repeat group **לפני השחרור**: ריצה קצרה (~100מ') + מנוחה, ×count."""
    plan_steps = session["steps"]
    mains = [st for st in plan_steps if st["kind"] != "cooldown"]
    cools = [st for st in plan_steps if st["kind"] == "cooldown"]
    steps, total, order = [], 0, 1

    for st in mains:
        secs = float(st["seconds"]); total += secs
        steps.append(STEP_BUILDERS[st["kind"]](secs, step_order=order)); order += 1

    # ── strides כ-repeat group (לפני השחרור): 100מ' ריצה (~זמן) + מנוחה, ×count ──
    spec = _strides_spec(session)
    if spec:
        count, meters, rest = spec
        stride_secs = max(15.0, float(round(meters * 0.24)))  # 100מ' ≈ 24ש' @ ~4:00/ק"מ
        rep_steps = [
            create_interval_step(stride_secs, step_order=1),   # ריצת ה-stride
            create_recovery_step(float(rest), step_order=2),    # מנוחה (הליכה)
        ]
        steps.append(create_repeat_group(count, rep_steps, step_order=order)); order += 1
        total += count * (stride_secs + rest)
        print(f"  + strides: {count}×{meters}מ (~{int(stride_secs)}ש') · מנוחה {rest}ש'")

    for st in cools:
        secs = float(st["seconds"]); total += secs
        steps.append(create_cooldown_step(secs, step_order=order)); order += 1

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
    # M9.2: דרך garmin_client — הנתיב הזה נפל עד כה על ה-429 הראשון; עכשיו retry אחיד.
    from garmin_client import login as _login
    return _login()


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
        ids = store.load_created()
        if not ids:
            print("אין אימונים רשומים — אין מה למחוק.")
            return
        client = login()
        for item in ids:
            try:
                client.delete_workout(item["workout_id"])
                print(f"🗑️  נמחק {item['workout_id']} ({item['name']})")
            except Exception as e:
                print(f"⚠️  כשל במחיקת {item['workout_id']}: {e}")
        # כותבים רשימה ריקה (לא מוחקים את הקובץ) — כדי שה-git_sync ישמור מצב נקי
        # ב-repo. אחרת ה-repo ימשיך להחזיק IDs מחוקים והדחיפה הבאה תדלג עליהם.
        store.save_created([])
        print("✅ created_workouts.json נוקה (רשימה ריקה).")
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
        already = {(c["date"], c["name"]): c for c in store.load_created()}

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
        store.save_created(created)
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
