"""
ניסוי: הזנת אימון מובנה לגרמין.
מטרה: לבדוק אם אפשר לדחוף תוכנית אימון מהמאמן ישירות ללוח של גרמין.

מצבי הרצה:
  python push_workout_test.py --build-only   → בונה ומדפיס JSON בלבד (בלי סיסמה, בלי חיבור)
  python push_workout_test.py                → מתחבר, מעלה אימון בדיקה, מתזמן למחר, מאמת
  python push_workout_test.py --cleanup <id> → מוחק אימון בדיקה לפי מזהה

סיסמה נקראת ממשתני סביבה GARMIN_EMAIL / GARMIN_PASSWORD (GitHub Secrets בלבד).
"""
import os
import sys
import json
from datetime import date, timedelta

sys.stdout.reconfigure(encoding="utf-8")

from garminconnect.workout import (
    RunningWorkout,
    WorkoutSegment,
    create_warmup_step,
    create_interval_step,
    create_cooldown_step,
)

TEST_NAME = "🧪 בדיקה — מאמן AI (אפשר למחוק)"


def build_test_workout() -> RunningWorkout:
    """אימון בדיקה פשוט: 5 דק' חימום, 20 דק' ריצה קלה, 5 דק' שחרור."""
    steps = [
        create_warmup_step(300.0, step_order=1),    # 5 דק' חימום
        create_interval_step(1200.0, step_order=2),  # 20 דק' ריצה
        create_cooldown_step(300.0, step_order=3),   # 5 דק' שחרור
    ]
    return RunningWorkout(
        workoutName=TEST_NAME,
        estimatedDurationInSecs=1800,
        description="אימון בדיקה אוטומטי מהמאמן — לבדיקת היתכנות הזנה לגרמין.",
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                workoutSteps=steps,
            )
        ],
    )


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

    # מצב בנייה בלבד — בלי חיבור, בלי סיסמה
    if "--build-only" in args:
        wk = build_test_workout()
        print("=== JSON שייבנה ויישלח לגרמין ===")
        print(json.dumps(wk.model_dump(by_alias=True), ensure_ascii=False, indent=2))
        print("\n✅ הבנייה תקינה (Pydantic אימת את המבנה).")
        return

    # מצב ניקוי
    if "--cleanup" in args:
        idx = args.index("--cleanup")
        workout_id = args[idx + 1]
        client = login()
        client.delete_workout(workout_id)
        print(f"🗑️  אימון {workout_id} נמחק.")
        return

    # מצב מלא — העלאה + תזמון
    client = login()
    wk = build_test_workout()

    print("מעלה אימון בדיקה...")
    result = client.upload_running_workout(wk)
    workout_id = result.get("workoutId") or result.get("workoutid")
    print(f"✅ האימון הועלה. מזהה: {workout_id}")

    target = date.today() + timedelta(days=1)
    target_str = target.isoformat()
    print(f"מתזמן לתאריך {target_str}...")
    sched = client.schedule_workout(workout_id, target_str)
    print(f"✅ תוזמן. תגובת השרת: {json.dumps(sched, ensure_ascii=False)[:200]}")

    print("\nמאמת מול הלוח של גרמין...")
    scheduled = client.get_scheduled_workouts(target.year, target.month)
    count = len(scheduled) if isinstance(scheduled, list) else len(scheduled or {})
    print(f"נמצאו {count} פריטים בלוח לחודש {target.year}-{target.month:02d}")

    print(f"\n🎯 הצלחה! בדוק באפליקציית Garmin Connect → Calendar → {target_str}")
    print(f"למחיקה: python push_workout_test.py --cleanup {workout_id}")


if __name__ == "__main__":
    main()
