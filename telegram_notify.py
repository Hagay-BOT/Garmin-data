"""
Telegram Bot notification module for Garmin training coach.

Uses environment variables:
  TELEGRAM_BOT_TOKEN — bot token from @BotFather
  TELEGRAM_CHAT_ID   — chat/user ID to send messages to

All functions fail silently (log warning, return None) if credentials are missing.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

try:
    import requests as _requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False
    logger.warning("requests library not installed — Telegram notifications disabled.")


def _token() -> str | None:
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _chat_id() -> str | None:
    return os.environ.get("TELEGRAM_CHAT_ID")


def _api(method: str, **kwargs) -> dict | None:
    """Call a Telegram Bot API method. Returns parsed JSON or None on failure."""
    token = _token()
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — skipping Telegram call.")
        return None
    if not _REQUESTS_AVAILABLE:
        logger.warning("requests not available — skipping Telegram call.")
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        resp = _requests.post(url, json=kwargs, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning("Telegram API call failed (%s %s): %s", method, kwargs.get("chat_id", ""), exc)
        return None


def send_message(text: str, parse_mode: str = "HTML") -> int | None:
    """
    Send a text message to TELEGRAM_CHAT_ID.
    Returns the message_id on success, None on failure.
    """
    chat_id = _chat_id()
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set — skipping send_message.")
        return None
    result = _api("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)
    if result and result.get("ok"):
        return result["result"]["message_id"]
    return None


def get_updates(offset: int | None = None) -> list:
    """
    Call getUpdates. Returns a list of update objects.
    offset — if provided, only updates with update_id >= offset are returned.
    """
    kwargs: dict = {"timeout": 0, "allowed_updates": ["message"]}
    if offset is not None:
        kwargs["offset"] = offset
    result = _api("getUpdates", **kwargs)
    if result and result.get("ok"):
        return result.get("result", [])
    return []


def find_reply(since_message_id: int, since_time_unix: float) -> str | None:
    """
    Poll getUpdates for a reply from TELEGRAM_CHAT_ID sent AFTER since_time_unix.

    Looks for text messages containing:
      "כן" / "yes" / "1"  → returns "approve"
      "לא" / "no"  / "2"  → returns "reject"

    Returns "approve" | "reject" | None (not yet replied / credentials missing).

    NOTE: This function performs a single poll (not a blocking loop).
    Call it repeatedly (e.g. every 5 minutes) from check_telegram_reply.py.
    """
    chat_id = _chat_id()
    if not chat_id:
        logger.warning("TELEGRAM_CHAT_ID not set — cannot check for reply.")
        return None

    APPROVE_KEYWORDS = {"כן", "yes", "1"}
    REJECT_KEYWORDS  = {"לא", "no", "2"}

    updates = get_updates()
    for update in updates:
        msg = update.get("message") or {}
        msg_date = msg.get("date", 0)
        msg_chat = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()

        # Must be from our chat, after the sent_at timestamp
        if msg_chat != str(chat_id):
            continue
        if msg_date <= since_time_unix:
            continue

        text_lower = text.lower()
        words = set(text_lower.split())

        # Check approve keywords (any word match)
        if words & APPROVE_KEYWORDS or any(kw in text_lower for kw in APPROVE_KEYWORDS):
            return "approve"
        # Check reject keywords
        if words & REJECT_KEYWORDS or any(kw in text_lower for kw in REJECT_KEYWORDS):
            return "reject"

    return None
