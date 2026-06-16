"""
check_telegram_reply.py — Poll for Telegram reply to the morning workout recommendation.

Runs every 5 minutes via GitHub Actions (coach-morning-reply.yml).

Logic:
1. Read morning_state.json — if missing, date != today, or status != "pending_reply": exit 0
2. If > 90 minutes since sent_at_unix → update status to "timed_out", exit 0
3. Poll Telegram for reply (approve / reject / None)
4. "approve" → call adjust_today.apply_adjustment(), update state to "applied"
5. "reject"  → update state to "overridden", write override to data.json, notify Telegram
6. None      → exit 0 (check again in 5 min)
"""

import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE = Path(__file__).parent
MORNING_STATE_FILE = BASE / "morning_state.json"
DATA_FILE = BASE / "data.json"

TIMEOUT_MINUTES = 90


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return None


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    today = date.today().isoformat()

    # ── 1. Check morning_state.json ──────────────────────────────────────────
    state = _load_json(MORNING_STATE_FILE)
    if not state:
        logger.info("morning_state.json not found — nothing to do.")
        sys.exit(0)

    if state.get("date") != today:
        logger.info("morning_state.json is for %s, not today (%s) — exit.", state.get("date"), today)
        sys.exit(0)

    if state.get("status") != "pending_reply":
        logger.info("Status is '%s', not 'pending_reply' — exit.", state.get("status"))
        sys.exit(0)

    # ── 2. Timeout check ────────────────────────────────────────────────────
    sent_at = state.get("sent_at_unix", 0)
    elapsed_minutes = (time.time() - sent_at) / 60

    if elapsed_minutes > TIMEOUT_MINUTES:
        logger.info("%.1f minutes elapsed — timed out (limit: %d min).", elapsed_minutes, TIMEOUT_MINUTES)
        state["status"] = "timed_out"
        _save_json(MORNING_STATE_FILE, state)
        _send_timeout_notification(state)
        sys.exit(0)

    # ── 3. Poll Telegram for reply ───────────────────────────────────────────
    import telegram_notify as tg

    message_id = state.get("message_id")
    reply = tg.find_reply(message_id, sent_at)
    logger.info("Telegram reply: %s (elapsed %.1f min)", reply, elapsed_minutes)

    # ── 4. APPROVE ───────────────────────────────────────────────────────────
    if reply == "approve":
        logger.info("User approved adjustment — applying...")
        from adjust_today import apply_adjustment
        success = apply_adjustment(state)

        if success:
            state["status"] = "applied"
            _save_json(MORNING_STATE_FILE, state)
            logger.info("State updated to 'applied'.")
        else:
            logger.error("apply_adjustment() failed — state not updated.")
            # Send failure notification
            try:
                tg.send_message("⚠️ <b>שגיאה בעדכון האימון בגרמין</b>\nנסה לעדכן ידנית.")
            except Exception:
                pass

        sys.exit(0 if success else 1)

    # ── 5. REJECT ────────────────────────────────────────────────────────────
    if reply == "reject":
        logger.info("User rejected adjustment — keeping original workout.")
        state["status"] = "overridden"
        _save_json(MORNING_STATE_FILE, state)

        # Write override record to data.json
        data = _load_json(DATA_FILE) or {}
        data["today_override"] = {
            "date": today,
            "readiness_override": True,
            "planned": state.get("planned", ""),
            "reason": state.get("reason", ""),
            "adjustment_rejected": state.get("adjustment_type", ""),
        }
        _save_json(DATA_FILE, data)
        logger.info("Override written to data.json.")

        # Notify Telegram
        try:
            tg.send_message(
                "✅ <b>האימון נשאר כמתוכנן.</b>\n"
                "מתועד לניתוח עתידי (תגובה ידנית של הספורטאי)."
            )
        except Exception as exc:
            logger.warning("Could not send reject notification: %s", exc)

        sys.exit(0)

    # ── 6. NO REPLY YET ─────────────────────────────────────────────────────
    logger.info("No reply yet — will check again in 5 minutes.")
    sys.exit(0)


def _send_timeout_notification(state: dict) -> None:
    """Notify that the window expired and the original workout will stand."""
    try:
        import telegram_notify as tg
        planned = state.get("planned", "—")
        tg.send_message(
            f"⏰ <b>חלון התגובה פג (90 דקות)</b>\n"
            f"האימון המקורי נשמר: {planned}"
        )
    except Exception as exc:
        logger.warning("Could not send timeout notification: %s", exc)


if __name__ == "__main__":
    main()
