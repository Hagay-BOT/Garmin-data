# -*- coding: utf-8 -*-
"""
preview_messages.py — תצוגת הודעות הטלגרם מהנתונים החיים, בלי לשלוח ובלי LLM (M9.6).

    python preview_messages.py

מרנדר לוקאלית את הודעת אחרי-האימון (מנתוני הריצה האחרונה + נתונים דטרמיניסטיים)
ואת שלד ההודעה השבועית — כדי לבקר נוסח/מבנה בלי לחכות לריצת פרודקשן ובלי עלות.
(מה שה-LLM ממלא מסומן כ-<LLM>; כל השאר אמיתי.)
"""
import datetime

import telegram_notify
import coach
import store

SENT = []


def _fake_send(text, parse_mode="HTML", reply_markup=None):
    SENT.append(text)
    return 999


telegram_notify.send_message = _fake_send


def main():
    data = store.load_data()
    runs = [a for a in data["activities"] if a.get("activity_type") in coach.RUN_TYPES]
    last = runs[-1] if runs else {}
    run_done = last.get("date") == datetime.date.today().isoformat()

    pw = {
        "category": {"base_run": "ריצה קלה", "quality_tempo": "טמפו",
                     "quality_intervals": "אינטרוולים", "long_run": "ריצה ארוכה"}.get(
                         last.get("category"), last.get("category", "ריצה")),
        "planned": coach._todays_planned_run_md(),
        "actual": (f"{last.get('distance_km','?')} ק\"מ · דופק {last.get('avg_hr','?')} · "
                   f"קדנס {last.get('cadence_spm','?')} · GCT {last.get('gct_ms','?')}ms"),
        "improve": ["<LLM: דגש 1 — מדד→פירוש→עוגן>", "<LLM: דגש 2>"],
        "keep": "<LLM: דגש שימור>",
        "red_flags": [],
        "next": coach._next_sessions_md(run_done),
    }
    coach._send_postworkout_telegram(pw)

    wr = {
        "headline": "<LLM: כותרת השבוע>",
        "compass": "<LLM: מצפן מול היעד>",
        "week_analysis": "<LLM: ניתוח>",
        "wins": ["<LLM: חוזקה>"],
        "concerns": ["<LLM: דגש>"],
        "plan_summary": [f"{s['date'][5:]}: {s.get('name') or 'כוח ' + s.get('key','')}"
                          for s in store.load_week_plan().get("sessions", [])][:7],
        "focus": "<LLM: דגש>", "tip": "<LLM: טיפ>",
    }
    coach._send_weekly_telegram(wr, safety_messages=[], needs_review=False)

    for i, m in enumerate(SENT, 1):
        print(f"\n{'='*20} הודעה {i} {'='*20}")
        print(m.replace("<b>", "").replace("</b>", ""))


if __name__ == "__main__":
    main()
