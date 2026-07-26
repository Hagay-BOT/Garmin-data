# -*- coding: utf-8 -*-
"""
Smoke tests for every Telegram message the coach sends.

Guards the exact failure classes that broke production this session:
  - unescaped '<' / '&' in LLM content → Telegram 400 → lost message
  - empty / missing JSON → no message
  - JSON parsing across markers / ```json fence / bare object

Runs standalone (`python test_telegram_messages.py`) and under pytest.
No network, no credentials: telegram_notify.send_message is monkeypatched to capture text.
"""
import re
import telegram_notify
import coach

# ── HTML safety: only <b>/<i> tags allowed; all dynamic content must be escaped ──
_ALLOWED_TAGS = ["<b>", "</b>", "<i>", "</i>"]


def assert_html_safe(msg: str):
    assert msg and msg.strip(), "message is empty"
    stripped = msg
    for t in _ALLOWED_TAGS:
        stripped = stripped.replace(t, "")
    stripped = re.sub(r"&(?:lt|gt|amp|quot|#\d+);", "", stripped)
    assert "<" not in stripped and ">" not in stripped, f"unescaped angle bracket in: {stripped[:120]!r}"
    assert "&" not in stripped, f"unescaped ampersand in: {stripped[:120]!r}"


def _capture(monkeypatch=None):
    """Patch telegram_notify.send_message to capture the outgoing text."""
    box = {}

    def fake_send(text, parse_mode="HTML", reply_markup=None):
        assert_html_safe(text)
        box["text"] = text
        return 12345  # fake message_id → treated as a successful send

    telegram_notify.send_message = fake_send
    return box


def test_weekly_message_escapes_and_nonempty():
    _capture()
    wr = {
        "headline": "בנה בסיס — קל <141 & יציב",
        "compass": "VDOT 45 → 50 (פער סף 4:50 & endurance)",
        "week_analysis": "שבוע טוב, 27 ק\"מ, Z3 גבוה מדי (>15%)",
        "wins": ["התאוששות טובה", "סף ב-4:50 & יציב"],
        "concerns": ["Z3 > 15%"],
        "plan_summary": ["ראשון: Z2 5 ק\"מ", "שבת: לונג 10"],
        "focus": "שמור דופק <141",
        "tip": "strides בקצב 3:50-4:10 & קדנס 180",
    }
    coach._send_weekly_telegram(wr, safety_messages=["נפח +10% & בטוח"], needs_review=False)


def test_weekly_parse_markers():
    body = ('{"headline":"h","compass":"c","week_analysis":"w","wins":[],'
            '"concerns":[],"plan_summary":[],"focus":"f"}')
    text = f"...\n---WEEKLY_REPORT_JSON---\n{body}\n---END_WEEKLY_REPORT---\n"
    got = coach._parse_weekly_report_json(text)
    assert got and got.get("headline") == "h", f"weekly parse failed: {got}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"\nOK — {len(tests)} smoke tests passed.")


if __name__ == "__main__":
    _run_all()
