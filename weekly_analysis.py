"""
weekly_analysis.py — שלב 1 של הסיכום השבועי: ניתוח דטרמיניסטי מקדים (ללא LLM).

מחשב "עובדות קשות" מתוך מקבץ ה-metrics הקיים (build_metrics) + compliance, כדי שה-LLM
(Opus) יסתמך עליהן ולא ימציא ("מתמטיקה וירטואלית"). כל פונקציה מחזירה dict עם הערכים
+ שדה verdict טקסטואלי קצר בעברית.

הפונקציה המרכזית `rank_weekly_priorities` מדרגת את הדומיינים לפי דחיפות ומחזירה את
"כותרת השבוע" — המנגנון שהופך את הדגש האדפטיבי לקונקרטי.

מודול טהור: לא מייבא את coach.py (שמתחבר לגרמין ב-import), כדי שיהיה נבדק-ביחידה.
"""

import math

# ── VDOT (Jack Daniels) — עותק מקומי כדי לא לייבא את coach.py ──────────────────

def vdot_from_pace(distance_km: float, pace_sec_per_km: float) -> float | None:
    """VDOT ממאמץ בודד (מרחק + קצב). זהה ל-coach._vdot_from_pace."""
    if not distance_km or not pace_sec_per_km:
        return None
    t_min = pace_sec_per_km * distance_km / 60.0
    if t_min <= 0:
        return None
    v = distance_km * 1000.0 / t_min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v ** 2
    pct = (0.8 + 0.1894393 * math.exp(-0.012778 * t_min)
           + 0.2989558 * math.exp(-0.1932605 * t_min))
    return round(vo2 / pct, 1) if pct else None


def parse_pace_to_sec(pace_str) -> int | None:
    """'5:20/km' או '5:20' → 320 שניות/ק\"מ."""
    if not pace_str:
        return None
    s = str(pace_str).split("/")[0].strip()
    if ":" not in s:
        return None
    try:
        m, sec = s.split(":")
        return int(m) * 60 + int(sec)
    except (ValueError, TypeError):
        return None


def required_vdot_for_race(macro: dict) -> dict:
    """ה-VDOT הנדרש כדי לרוץ את המרוץ בקצב היעד (המצפן)."""
    race = (macro or {}).get("race") or {}
    dist = race.get("distance_km")
    goal_sec = parse_pace_to_sec(race.get("goal_pace"))
    if not dist or not goal_sec:
        return {"available": False}
    vdot = vdot_from_pace(dist, goal_sec)
    return {
        "available": vdot is not None,
        "required_vdot": vdot,
        "race": f"{dist}K @ {race.get('goal_pace')}",
    }


# ── ניתוחי תת-דומיין ───────────────────────────────────────────────────────────

def compliance_detailed(compliance: dict, metrics: dict) -> dict:
    """מתוכנן מול בוצע + האם אימון איכות בוצע (dominant_zone≥4)."""
    out = dict(compliance or {})
    runs = (metrics.get("last_week") or {}).get("runs") or []
    quality_done = any((r.get("dominant_zone") or 0) >= 4 for r in runs)
    out["quality_done"] = quality_done
    lvl = out.get("compliance_level")
    if not out.get("available", True) and "available" in out:
        out["verdict"] = out.get("reason", "אין נתון ציות")
    elif lvl == "נמוך":
        out["verdict"] = "ציות נמוך — לא לקפוץ עומס, לבנות קרוב לבוצע"
    elif lvl == "חלקי":
        out["verdict"] = "ציות חלקי — התקדמות מתונה בלבד"
    elif lvl == "מלא":
        out["verdict"] = "ציות מלא — אפשר להתקדם בזהירות"
    else:
        out["verdict"] = "ציות לא ידוע"
    if not quality_done:
        out["verdict"] += " · אימון האיכות לא בוצע"
    return out


def zone_balance_verdict(zones: dict) -> dict:
    """איזון 80/20 + דגל 'no man's land' (Z3>15%)."""
    z = zones or {}
    if not z.get("available"):
        return {"available": False, "verdict": "אין נתוני זונות"}
    easy = z.get("easy_pct", 0)
    z3 = z.get("z3_pct", 0)
    hard = z.get("hard_pct", 0)
    no_mans_land = z3 > 15
    if no_mans_land:
        verdict = f"דשדוש ב-Z3 ({z3}%) — לחדד את הקיטוב: קל יותר קל, קשה יותר קשה"
    elif easy >= 80:
        verdict = f"איזון פולארי טוב (קל {easy}%)"
    else:
        verdict = f"מעט מדי קל ({easy}% מול 80%) — להוסיף נפח Z2"
    return {"available": True, "easy_pct": easy, "z3_pct": z3, "hard_pct": hard,
            "no_mans_land": no_mans_land, "verdict": verdict}


def threshold_progress(metrics: dict, macro: dict) -> dict:
    """המצפן: VDOT נוכחי מול הנדרש למרוץ + מצב הסף."""
    f4 = metrics.get("fitness_4week") or {}
    req = required_vdot_for_race(macro)
    cur_vdot = f4.get("vdot")
    out = {
        "current_vdot": cur_vdot,
        "vdot_basis": f4.get("vdot_basis"),
        "threshold_pace": f4.get("threshold_pace"),
        "required_vdot": req.get("required_vdot"),
    }
    if cur_vdot and req.get("required_vdot"):
        gap = round(req["required_vdot"] - cur_vdot, 1)
        out["vdot_gap"] = gap
        if gap <= 0:
            out["verdict"] = f"VDOT {cur_vdot} ≥ נדרש {req['required_vdot']} — בכושר למרוץ ✓"
            out["on_track"] = True
        else:
            out["verdict"] = f"פער VDOT {gap} (נוכחי {cur_vdot} → נדרש {req['required_vdot']}) — הסף הוא המנוע"
            out["on_track"] = False
    else:
        out["verdict"] = "אין מספיק נתונים ל-VDOT (פחות מ-4 שבועות?)"
        out["on_track"] = None
    return out


def load_trajectory(metrics: dict) -> dict:
    """verdict על העומס: ACWR, ramp, monotony, TSB."""
    load = metrics.get("load") or {}
    acwr = load.get("acwr")
    ramp = load.get("ramp_rate_4w", 0) or 0
    mono = (metrics.get("monotony") or {}).get("monotony")
    tsb = load.get("tsb")
    flags = []
    sev_rank = 0  # 0=🟢 1=🟡 2=🔴
    if acwr is not None and acwr > 1.5:
        flags.append(f"ACWR {acwr} >1.5 (אזור סיכון Gabbett)"); sev_rank = max(sev_rank, 2)
    elif acwr is not None and acwr > 1.3:
        flags.append(f"ACWR {acwr} מתקרב לגבול"); sev_rank = max(sev_rank, 1)
    if ramp > 10:
        flags.append(f"ramp {ramp} >10/שבוע (עלייה חדה)"); sev_rank = max(sev_rank, 1)
    if mono and mono > 2.0:
        flags.append(f"monotony {mono} >2.0 (חוסר גיוון)"); sev_rank = max(sev_rank, 1)
    severity = {0: "🟢", 1: "🟡", 2: "🔴"}[sev_rank]
    verdict = " · ".join(flags) if flags else f"עומס מאוזן (ACWR {acwr}, TSB {tsb})"
    return {"acwr": acwr, "ramp": ramp, "monotony": mono, "tsb": tsb,
            "severity": severity, "verdict": verdict}


def macro_adherence(metrics: dict, macro: dict) -> dict:
    """נפח בפועל מול יעד המאקרו."""
    m = macro or {}
    target = m.get("target_km")
    actual = (metrics.get("last_week") or {}).get("total_km", 0)
    out = {"phase": m.get("phase"), "week_num": m.get("week_num"),
           "target_km": target, "actual_km": actual,
           "deload": m.get("deload"), "gate": m.get("gate")}
    if target:
        ratio = actual / target if target else 0
        if ratio >= 0.9:
            out["verdict"] = f"בנפח המאקרו ({actual}/{target} ק\"מ)"
            out["status"] = "on"
        elif ratio >= 0.7:
            out["verdict"] = f"מעט מתחת ליעד ({actual}/{target} ק\"מ)"
            out["status"] = "under"
        else:
            out["verdict"] = f"הרבה מתחת ליעד ({actual}/{target} ק\"מ)"
            out["status"] = "under"
    else:
        out["verdict"] = "אין יעד מאקרו (טרם החל/הסתיים)"
        out["status"] = "none"
    return out


def strength_balance(metrics: dict) -> dict:
    """ספירת אימוני כוח + רענן."""
    s = metrics.get("strength") or {}
    cnt = s.get("session_count", 0)
    out = {"session_count": cnt, "days_since_last": s.get("days_since_last")}
    if cnt >= 4:
        out["verdict"] = f"כוח עקבי ({cnt} אימונים/שבוע)"
    elif cnt >= 2:
        out["verdict"] = f"כוח חלקי ({cnt}/שבוע) — להשלים PPL"
    else:
        out["verdict"] = f"כוח חסר ({cnt}/שבוע) — קריטי למניעת פציעות ברך/קרסול"
    return out


def detect_macro_reality_conflict(metrics: dict, macro: dict,
                                  compliance: dict) -> dict:
    """
    קונפליקט = המאקרו דורש עליית נפח אבל המציאות מסויגת
    (ציות נמוך / ACWR מטפס / מונוטוניות גבוהה).
    מחזיר את שני היעדים: macro_target מול conservative_target.
    """
    m = macro or {}
    target = m.get("target_km")
    actual = (metrics.get("last_week") or {}).get("total_km", 0) or 0
    load = metrics.get("load") or {}
    acwr = load.get("acwr")
    lvl = (compliance or {}).get("compliance_level")

    macro_wants_increase = bool(target and target > actual * 1.1)
    reality_cautious = (lvl == "נמוך"
                        or (acwr is not None and acwr > 1.3)
                        or bool(m.get("deload")))

    conflict = macro_wants_increase and reality_cautious
    # יעד שמרני: max(+15%, +3 ק"מ) מעל הבוצע בפועל — תואם את שכבת הבטיחות
    conservative = round(max(actual * 1.15, actual + 3), 1) if actual else target
    reasons = []
    if lvl == "נמוך":
        reasons.append("ציות נמוך בשבוע שעבר")
    if acwr is not None and acwr > 1.3:
        reasons.append(f"ACWR {acwr} מטפס")
    if m.get("deload"):
        reasons.append("שבוע deload")
    return {
        "conflict": conflict,
        "macro_target_km": target,
        "conservative_target_km": conservative,
        "actual_km": actual,
        "reasons": reasons,
        "summary": (f"המאקרו דורש {target} ק\"מ אבל "
                    + ", ".join(reasons) + f" → שמרני {conservative} ק\"מ")
                   if conflict else "אין קונפליקט מאקרו↔מציאות",
    }


# ── דירוג עדיפויות — "כותרת השבוע" (הדגש האדפטיבי) ─────────────────────────────

def rank_weekly_priorities(metrics: dict, analyses: dict) -> dict:
    """
    מדרג דומיינים לפי דחיפות ומחזיר את כותרת השבוע (הדומיין מספר 1).
    סדר: דגל 🔴 > ACWR>1.5 > קיפאון סף ב-Build > חוסר-איזון zones > פער ציות > פער כוח.
    """
    ranked = []

    red = [f for f in (metrics.get("red_flags") or []) if f.get("severity") == "🔴"]
    if red:
        ranked.append(("red_flag", 100,
                       f"🔴 דגל אדום: {red[0].get('flag')} — {red[0].get('detail')}"))

    load = analyses.get("load_trajectory", {})
    if load.get("severity") == "🔴":
        ranked.append(("load", 90, f"⚠️ עומס: {load.get('verdict')}"))

    thr = analyses.get("threshold_progress", {})
    phase = (metrics.get("macro") or {}).get("phase")
    if thr.get("on_track") is False and phase == "Build":
        ranked.append(("threshold", 80,
                       f"🎯 מיקוד סף: {thr.get('verdict')}"))

    zb = analyses.get("zone_balance", {})
    if zb.get("no_mans_land"):
        ranked.append(("zones", 70, f"📊 איזון: {zb.get('verdict')}"))

    comp = analyses.get("compliance", {})
    if comp.get("compliance_level") == "נמוך":
        ranked.append(("compliance", 60,
                       f"📉 ציות: {comp.get('verdict')}"))

    if thr.get("on_track") is False and phase != "Build":
        ranked.append(("threshold", 55, f"🎯 סף: {thr.get('verdict')}"))

    st = analyses.get("strength_balance", {})
    if st.get("session_count", 99) < 2:
        ranked.append(("strength", 50, f"💪 כוח: {st.get('verdict')}"))

    ranked.sort(key=lambda x: x[1], reverse=True)
    if ranked:
        headline = ranked[0][2]
        domain = ranked[0][0]
    else:
        # ברירת מחדל: הכל תקין — מובילים עם המצפן
        headline = f"✅ על המסלול. {thr.get('verdict', '')}".strip()
        domain = "on_track"
    return {"headline": headline, "headline_domain": domain,
            "ranked": [{"domain": d, "score": s, "text": t} for d, s, t in ranked]}


def build_weekly_analysis(metrics: dict, compliance: dict) -> dict:
    """אורקסטרציה של שלב 1 — מחזיר את כל הניתוחים + כותרת + קונפליקט."""
    macro = metrics.get("macro") or {}
    analyses = {
        "compliance": compliance_detailed(compliance, metrics),
        "zone_balance": zone_balance_verdict(metrics.get("zones")),
        "threshold_progress": threshold_progress(metrics, macro),
        "load_trajectory": load_trajectory(metrics),
        "macro_adherence": macro_adherence(metrics, macro),
        "strength_balance": strength_balance(metrics),
    }
    analyses["conflict"] = detect_macro_reality_conflict(
        metrics, macro, analyses["compliance"])
    analyses["priority"] = rank_weekly_priorities(metrics, analyses)
    return analyses
