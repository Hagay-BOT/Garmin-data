"""
evening_cancel_prompt.py — נשלח כשחלון הערב (18:30–22:00) הסתיים בלי נתוני ריצה.

שולח הודעת טלגרם ששואלת אם הריצה המתוכננת בוטלה ולמה, וכותב evening_state.json
עם status="prompted" כדי ש-check_evening_reply.py יוכל ללכוד את התשובה.

נקרא רק בסלוט האחרון (22:00 ישראל) של coach-postworkout.yml.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).parent
STATE_FILE = BASE / "evening_state.json"
WEEK_PLAN = BASE / "week_plan.json"
DATA_FILE = BASE / "data.json"

# subtypes שנחשבים ריצה (לא כוח) — אימון הכוח כבר בוצע בבוקר
_RUN_SUBTYPES = {"easy", "quality", "long", "tempo", "intervals", "recovery"}
_RUN_TYPES = {"running", "treadmill_running", "trail_running"}


def ran_today() -> bool:
    """האם בוצעה ריצה בפועל היום (לפי data.json)."""
    if not DATA_FILE.exists():
        return False
    try:
        d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    today = date.today().isoformat()
    return any(a.get("date") == today and a.get("activity_type") in _RUN_TYPES
               for a in d.get("activities", []))


def already_prompted_today() -> bool:
    """האם כבר נשלחה שאלת ביטול היום (מניעת כפילות)."""
    if not STATE_FILE.exists():
        return False
    try:
        s = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    return s.get("date") == date.today().isoformat() and s.get("status") in (
        "prompted", "cancelled", "ran_unsynced")


def planned_run_today() -> dict | None:
    """מחזיר את סשן הריצה המתוכנן להיום מ-week_plan.json, אם קיים."""
    if not WEEK_PLAN.exists():
        return None
    try:
        plan = json.loads(WEEK_PLAN.read_text(encoding="utf-8"))
    except Exception:
        return None
    today = date.today().isoformat()
    for s in plan.get("sessions", []):
        if (s.get("date") == today
                and s.get("subtype") in _RUN_SUBTYPES
                and s.get("est_km")):
            return s
    return None


def main() -> None:
    today = date.today().isoformat()

    # שלושה תנאים מחייבים לשליחת שאלת ביטול:
    if ran_today():
        print("בוצעה ריצה היום — אין צורך בשאלת ביטול.")
        return
    if already_prompted_today():
        print("שאלת ביטול כבר נשלחה היום — מדלג.")
        return
    if not planned_run_today():
        print("לא הייתה ריצה מתוכננת היום — אין על מה לשאול.")
        return

    sess = planned_run_today()
    if sess:
        desc = f'{sess.get("est_km")} ק"מ ({sess.get("subtype")})'
    else:
        desc = "ריצה מתוכננת"

    text = (
        f"🏃 <b>לא ראיתי ריצה היום ({today})</b>\n\n"
        f"בתוכנית היה: {desc}\n\n"
        f"ביטלת את הריצה? אם כן — <b>למה?</b>\n"
        f"(עייפות / כאב / לחץ זמן / מזג אוויר / אחר)\n\n"
        f"כתוב לי במשפט קצר ואני אתעד את זה בהיסטוריה כדי להתחשב בזה בתכנון.\n"
        f"אם בעצם <i>רצת</i> והנתונים פשוט לא סונכרנו — כתוב «רצתי»."
    )

    import telegram_notify as tg
    message_id = tg.send_message(text)

    state = {
        "date": today,
        "status": "prompted",
        "planned": desc,
        "message_id": message_id,
        "sent_at_unix": time.time(),
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    print(f"שאלת ביטול נשלחה (message_id={message_id}), evening_state.json נשמר.")


if __name__ == "__main__":
    main()
