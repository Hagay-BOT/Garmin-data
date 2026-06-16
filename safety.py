# -*- coding: utf-8 -*-
"""
safety.py — שכבת בטיחות דטרמיניסטית בין ה-LLM לבין הספורטאי.

אין כאן שום קריאה ל-LLM. כל הכללים ניתנים-לבדיקה (pure functions) ומהווים את קו ההגנה
האחרון לפני ש-week_plan.json נכתב לדיסק וזורם ליומן/גרמין.

מדיניות (לפי החלטות המשתמש):
  • נפח שבועי — תקרה רכה: clamp אוטומטי ל-max(prev*1.15, prev+3) ק"מ. תמיד עם התראה.
  • Deload — אם המאקרו מסמן deload: יעד ≈ prev*0.70 (−30%). חיתוך עמוק יותר רק עם גורם מצדיק.
  • ימי איכות צמודים — לא משנים בשקט: מתריעים, מסמנים needs_review, ומציעים חלופות. הספורטאי מחליט.
  • ולידציה מבנית — דחייה קשה (לא clamp): אם התוכנית פגומה מבנית, מחזירים None ולא כותבים.
  • ACWR — הסלמה בלבד, אף פעם לא חוסם ייצור: >1.5 התראה · >1.7 התראה חמורה + needs_review.
"""
from __future__ import annotations

import re
from datetime import date

# ── סף וקבועים ────────────────────────────────────────────────────────────────
VOLUME_CAP_FACTOR = 1.15        # +15% מהשבוע הקודם
VOLUME_FLOOR_KM = 3.0           # ...אבל תמיד מתירים לפחות +3 ק"מ (שבועות נפח נמוך)
DELOAD_TARGET_FACTOR = 0.70     # deload = −30% כברירת מחדל
DELOAD_DEEP_FACTOR = 0.55       # חיתוך עמוק רק עם גורם מצדיק (מחלה/פציעה/עייפות/אחרי-מרוץ)
ACWR_WARN = 1.5
ACWR_SEVERE = 1.7
VALID_STEP_KINDS = {"warmup", "interval", "cooldown"}
MAX_TOTAL_SECONDS = 4 * 3600    # אימון בודד לא יעלה על 4 שעות
MIN_TOTAL_SECONDS = 5 * 60      # ...ולא יפחת מ-5 דקות
HARD_SUBTYPES = {"quality", "long"}
DEEP_DELOAD_FACTORS = {"illness", "injury", "fatigue", "post_race",
                       "מחלה", "פציעה", "עייפות", "אחרי_מרוץ"}


def _run_sessions(plan: dict) -> list[dict]:
    return [s for s in plan.get("sessions", []) if s.get("type") == "run"]


def _total_km(plan: dict) -> float:
    return round(sum(float(s.get("est_km") or 0) for s in _run_sessions(plan)), 1)


def _scale_run(session: dict, factor: float) -> None:
    """מקטין run בודד (est_km + seconds של כל step) ב-factor. עובד in-place."""
    session["est_km"] = round(float(session.get("est_km") or 0) * factor, 1)
    for st in session.get("steps", []):
        st["seconds"] = int(round(float(st.get("seconds") or 0) * factor))


def validate_structure(plan: dict) -> list[str]:
    """ולידציה מבנית קשה. מחזיר רשימת שגיאות (ריקה = תקין)."""
    errors: list[str] = []
    sessions = plan.get("sessions")
    if not sessions:
        return ["INVALID: אין sessions בתוכנית"]

    prev_date: date | None = None
    for s in sessions:
        d = s.get("date", "")
        try:
            cur = date.fromisoformat(d)
        except Exception:
            errors.append(f"INVALID: תאריך לא תקין '{d}'")
            cur = None
        if cur and prev_date and cur < prev_date:
            errors.append(f"INVALID: תאריכים לא ממוינים סביב {d}")
        if cur:
            prev_date = cur

        if s.get("type") != "run":
            continue

        if float(s.get("est_km") or 0) <= 0:
            errors.append(f"INVALID: est_km לא חיובי בריצה {d}")
        pace = s.get("pace")
        if pace is not None and not re.match(r"^\d{1,2}:\d{2}$", str(pace)):
            errors.append(f"INVALID: פורמט קצב שגוי '{pace}' בריצה {d}")

        steps = s.get("steps") or []
        if not steps:
            errors.append(f"INVALID: אין steps בריצה {d}")
        total = 0
        for st in steps:
            if st.get("kind") not in VALID_STEP_KINDS:
                errors.append(f"INVALID: סוג step לא מוכר '{st.get('kind')}' בריצה {d}")
            secs = float(st.get("seconds") or 0)
            if secs <= 0:
                errors.append(f"INVALID: step עם משך לא חיובי בריצה {d}")
            total += secs
        if steps and not (MIN_TOTAL_SECONDS <= total <= MAX_TOTAL_SECONDS):
            errors.append(f"INVALID: משך כולל לא סביר ({int(total)} שנ') בריצה {d}")
    return errors


def _check_consecutive_hard(plan: dict) -> tuple[list[str], list[str]]:
    """מאתר ימי איכות/ארוכה צמודים. מחזיר (warnings, suggestions). לא משנה את התוכנית."""
    hard = sorted(
        [s for s in _run_sessions(plan) if s.get("subtype") in HARD_SUBTYPES],
        key=lambda s: s.get("date", ""),
    )
    warnings: list[str] = []
    suggestions: list[str] = []
    for a, b in zip(hard, hard[1:]):
        try:
            da, db = date.fromisoformat(a["date"]), date.fromisoformat(b["date"])
        except Exception:
            continue
        if (db - da).days == 1:
            warnings.append(
                f"⚠️ אימונים עצימים צמודים: {a.get('subtype')} ב-{a['date']} ו-{b.get('subtype')} "
                f"ב-{b['date']} — נדרשות ≥48 שעות התאוששות בין מאמצים קשים."
            )
            suggestions.append(
                f"שקול: (א) להחליף ימים, (ב) להנמיך עצימות של {b['date']}, "
                f"או (ג) להזיז את הריצה הארוכה ליום אחר."
            )
    return warnings, suggestions


def clamp_and_validate_week_plan(
    full_plan: dict,
    prev_week_km: float,
    macro: dict | None = None,
    acwr: float | None = None,
    factors: set[str] | None = None,
) -> tuple[dict | None, list[str], list[str], bool]:
    """
    שכבת הבטיחות המרכזית.

    מחזיר: (plan_or_None, adjustments, warnings, needs_review)
      • plan_or_None — התוכנית (אולי מוקטנת). None = נדחתה מבנית, אסור לכתוב.
      • adjustments  — שינויים אוטומטיים שבוצעו (clamp נפח/deload).
      • warnings     — התראות לעיון אנושי בשער האישור.
      • needs_review — האם נדרש אישור מפורש (ימי איכות צמודים / ACWR חמור).
    """
    macro = macro or {}
    factors = factors or set()
    adjustments: list[str] = []
    warnings: list[str] = []
    needs_review = False

    # 1) ולידציה מבנית — דחייה קשה
    errors = validate_structure(full_plan)
    if errors:
        return None, [], errors, True

    total = _total_km(full_plan)

    # 2) תקרת נפח / deload — clamp אוטומטי
    is_deload = bool(macro.get("deload"))
    cap: float | None = None
    if prev_week_km and prev_week_km > 0:
        if is_deload:
            deep = bool(factors & DEEP_DELOAD_FACTORS)
            target_factor = DELOAD_DEEP_FACTOR if deep else DELOAD_TARGET_FACTOR
            cap = round(prev_week_km * target_factor, 1)
        else:
            cap = round(max(prev_week_km * VOLUME_CAP_FACTOR, prev_week_km + VOLUME_FLOOR_KM), 1)
    elif total > 0:
        warnings.append("אין נתון נפח לשבוע הקודם — לא ניתן לאמת התקדמות נפח.")

    if cap is not None and total > cap and total > 0:
        factor = cap / total
        for s in _run_sessions(full_plan):
            _scale_run(s, factor)
        pct = round((1 - factor) * 100)
        if is_deload:
            adjustments.append(f"שבוע deload: נפח הופחת ב-{pct}% ל-{cap} ק\"מ (מ-{total}).")
        else:
            adjustments.append(f"נפח הופחת ב-{pct}% ל-{cap} ק\"מ (מ-{total}) לעמידה במגבלת התקדמות.")
    elif is_deload and cap is not None:
        warnings.append(f"שבוע deload — יעד נפח ≈ {cap} ק\"מ (התוכנית כבר בטווח).")

    # 3) ימי איכות צמודים — התראה + דגל בלבד, ללא שינוי מבנה
    hard_warn, hard_sugg = _check_consecutive_hard(full_plan)
    if hard_warn:
        warnings.extend(hard_warn)
        warnings.extend(hard_sugg)
        needs_review = True

    # 4) ACWR — הסלמה בלבד, לעולם לא חוסם
    if acwr is not None:
        if acwr > ACWR_SEVERE:
            warnings.append(f"🔴 ACWR={acwr} חורג מהסף החמור ({ACWR_SEVERE}) — נדרש אישור מפורש.")
            needs_review = True
        elif acwr > ACWR_WARN:
            warnings.append(f"🟡 ACWR={acwr} מעל הסף המומלץ ({ACWR_WARN}) — שים לב לעומס.")

    return full_plan, adjustments, warnings, needs_review


def build_plan_metadata(adjustments: list[str], warnings: list[str],
                        needs_review: bool, generated_by: str = "LLM") -> dict:
    """בלוק שקיפות שמצורף ל-week_plan.json — מסביר אילו התערבויות בטיחות בוצעו ולמה."""
    return {
        "generated_by": generated_by,
        "approval_required": True,
        "needs_review": bool(needs_review),
        "safety_adjustments": list(adjustments),
        "warnings": list(warnings),
    }
