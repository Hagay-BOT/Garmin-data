# -*- coding: utf-8 -*-
"""
message_nlu.py — הבנת הודעות-טלגרם במודל קטן (14.11.2026).

למה: כללי-הזיהוי הקשיחים (regex) ב-telegram_intake וב-body_state פספסו שוב ושוב
ניסוחים טבעיים ("הברכיים גומרות אותי", "כף רגל בגיד החיצוני") והשאירו את הגיא בלי
מענה. שפה חופשית היא קלט שמתאים למודל; ההחלטות נשארות בקוד.

גבולות (חוק הליבה הדטרמיניסטית):
  • המודל רק *מתאר* את ההודעה: כוונה (עריכה או הערה) ודגלי-גוף (פתיחה/סגירה).
  • אישור תוכנית ("אשר") נשאר דטרמיניסטי לגמרי ולא עובר כאן לעולם.
  • התוכנית, התקרות והבטיחות נשארות בקוד (plan_generator, safety).
  • אין מפתח API, שגיאה, סירוב או פלט לא-תקין → None, והקורא נופל לכללים הישנים.

כיבוי: משתנה-הסביבה COACH_NLU=off.
"""
from __future__ import annotations

import json
import os

MODEL_NLU = "claude-haiku-5-5"
BODY_PARTS = ["knee", "ankle", "shin", "back", "hip", "achilles", "foot", "illness"]
INTENTS = ["revision", "note"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "body": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["open", "close"]},
                    "part": {"type": "string", "enum": BODY_PARTS},
                },
                "required": ["action", "part"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["intent", "body"],
    "additionalProperties": False,
}

_SYSTEM = """אתה מפענח הודעות קצרות בעברית שרץ חובב שולח לבוט האימונים שלו בטלגרם.
החזר JSON בלבד לפי הסכמה. אתה מתאר את ההודעה ולא מחליט שום דבר על התוכנית.

intent:
- "revision": ההודעה מבקשת לשנות את תוכנית האימונים (להזיז, להוסיף, להוריד, לקצר, להקל, להחליף יום או אימון).
- "note": כל דבר אחר: דיווח על הרגשה, שינה, כאב, עומס בעבודה, תיאור אימון שהיה, שאלה כללית.

body: רשימת שינויים במצב הגוף שההודעה מדווחת עליהם עכשיו. ריקה אם אין.
- action "open": כאב, פציעה, רגישות או מחלה שקיימים עכשיו.
- action "close": המתאמן אומר במפורש שהבעיה עברה.
- part: knee (ברך), ankle (קרסול), shin (שוק), back (גב), hip (ירך או מפשעה), achilles (גיד אכילס), foot (כף רגל, כולל גיד בכף הרגל ופלנטר), illness (מחלה, חום, הצטננות).
- כאב שרירים רגיל אחרי אימון, עייפות, או אזכור של חלק גוף בלי בעיה: לא נכנסים.
- שלילה ("הברך לא כואבת", "לא חולה") בלי דגל פתוח קודם: לא נכנסת כ-open."""

_cache: dict = {}


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("COACH_NLU", "").lower() != "off"


def _validate(data) -> dict | None:
    if not isinstance(data, dict) or data.get("intent") not in INTENTS:
        return None
    body = []
    for b in data.get("body") or []:
        if (isinstance(b, dict) and b.get("action") in ("open", "close")
                and b.get("part") in BODY_PARTS and (b["action"], b["part"]) not in body):
            body.append((b["action"], b["part"]))
    return {"intent": data["intent"], "body": body}


def understand(text: str, client=None) -> dict | None:
    """הודעה → {"intent": "revision"|"note", "body": [(action, part), ...]} או None.
    None = לא זמין; הקורא חייב ליפול לכללים הדטרמיניסטיים. לא זורק לעולם."""
    text = (text or "").strip()
    if not text:
        return None
    if text in _cache:
        return _cache[text]
    if client is None:
        if not enabled():
            return None
        try:
            import anthropic
            client = anthropic.Anthropic()
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ message_nlu: לקוח לא זמין ({e}) — כללים דטרמיניסטיים.")
            return None
    try:
        resp = client.messages.create(
            model=MODEL_NLU,
            # 8192 ולא פחות: thinking אדפטיבי + תקרה קטנה = פלט ריק (לקח max_tokens).
            max_tokens=8192,
            system=_SYSTEM,
            messages=[{"role": "user", "content": text[:1500]}],
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        if getattr(resp, "stop_reason", None) in ("refusal", "max_tokens"):
            print(f"⚠️ message_nlu: stop_reason={resp.stop_reason} — כללים דטרמיניסטיים.")
            return None
        raw = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        result = _validate(json.loads(raw))
    except Exception as e:  # noqa: BLE001 — רשת/400/JSON: תמיד נופלים לכללים
        print(f"⚠️ message_nlu: כשל ({str(e)[:120]}) — כללים דטרמיניסטיים.")
        return None
    if result is not None:
        _cache[text] = result
    return result
