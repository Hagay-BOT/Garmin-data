"""
🛑 אישור שבועי מאוחד — פעולה אחת מפעילה את כל ההמשך אוטומטית.
כשהמשתמש מאשר את התוכנית (מריץ workflow זה), המערכת מבצעת ביחד:
  1. נועלת את week_plan.json (approved=true + חותמת זמן)
  2. מייצרת/מעדכנת את היומן (ICS)
  3. דוחפת ומסנכרנת את האימונים ל-Garmin

זהו השער היחיד — אין אישורים נפרדים נוספים. דורש GARMIN secrets (רץ ב-Actions).
"""
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).parent
PLAN_FILE = BASE / "week_plan.json"


def lock_plan() -> dict:
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    if not plan.get("sessions"):
        raise SystemExit("week_plan.json ריק — אין מה לאשר.")
    plan["approved"] = True
    plan["approved_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return plan


def main():
    print("🛑 אישור שבועי מאוחד — מתחיל\n")

    # 1. נעילה
    plan = lock_plan()
    n = len(plan["sessions"])
    print(f"✅ 1/3 week_plan.json נעול ({n} אימונים, אושר {plan['approved_at']})")

    # 2. יומן
    try:
        import calendar_sync
        sys.argv = ["calendar_sync"]
        calendar_sync.main()
        print("✅ 2/3 יומן (ICS) עודכן")
    except Exception as e:
        print(f"⚠️ 2/3 כשל ביצירת יומן: {e}")

    # 3. גרמין
    if not (os.environ.get("GARMIN_EMAIL") and os.environ.get("GARMIN_PASSWORD")):
        print("⚠️ 3/3 דילוג על גרמין — אין GARMIN secrets (רץ מחוץ ל-Actions?)")
    else:
        try:
            import push_week
            # RESYNC=true (M4.2): ניקוי מלא לפני הדחיפה — פעולה אחת במקום הריקוד
            # הידני cleanup→המתנה→approve שביצענו ידנית אחרי כל שינוי-תוכנית.
            if os.environ.get("RESYNC", "").lower() in ("1", "true", "yes"):
                print("🧹 RESYNC — מנקה את האימונים הקיימים בגרמין לפני דחיפה נקייה...")
                sys.argv = ["push_week", "--cleanup"]
                push_week.main()
            sys.argv = ["push_week", "--push"]
            push_week.main()
            print("✅ 3/3 אימונים סונכרנו ל-Garmin")
        except Exception as e:
            print(f"⚠️ 3/3 כשל בסנכרון גרמין: {e}")

    print("\n🎯 האישור המאוחד הושלם — JSON נעול · יומן · גרמין.")


if __name__ == "__main__":
    main()
