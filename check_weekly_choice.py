"""
check_weekly_choice.py — לוכד את בחירת A/B לתוכנית השבועית (שער ההכרעה).

רץ כל ~15 דק' שבת בערב (coach-weekly-choice.yml). כשיש קונפליקט מאקרו↔מציאות,
run_weekly שולח שתי אפשרויות וכותב weekly_state.json (status=pending_choice).
כאן לוכדים את התשובה ובונים את הווריאנט הנבחר → שכבת בטיחות → week_plan.json.

A = נאמן למאקרו · B = שמרני. timeout (90 דק') → ברירת מחדל B (הבטוח).
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
STATE_FILE = BASE / "weekly_state.json"
TIMEOUT_MINUTES = 90

_A_KEYS = {"a", "א", "1"}
_B_KEYS = {"b", "ב", "2"}


def _parse_choice(text: str) -> str | None:
    """טקסט חופשי → 'a' / 'b' / None. התאמת מילה שלמה (לא אות ראשונה) למניעת false-positive."""
    t = (text or "").strip().lower()
    if not t:
        return None
    words = set(t.split())
    is_a = bool(words & _A_KEYS) or "מאקרו" in t
    is_b = bool(words & _B_KEYS) or "שמרני" in t
    if is_a and not is_b:
        return "a"
    if is_b and not is_a:
        return "b"
    return None  # אמביוולנטי / לא תקף


def _finalize(state: dict, choice: str) -> bool:
    """בונה את הווריאנט הנבחר ומעביר דרך coach.save_week_plan (שכבת בטיחות)."""
    variant = state.get("variant_a") if choice == "a" else state.get("variant_b")
    if not variant:
        logger.error("וריאנט %s חסר ב-state.", choice)
        return False
    base = state.get("base") or {}
    raw_week = {
        "week_of": base.get("week_of"),
        "macro_week": base.get("macro_week"),
        "phase": base.get("phase"),
        "sessions": variant,
    }
    import coach  # ייבוא קל — Anthropic נבנה רק ב-main(), לא ב-import
    saved, messages, needs_review = coach.save_week_plan(
        raw_week, prev_week_km=state.get("prev_week_km", 0) or 0,
        macro=state.get("macro"), acwr=state.get("acwr"))
    logger.info("save_week_plan: saved=%s needs_review=%s", saved, needs_review)
    return saved


def main() -> None:
    today = date.today().isoformat()
    if not STATE_FILE.exists():
        logger.info("weekly_state.json לא נמצא — אין מה לעשות.")
        sys.exit(0)
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("weekly_state.json לא קריא: %s", exc)
        sys.exit(0)
    if state.get("date") != today or state.get("status") != "pending_choice":
        logger.info("אין הכרעה ממתינה להיום (status=%s).", state.get("status"))
        sys.exit(0)

    sent_at = state.get("sent_at_unix", 0)
    elapsed = (time.time() - sent_at) / 60

    import telegram_notify as tg

    # timeout → ברירת מחדל B (הבטוח)
    if elapsed > TIMEOUT_MINUTES:
        logger.info("%.1f דק' — timeout, בוחר B (שמרני).", elapsed)
        ok = _finalize(state, "b")
        state["status"] = "timeout_b" if ok else "error"
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        if ok:
            try:
                tg.send_message("⏰ לא התקבלה בחירה (90 דק') — בניתי את התוכנית <b>השמרנית (B)</b>. "
                                "ממתינה לאישורך לפני סנכרון לגרמין.")
            except Exception:
                pass
        sys.exit(0)

    text = tg.find_text_reply(sent_at)
    choice = _parse_choice(text) if text else None
    if not choice:
        logger.info("אין בחירה תקפה עדיין — נבדוק שוב בעוד 15 דק'.")
        sys.exit(0)

    logger.info("בחירה: %s", choice.upper())
    ok = _finalize(state, choice)
    state["status"] = f"chosen_{choice}" if ok else "error"
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    if ok:
        label = "נאמן למאקרו (A)" if choice == "a" else "שמרני (B)"
        try:
            tg.send_message(f"✅ נבחר: <b>{label}</b>. בניתי את התוכנית — "
                            f"ממתינה לאישורך לפני סנכרון לגרמין.")
        except Exception:
            pass
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
