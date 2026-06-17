"""
check_evening_reply.py — לוכד את תשובת הספורטאי לשאלת ביטול הריצה.

רץ כל ~15 דקות (coach-evening-reply.yml) בחלון 22:00–23:30 ישראל.

לוגיקה:
1. קרא evening_state.json — אם חסר, תאריך ≠ היום, או status ≠ "prompted": exit 0
2. אם עברו > TIMEOUT_MINUTES מאז השליחה → status="cancelled", reason="לא דווח", תעד, exit
3. poll טלגרם לטקסט חופשי:
   - "רצתי" / "ran"  → status="ran_unsynced" (הנתונים יגיעו, ינותחו אוטומטית)
   - טקסט אחר        → status="cancelled", reason=הטקסט, תעד ב-run_cancellations.json
   - אין תשובה       → exit 0 (נבדוק שוב בעוד 15 דק')

ביטולים נשמרים בקובץ ייעודי run_cancellations.json (ולא ב-data.json, שאותו
fetch_garmin.py דורס בכל ריצה).
"""

import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE = Path(__file__).parent
STATE_FILE = BASE / "evening_state.json"
CANCEL_LOG = BASE / "run_cancellations.json"

TIMEOUT_MINUTES = 90
_RAN_KEYWORDS = {"רצתי", "ran", "כן רצתי", "רץ"}


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("לא ניתן לקרוא %s: %s", path, exc)
        return None


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_cancellation(today: str, planned: str, reason: str) -> None:
    """מוסיף רשומת ביטול ל-run_cancellations.json (idempotent על אותו תאריך)."""
    log = _load_json(CANCEL_LOG) or {"version": 1, "cancellations": []}
    log["cancellations"] = [c for c in log["cancellations"] if c.get("date") != today]
    log["cancellations"].append({
        "date": today,
        "planned": planned,
        "reason": reason,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    })
    log["cancellations"] = sorted(log["cancellations"], key=lambda c: c["date"])
    _save_json(CANCEL_LOG, log)
    logger.info("ביטול תועד: %s — %s", today, reason)


def main() -> None:
    today = date.today().isoformat()

    state = _load_json(STATE_FILE)
    if not state:
        logger.info("evening_state.json לא נמצא — אין מה לעשות.")
        sys.exit(0)
    if state.get("date") != today:
        logger.info("evening_state.json הוא ל-%s ולא היום (%s) — exit.", state.get("date"), today)
        sys.exit(0)
    if state.get("status") != "prompted":
        logger.info("status='%s' (לא 'prompted') — exit.", state.get("status"))
        sys.exit(0)

    sent_at = state.get("sent_at_unix", 0)
    elapsed_min = (time.time() - sent_at) / 60
    planned = state.get("planned", "ריצה מתוכננת")

    # ── Timeout → רישום ביטול ללא סיבה ──────────────────────────────────────
    if elapsed_min > TIMEOUT_MINUTES:
        logger.info("%.1f דקות עברו — timeout (%d).", elapsed_min, TIMEOUT_MINUTES)
        state["status"] = "cancelled"
        state["reason"] = "לא דווח (timeout)"
        _save_json(STATE_FILE, state)
        log_cancellation(today, planned, "לא דווח")
        sys.exit(0)

    # ── Poll טלגרם ──────────────────────────────────────────────────────────
    import telegram_notify as tg
    text = tg.find_text_reply(sent_at)
    if not text:
        logger.info("אין תשובה עדיין — נבדוק שוב בעוד 15 דק'.")
        sys.exit(0)

    logger.info("תשובה התקבלה: %s", text)
    text_lower = text.lower()

    # ── "רצתי" → לא ביטול, הנתונים פשוט לא סונכרנו ──────────────────────────
    if any(k in text_lower for k in (kw.lower() for kw in _RAN_KEYWORDS)):
        state["status"] = "ran_unsynced"
        _save_json(STATE_FILE, state)
        try:
            tg.send_message(
                "📡 הבנתי — הריצה כנראה עדיין לא סונכרנה מהשעון.\n"
                "אנתח אותה אוטומטית כשהנתונים יגיעו לגרמין."
            )
        except Exception:
            pass
        sys.exit(0)

    # ── טקסט חופשי → ביטול עם סיבה ──────────────────────────────────────────
    state["status"] = "cancelled"
    state["reason"] = text
    _save_json(STATE_FILE, state)
    log_cancellation(today, planned, text)
    try:
        tg.send_message(
            f"✅ תיעדתי שהריצה בוטלה.\n"
            f"סיבה: <i>{text}</i>\n"
            f"אתחשב בזה בתכנון ההמשך."
        )
    except Exception as exc:
        logger.warning("לא ניתן לשלוח אישור: %s", exc)
    sys.exit(0)


if __name__ == "__main__":
    main()
