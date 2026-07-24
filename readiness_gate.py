# -*- coding: utf-8 -*-
"""
readiness_gate.py — שער-מוכנות דטרמיניסטי לאימוני-איכות (T5 / M3.2).

הרקע: ביום-סף עם 3.5 שעות שינה — הגיא תפס את זה, לא המערכת, למרות שנתוני השינה
קיימים. השער הזה בודק בבוקר יום-איכות/לונג: אם המוכנות נמוכה (ציון-שינה / סוללת-גוף)
— שולח הצעה קצרה בטלגרם להחליף לקל/מנוחה. **לא משנה תוכנית לבד** — רק מציע; הגיא
עונה 'החלף' (מטופל ע"י לולאת-העריכה הקיימת) או מתעלם.

דטרמיניסטי לחלוטין — בלי LLM. רץ מתוך ה-watcher הקיים (coach-postworkout), פעם ביום.
"""
import datetime

import athlete
import store

HARD_SUBTYPES = ("quality", "long")


def evaluate(session: dict | None, readiness_today: dict | None) -> tuple[bool, str]:
    """(should_flag, reason). דגל רק אם: היום אימון איכות/לונג **וגם** מוכנות נמוכה.
    חסר-נתונים = לא מדגמן (שמרני — לא מטריד סתם)."""
    if not session or session.get("subtype") not in HARD_SUBTYPES:
        return False, ""
    r = readiness_today or {}
    score = r.get("sleep_score")
    battery = r.get("body_battery_morning")
    reasons = []
    if isinstance(score, (int, float)) and 0 < score < athlete.SLEEP_SCORE_MIN_FOR_QUALITY:
        reasons.append(f"ציון-שינה {score}")
    if isinstance(battery, (int, float)) and 0 < battery < athlete.BODY_BATTERY_MIN_FOR_QUALITY:
        reasons.append(f"סוללת-גוף {battery}")
    return (bool(reasons), " · ".join(reasons))


def _today_session(plan: dict, today_iso: str) -> dict | None:
    runs = [s for s in plan.get("sessions", [])
            if s.get("date") == today_iso and s.get("type") == "run"]
    return runs[0] if runs else None


def _today_readiness(metrics_readiness: dict, today_iso: str) -> dict | None:
    return (metrics_readiness or {}).get(today_iso)


def main(today: datetime.date | None = None) -> None:
    import coach
    import telegram_notify as tg

    today = today or datetime.date.today()
    today_iso = today.isoformat()

    # מונע ספאם: מודיע פעם אחת ליום בלבד
    gate_state = store.load_weekly_state()
    if gate_state.get("readiness_flagged_date") == today_iso:
        print("שער-מוכנות: כבר הודיע היום — מדלג.")
        return

    plan = store.load_week_plan()
    session = _today_session(plan, today_iso)
    if not session:
        print("שער-מוכנות: אין ריצה מתוכננת היום.")
        return

    metrics = coach.build_metrics(coach.load_data())
    readiness = _today_readiness(metrics.get("readiness", {}), today_iso)
    flag, reason = evaluate(session, readiness)
    if not flag:
        print(f"שער-מוכנות: {session.get('name','?')} — מוכנות תקינה, אין התראה.")
        return

    name = session.get("name", "אימון")
    msg = (f"🌅 <b>שער מוכנות</b>\n\n"
           f"היום מתוכנן <b>{name}</b> (אימון איכות), אבל המוכנות נמוכה — {reason}.\n"
           f"אימון איכות על מוכנות נמוכה = עומס בלי אדפטציה + סיכון. "
           f"מציע להחליף ל<b>ריצה קלה או מנוחה</b> ולדחות את האיכות ליום עם שינה טובה.\n\n"
           f"השב <b>'החלף'</b> ואעדכן, או התעלם אם אתה מרגיש טוב. 💪")
    mid = tg.send_message(msg)
    if mid:
        gate_state["readiness_flagged_date"] = today_iso
        store.save_weekly_state(gate_state)
        print(f"⚠️ שער-מוכנות התריע ({reason}) — נשלח לטלגרם (message_id={mid}).")


if __name__ == "__main__":
    main()
