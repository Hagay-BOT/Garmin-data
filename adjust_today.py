"""
adjust_today.py — Apply an AI-recommended workout adjustment to Garmin.

Reads:
  morning_state.json   — adjustment type + planned/adjusted workout info
  created_workouts.json — maps date→workout_id
  week_plan.json        — find today's run session definition

Actions per adjustment_type:
  none      → exit 0 (no change)
  shorter   → reduce all step seconds by 25%, add "קצר" suffix to name
  easier    → replace with single Z2 easy interval (total × 0.9)
  indoor    → prepend "🏃‍♂️ חדר כושר — " to name (same structure)
  rest      → delete today's workout from Garmin, no replacement
  reschedule→ treated as rest (remove from Garmin, user reschedules manually)

On success:
  - Updates created_workouts.json with new workout_id
  - Sends Telegram confirmation

Usage:
  python adjust_today.py   (reads morning_state.json for context)
  Can also be imported and called as apply_adjustment(state_data).
"""

import json
import os
import sys
import logging
from datetime import date
from pathlib import Path
from copy import deepcopy

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BASE = Path(__file__).parent
MORNING_STATE_FILE = BASE / "morning_state.json"
CREATED_FILE = BASE / "created_workouts.json"
PLAN_FILE = BASE / "week_plan.json"


# ── Helper: load files ───────────────────────────────────────────────────────

def _load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return None


def _save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Helper: Garmin login ─────────────────────────────────────────────────────

def _garmin_login():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        logger.error("GARMIN_EMAIL / GARMIN_PASSWORD not set.")
        sys.exit(1)
    client = Garmin(email, password)
    client.login()
    logger.info("Connected to Garmin.")
    return client


# ── Workout builders (import from push_week) ──────────────────────────────────

def _build_run_from_session(session: dict):
    """Build a RunningWorkout from a week_plan session dict."""
    from push_week import build_run
    return build_run(session)


# ── Step manipulation ────────────────────────────────────────────────────────

def _apply_shorter(session: dict) -> dict:
    """Reduce all step durations by 25%, append 'קצר' to name."""
    s = deepcopy(session)
    s["name"] = s.get("name", "ריצה") + " — קצר"
    s["desc"] = s.get("desc", "") + " (קוצר ב-25% — מוכנות בינונית)"
    for step in s.get("steps", []):
        step["seconds"] = int(round(step["seconds"] * 0.75))
    return s


def _apply_easier(session: dict) -> dict:
    """Replace all steps with a single Z2 easy interval (total time × 0.9)."""
    s = deepcopy(session)
    original_total = sum(st["seconds"] for st in s.get("steps", []))
    new_total = int(round(original_total * 0.9))
    s["name"] = "🏃 Z2 קל — " + s.get("name", "ריצה")
    s["desc"] = f"ריצה קלה Z2 {new_total // 60} דק' (מוכנות נמוכה — הוחלפה לאיטי)"
    s["steps"] = [{"kind": "interval", "seconds": new_total}]
    return s


def _apply_indoor(session: dict) -> dict:
    """Prepend indoor marker to name."""
    s = deepcopy(session)
    s["name"] = "🏃‍♂️ חדר כושר — " + s.get("name", "ריצה")
    s["desc"] = s.get("desc", "") + " (חדר כושר — מזג אוויר)"
    return s


# ── Find today's run in plan ─────────────────────────────────────────────────

def _find_today_run_session(plan: dict) -> dict | None:
    today = date.today().isoformat()
    for s in plan.get("sessions", []):
        if s.get("date") == today and s.get("type") == "run":
            return s
    return None


def _find_today_run_in_created(created: list) -> dict | None:
    """Return the created_workouts entry for today's run (first run found)."""
    today = date.today().isoformat()
    # Look for run entries (not strength) — heuristic: name starts with 🏃
    for item in created:
        if item.get("date") == today:
            name = item.get("name", "")
            if "🏃" in name or "ריצה" in name or "קל" in name or "סף" in name or "Long" in name:
                return item
    # Fallback: any entry for today
    for item in created:
        if item.get("date") == today:
            return item
    return None


# ── Core apply logic ─────────────────────────────────────────────────────────

def apply_adjustment(state: dict) -> bool:
    """
    Apply the adjustment from morning_state to Garmin.

    Returns True on success, False on failure.
    State dict must have: adjustment_type, planned, adjusted, reason.
    """
    adjustment_type = state.get("adjustment_type", "none")
    today = date.today().isoformat()

    if adjustment_type == "none":
        logger.info("adjustment_type=none — nothing to do.")
        return True

    # Load plan and created workouts
    plan = _load_json(PLAN_FILE)
    created = _load_json(CREATED_FILE) or []

    if not plan:
        logger.error("week_plan.json not found — cannot adjust.")
        return False

    # Find today's run session in the plan
    run_session = _find_today_run_session(plan)
    if not run_session and adjustment_type != "rest":
        logger.warning("No run session found for %s in week_plan.json.", today)
        # For rest, we still try to delete
        if adjustment_type not in ("rest", "reschedule"):
            return False

    # Find existing workout_id for today's run
    created_entry = _find_today_run_in_created(created)
    existing_workout_id = created_entry["workout_id"] if created_entry else None

    # Login to Garmin
    try:
        client = _garmin_login()
    except SystemExit:
        return False

    # ── REST / RESCHEDULE: just delete ───────────────────────────────────────
    if adjustment_type in ("rest", "reschedule"):
        if existing_workout_id:
            try:
                client.delete_workout(existing_workout_id)
                logger.info("Deleted workout %s from Garmin.", existing_workout_id)
                # Remove from created list
                created = [c for c in created if not (c.get("date") == today and c.get("workout_id") == existing_workout_id)]
                _save_json(CREATED_FILE, created)
            except Exception as exc:
                logger.warning("Could not delete workout %s: %s", existing_workout_id, exc)
        else:
            logger.info("No existing workout found for today to delete.")

        # Send Telegram confirmation
        _send_telegram_confirmation(adjustment_type, state)
        return True

    # ── BUILD MODIFIED SESSION ────────────────────────────────────────────────
    if adjustment_type == "shorter":
        modified_session = _apply_shorter(run_session)
    elif adjustment_type == "easier":
        modified_session = _apply_easier(run_session)
    elif adjustment_type == "indoor":
        modified_session = _apply_indoor(run_session)
    else:
        logger.warning("Unknown adjustment_type: %s — treating as none.", adjustment_type)
        return True

    # Build RunningWorkout object
    try:
        workout = _build_run_from_session(modified_session)
    except Exception as exc:
        logger.error("Failed to build workout: %s", exc)
        return False

    # Delete old workout from Garmin
    if existing_workout_id:
        try:
            client.delete_workout(existing_workout_id)
            logger.info("Deleted old workout %s.", existing_workout_id)
        except Exception as exc:
            logger.warning("Could not delete old workout %s: %s", existing_workout_id, exc)

    # Upload new workout and schedule it for today
    try:
        res = client.upload_running_workout(workout)
        new_workout_id = res.get("workoutId") or res.get("workoutid")
        if not new_workout_id:
            logger.error("Upload returned no workoutId: %s", res)
            return False
        client.schedule_workout(new_workout_id, today)
        logger.info("Uploaded and scheduled new workout %s for %s.", new_workout_id, today)
    except Exception as exc:
        logger.error("Failed to upload/schedule workout: %s", exc)
        return False

    # Update created_workouts.json
    # Remove old entry for today's run
    if created_entry:
        created = [c for c in created
                   if not (c.get("date") == today and c.get("workout_id") == existing_workout_id)]
    # Add new entry
    created.append({
        "date": today,
        "name": modified_session["name"],
        "workout_id": new_workout_id,
    })
    _save_json(CREATED_FILE, created)
    logger.info("created_workouts.json updated with new workout_id %s.", new_workout_id)

    # Send Telegram confirmation
    _send_telegram_confirmation(adjustment_type, state)
    return True


def _send_telegram_confirmation(adjustment_type: str, state: dict) -> None:
    """Send a Telegram message confirming the adjustment was applied."""
    try:
        import telegram_notify as tg
        adj_labels = {
            "shorter": "קוצר ב-25%",
            "easier": "הוחלף לאיטי Z2",
            "indoor": "הועבר לחדר כושר",
            "rest": "נמחק (יום מנוחה)",
            "reschedule": "נמחק (לתזמון מחדש)",
        }
        label = adj_labels.get(adjustment_type, adjustment_type)
        planned = state.get("planned", "—")
        adjusted = state.get("adjusted", "—")
        reason = state.get("reason", "—")
        text = (
            f"✅ <b>האימון עודכן בגרמין</b>\n\n"
            f"📋 תוכנן: {planned}\n"
            f"✏️ שונה ל: {adjusted}\n"
            f"🔧 שינוי: {label}\n"
            f"📌 סיבה: {reason}"
        )
        tg.send_message(text)
        logger.info("Telegram confirmation sent.")
    except Exception as exc:
        logger.warning("Could not send Telegram confirmation: %s", exc)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    state = _load_json(MORNING_STATE_FILE)
    if not state:
        logger.error("morning_state.json not found or invalid.")
        sys.exit(1)

    today = date.today().isoformat()
    if state.get("date") != today:
        logger.info("morning_state.json is for %s, not today (%s) — exit.", state.get("date"), today)
        sys.exit(0)

    success = apply_adjustment(state)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
