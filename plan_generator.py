# -*- coding: utf-8 -*-
"""
plan_generator.py — מחולל התוכנית השבועית הדטרמיניסטי (M3.3 + M10).

מחליף את ה-LLM בבניית ה-WEEK_PLAN: תכנון-שבוע הוא בעיה פתורה של חוקים —
מאקרו (נפח/לונג/איכות/deload) × כללי-המבנה של הגיא × המשכיות-כוח × אילוצי-זמינות.
ה-LLM נשאר בקצוות: נרטיב הסיכום, עריכה-בטלגרם, ופרשנות זמינות מורכבת.

כללי-המבנה (מקור: user_profile + החלטות):
  • שבת = ריצת הנפח (לונג).
  • איכות באמצע-שבוע, ≥48ש' מהלונג. אחרי אינטרוולים — בלי ריצה למחרת.
  • רגליים (C) לא צמוד לאיכות/לונג; היום שאחרי C = ריצת התאוששות Z1 קצרה.
  • כוח: A/B ×2 (עליון), C ×1. השבוע מתחיל באימון הבא ברוטציה (המשכיות).
  • יום עמוס (זמינות) = בלי אימונים בו; הק"מ מתפזר לימים אחרים, לא נחתך.

הפלט: dict "raw" בסכמת extract_week_plan — עובר את materialize+safety הקיימים.
"""
import datetime
import re

import athlete

WEEKDAYS_HE = {"ראשון": 6, "שני": 0, "שלישי": 1, "רביעי": 2,
               "חמישי": 3, "שישי": 4, "שבת": 5}  # python weekday()

_BUSY_WORDS = r"(עמוס|נסיעה|לא (אוכל|יכול|אהיה|נמצא)|אין לי|מילואים|חופש בלי|טס|עסוק)"
_PREFER_WORDS = r"(מעדיף|עדיף|רוצה|בא לי|נוח לי)"
# סוג-אימון שניתן להעדיף יום עבורו → מפתח פנימי
_PREFER_KINDS = {"לונג": "long", "ארוכה": "long", "נפח": "long",
                 "איכות": "quality", "סף": "quality", "טמפו": "quality",
                 "אינטרוול": "quality"}


def parse_availability(text: str) -> dict:
    """טקסט-חופשי → {'busy_days': [...], 'prefer': {'long': wd, 'quality': wd}, 'raw': text}.
    דטרמיניסטי ושמרני: יום=עמוס רק במשפט עם מילת-עומס; העדפה=רק במשפט עם מילת-העדפה
    + סוג-אימון + יום. כל מה שלא זוהה עדיין מגיע ל-LLM דרך raw."""
    busy: set = set()
    prefer: dict = {}
    if text:
        for sentence in re.split(r"[.,;\n]| ו(?=[א-ת])", text):
            days = [wd for name, wd in WEEKDAYS_HE.items() if name in sentence]
            if re.search(_BUSY_WORDS, sentence):
                busy.update(days)
            # העדפה: מילת-העדפה + סוג-אימון מוכר + יום יחיד ומפורש
            if re.search(_PREFER_WORDS, sentence) and len(days) == 1:
                for kw, kind in _PREFER_KINDS.items():
                    if kw in sentence:
                        prefer.setdefault(kind, days[0])
                        break
    # יום שגם עמוס וגם מועדף — העומס גובר (בטיחות לפני העדפה)
    prefer = {k: v for k, v in prefer.items() if v not in busy}
    return {"busy_days": sorted(busy), "prefer": prefer, "raw": (text or "").strip()}


def _dates_for_week(week_start: datetime.date) -> dict:
    """weekday() → ISO date עבור שבוע שמתחיל בראשון."""
    return {(week_start + datetime.timedelta(days=i)).weekday():
            (week_start + datetime.timedelta(days=i)).isoformat() for i in range(7)}


def _next_upper(last: str) -> str:
    return {"A": "B", "B": "A"}.get(last, "A")


def generate(week_start: datetime.date, macro: dict,
             last_strength_seq: list | None = None,
             availability: dict | None = None) -> dict:
    """בונה WEEK_PLAN דטרמיניסטי. week_start חייב להיות יום ראשון."""
    assert week_start.weekday() == 6, "week_start חייב להיות ראשון (עוגן-השבוע)"
    busy = set((availability or {}).get("busy_days", []))
    prefer = (availability or {}).get("prefer", {})
    dates = _dates_for_week(week_start)
    target_km = float(macro.get("target_km") or 25)
    long_km = min(float(macro.get("long_run_km") or 9), athlete.LONG_RUN_CAP_KM)
    deload = bool(macro.get("deload"))

    def free(*wds):
        """היום הפנוי הראשון מהרשימה (weekday values)."""
        return next((w for w in wds if w not in busy), None)

    sessions, used_run_days = [], set()

    def add_run(wd, subtype, name, km, steps_hint=None, desc=""):
        if wd is None:
            return False
        sessions.append({"date": dates[wd], "type": "run", "subtype": subtype,
                         "name": name, "est_km": round(km, 1), "desc": desc,
                         "pace": steps_hint or "6:50"})
        used_run_days.add(wd)
        return True

    # 1. לונג — ברירת-מחדל שבת (עוגן הנפח); שבת עמוסה → שישי → חמישי.
    #    T2: העדפת-לונג ("מעדיף לונג בשישי") גוברת אם היום פנוי.
    long_wd = free(prefer["long"], 5, 4, 3) if "long" in prefer else free(5, 4, 3)
    add_run(long_wd, "long", f"🏃 ריצת נפח — {long_km:g} ק\"מ Z2",
            long_km, "6:50", "לפי דופק Z2 (עד 141), לא קצב.")

    # 2. איכות — שני (≥48ש' מהלונג); עמוס → ראשון/שלישי. deload → איכות קלה.
    #    T2: העדפת-איכות גוברת אם פנויה ורחוקה ≥48ש' מהלונג.
    is_intervals = "אינטרוול" in str(macro.get("quality", "")) or "VO2" in str(macro.get("quality", ""))
    q_km = 5.0 if deload else 6.0
    _q_pref = prefer.get("quality")
    if _q_pref is not None and _q_pref not in busy and _q_pref != long_wd \
            and (long_wd is None or abs((long_wd - _q_pref)) % 7 >= 2):
        q_wd = _q_pref
    else:
        q_wd = free(0, 6, 1)
    q_name = ("🏃 " + str(macro.get("quality") or "טמפו")).strip()
    add_run(q_wd, "quality", q_name, q_km, athlete.THRESHOLD_PACE,
            f"איכות לפי המאקרו: {macro.get('quality', 'טמפו')}. + strides בסיום.")

    # 3. רגליים (C) — אמצע-שבוע, לא צמוד לאיכות ולא יום-לפני-הלונג.
    legs_candidates = [w for w in (2, 1, 3) if w not in busy
                       and w != q_wd
                       and (long_wd is None or (long_wd - w) % 7 >= 2)]
    legs_wd = legs_candidates[0] if legs_candidates else None
    if legs_wd is not None:
        sessions.append({"date": dates[legs_wd], "type": "strength", "key": "C"})

    # 4. היום שאחרי C = ריצת התאוששות Z1 קצרה (אם פנוי ולא יום-הלונג).
    if legs_wd is not None:
        rec_wd = (legs_wd + 1) % 7
        if rec_wd not in busy and rec_wd != long_wd and rec_wd not in used_run_days:
            add_run(rec_wd, "easy", "🚶 התאוששות Z1 — 4 ק\"מ (אחרי רגליים)",
                    4.0, "7:10", "קל מאוד/הליכה-ריצה. אחרי יום רגליים.")

    # 5. אחרי אינטרוולים — בלי ריצה למחרת.
    no_run_day = (q_wd + 1) % 7 if (is_intervals and q_wd is not None) else None

    # 6. נפח קל — הק"מ שנותר מתפזר על ימים פנויים (לא נחתך!).
    #    T1: כל ריצה-קלה חסומה ב-EASY_RUN_CAP_KM (לא "מתנפחת" ל-9+ כשיש רק יום פנוי אחד).
    gen_notes: list[str] = []
    rec_km = sum(s["est_km"] for s in sessions
                 if s.get("type") == "run" and "התאוששות" in s.get("name", ""))
    remaining = max(0.0, target_km - long_km - q_km - rec_km)
    easy_days = [w for w in (6, 1, 3, 4) if w not in busy and w not in used_run_days
                 and w != no_run_day and w != legs_wd][:2]
    if easy_days:
        per = round(remaining / len(easy_days), 1)
        for wd in easy_days:
            km = min(per, athlete.EASY_RUN_CAP_KM)
            if km >= 3:
                add_run(wd, "easy", f"🏃 קל Z2 — {km:g} ק\"מ", km, "6:50",
                        f"ריצת בסיס לפי דופק Z2 ({athlete.EASY_PACE_RANGE}).")

    # T1: אם ימים עמוסים חסמו נפח — דיווח מפורש (מגיע לטלגרם דרך הדוח), לא אובדן שקט.
    placed_km = round(sum(s["est_km"] for s in sessions if s["type"] == "run"), 1)
    if target_km > 0 and placed_km < target_km * 0.9:
        gen_notes.append(f"⚠️ נפח בפועל {placed_km:g} מתוך יעד {target_km:g} ק\"מ — "
                         f"ימים פנויים לא הספיקו (אילוצי-זמינות). לא נחתך במכוון.")

    # 7. כוח עליון A/B ×2 — רוטציה ממשיכה מהשבוע שעבר, לא באותו יום כמו C.
    last_upper = next((k for k in reversed(last_strength_seq or []) if k in ("A", "B")), "B")
    order = [_next_upper(last_upper)]
    for _ in range(3):
        order.append(_next_upper(order[-1]))
    upper_days = [w for w in (6, 0, 3, 4) if w not in busy and w != legs_wd][:4]
    for wd, key in zip(upper_days, order):
        sessions.append({"date": dates[wd], "type": "strength", "key": key})

    sessions.sort(key=lambda s: (s["date"], 0 if s["type"] == "run" else 1))
    return {
        "week_of": week_start.isoformat(),
        "macro_week": macro.get("week_num"),
        "phase": macro.get("phase", ""),
        "notes": ("נבנה דטרמיניסטית (plan_generator). "
                  + (f"אילוצים: {(availability or {}).get('raw')} " if (availability or {}).get("raw") else "")
                  + " ".join(gen_notes)),
        "sessions": sessions,
    }
