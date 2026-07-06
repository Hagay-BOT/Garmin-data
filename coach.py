"""
Running Coach AI Agent
Reads data.json, computes training metrics, and generates a Hebrew coaching report via Claude.
"""

import json
import os
import sys

# Ensure UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime, date, timedelta
from pathlib import Path
import anthropic
import athlete


BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
KB_DIR = BASE_DIR / "knowledge_base"
REPORT_FILE = BASE_DIR / "coach_report.md"
HISTORY_FILE = BASE_DIR / "coach_history.json"
MACRO_FILE = BASE_DIR / "macro_plan.json"

HISTORY_WEEKS_TO_KEEP = 52
HISTORY_WEEKS_TO_INJECT = 4

# Activity types counted as "a run" — includes treadmill and trail runs
RUN_TYPES = ("running", "treadmill_running", "trail_running")


# ── Load data ────────────────────────────────────────────────────────────────

def load_data() -> dict:
    """טוען data.json. עמיד לקובץ חסר/פגום — מחזיר מבנה ריק בטוח במקום לקרוס."""
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"⚠️  load_data: כשל בקריאת {DATA_FILE} ({e}) — מחזיר מבנה ריק.")
        return {"activities": [], "daily": {}}


# ── Macro Plan (14-week periodization) ────────────────────────────────────────

def load_macro_plan() -> dict | None:
    """Read the structured 14-week macro plan (single source of truth)."""
    if not MACRO_FILE.exists():
        return None
    try:
        return json.loads(MACRO_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_macro_week(today: date | None = None) -> dict:
    """
    Locate where we are in the 14-week macro plan based on today's date.
    Returns the current week's targets + phase + gate/deload flags, plus
    weeks-to-race. This is the bridge between micro (weekly) and macro.
    """
    plan = load_macro_plan()
    if not plan:
        return {"status": "no_plan"}

    today = today or date.today()
    start = date.fromisoformat(plan.get("start_sunday") or plan["start_monday"])
    weeks = plan["weeks"]
    total = len(weeks)
    race_date = date.fromisoformat(plan["race"]["date"])
    days_to_race = (race_date - today).days

    delta_days = (today - start).days
    if delta_days < 0:
        days_until_start = -delta_days
        return {"status": "pre", "race": plan["race"], "total_weeks": total,
                "days_until_start": days_until_start, "days_to_race": days_to_race,
                "first_week": weeks[0]}

    week_num = delta_days // 7 + 1
    if week_num > total:
        return {"status": "post", "race": plan["race"], "total_weeks": total,
                "days_to_race": days_to_race}

    wk = weeks[week_num - 1]
    return {
        "status": "active",
        "week_num": week_num,
        "total_weeks": total,
        "phase": wk["phase"],
        "target_km": wk["target_km"],
        "long_run_km": wk["long_run_km"],
        "quality": wk["quality"],
        "deload": wk["deload"],
        "gate": wk["gate"],
        "focus": wk["focus"],
        "days_to_race": days_to_race,
        "weeks_to_race": max(0, total - week_num),
        "race": plan["race"],
    }


def format_macro_for_prompt(macro: dict) -> str:
    """Render the macro position as a compact markdown block for prompts."""
    if not macro or macro.get("status") == "no_plan":
        return "אין תוכנית מאקרו טעונה (macro_plan.json חסר)."
    if macro.get("status") == "pre":
        return (f"התוכנית עוד לא התחילה — מתחילה בעוד {macro['days_until_start']} ימים. "
                f"תחרות בעוד {macro['days_to_race']} ימים.")
    if macro.get("status") == "post":
        return f"התוכנית הסתיימה. תחרות בעוד {macro['days_to_race']} ימים."
    race = macro["race"]
    gate = " 🔬 **שבוע גייט — הערכת מאקרו מחדש**" if macro["gate"] else ""
    deload = " 🔻 **DELOAD**" if macro["deload"] else ""
    return (
        f"**מיקום במאקרו:** שבוע {macro['week_num']}/{macro['total_weeks']} · "
        f"פאזת **{macro['phase']}**{deload}{gate}\n"
        f"- יעד התחרות: {race['distance_km']} ק\"מ @ {race['goal_pace']}/ק\"מ "
        f"({macro['days_to_race']} ימים, {macro['weeks_to_race']} שבועות לתחרות)\n"
        f"- יעד נפח השבוע: ~{macro['target_km']} ק\"מ\n"
        f"- Long run השבוע: עד {macro['long_run_km']} ק\"מ\n"
        f"- אימון איכות מתוכנן: {macro['quality']}\n"
        f"- מיקוד הפאזה: {macro['focus']}"
    )


# ── Training Load Metrics ────────────────────────────────────────────────────

def build_daily_load(activities: list) -> dict[str, float]:
    """Sum exercise_load per calendar day across all activities."""
    daily: dict[str, float] = {}
    for act in activities:
        d = act.get("date")
        load = act.get("exercise_load") or 0.0
        if d and load > 0:
            daily[d] = daily.get(d, 0.0) + load
    return daily


def compute_ctl_atl(daily_load: dict[str, float], reference_date: date) -> dict:
    """
    Compute CTL (42-day EWA) and ATL (7-day EWA) up to reference_date.
    Returns dict with ctl, atl, acwr, tsb and 28-day history for ramp rate.
    """
    k42 = 1.0 / 42
    k7 = 1.0 / 7

    ctl = 0.0
    atl = 0.0
    ctl_28_ago = 0.0

    # Walk day by day from earliest data to reference_date
    day = date(2024, 1, 1)
    while day <= reference_date:
        ds = day.isoformat()
        load = daily_load.get(ds, 0.0)
        ctl = ctl + (load - ctl) * k42
        atl = atl + (load - atl) * k7

        # capture CTL 28 days before reference
        if day == reference_date - timedelta(days=28):
            ctl_28_ago = ctl

        day += timedelta(days=1)

    acwr = round(atl / ctl, 2) if ctl > 0 else None
    tsb = round(ctl - atl, 1)
    ramp_rate_4w = round(ctl - ctl_28_ago, 1)

    return {
        "ctl": round(ctl, 1),
        "atl": round(atl, 1),
        "tsb": tsb,
        "acwr": acwr,
        "ramp_rate_4w": ramp_rate_4w,
    }


# ── ACWR Risk Flag (Feature 3) ───────────────────────────────────────────────

def acwr_status(acwr) -> dict:
    """Map ACWR to a traffic-light injury-risk flag (Gabbett 2016 zones)."""
    if acwr is None:
        return {"flag": "⚪", "level": "לא זמין", "color": "gray",
                "message": "אין מספיק נתונים לחישוב ACWR (CTL=0)."}
    if acwr > 1.5:
        return {"flag": "🔴", "level": "סכנה", "color": "red",
                "message": f"ACWR={acwr} מעל 1.5 — אזור Spike של Gabbett. סיכון פציעה גבוה. הורד עומס מיד."}
    if acwr > 1.3:
        return {"flag": "🟡", "level": "זהירות", "color": "yellow",
                "message": f"ACWR={acwr} בטווח 1.3–1.5 — סיכון מוגבר. אל תוסיף עומס השבוע."}
    if acwr < 0.8:
        return {"flag": "🔵", "level": "תת-אימון", "color": "blue",
                "message": f"ACWR={acwr} מתחת 0.8 — תת-עומס (detraining). אפשר להעלות בהדרגה."}
    return {"flag": "🟢", "level": "מיטבי", "color": "green",
            "message": f"ACWR={acwr} בטווח הבטוח 0.8–1.3. המשך כך."}


# ── Training Monotony (Feature 4) ─────────────────────────────────────────────

def compute_training_monotony(daily_load: dict, reference_date: date, days: int = 7) -> dict:
    """
    Foster's monotony = mean(daily load) / SD(daily load) over the window,
    counting rest days as 0. Strain = monotony × weekly load.
    Thresholds: <1.5 good, 1.5–2.0 caution, >2.0 high injury/illness risk.
    """
    import statistics
    loads = [daily_load.get((reference_date - timedelta(days=i)).isoformat(), 0.0)
             for i in range(days)]
    weekly_load = round(sum(loads), 1)
    mean_load = sum(loads) / days
    sd = statistics.pstdev(loads) if days > 1 else 0.0

    if mean_load == 0:
        return {"available": False, "monotony": None, "weekly_load": 0.0,
                "strain": None, "flag": "⚪", "level": "לא זמין",
                "message": "אין עומס בשבוע האחרון — לא ניתן לחשב מונוטוניות."}
    if sd == 0:
        return {"available": True, "monotony": None, "weekly_load": weekly_load,
                "strain": None, "flag": "🔴", "level": "מקסימלי",
                "message": "עומס זהה כל יום — מונוטוניות מקסימלית. הכנס ימי מנוחה ושונות."}

    monotony = round(mean_load / sd, 2)
    strain = round(monotony * weekly_load, 1)
    if monotony > 2.0:
        flag, level, msg = "🔴", "גבוה", (
            f"מונוטוניות {monotony} מעל 2.0 — אימון חדגוני, סיכון פציעה/מחלה. "
            "גוון: ימים קשים קשים, ימים קלים קלים.")
    elif monotony > 1.5:
        flag, level, msg = "🟡", "בינוני", (
            f"מונוטוניות {monotony} בטווח 1.5–2.0 — שמור על שונות בין הימים.")
    else:
        flag, level, msg = "🟢", "טוב", (
            f"מונוטוניות {monotony} מתחת 1.5 — חלוקה בריאה בין ימים קשים לקלים.")
    return {"available": True, "monotony": monotony, "weekly_load": weekly_load,
            "strain": strain, "flag": flag, "level": level, "message": msg}


# ── Zone Distribution ────────────────────────────────────────────────────────

def _zone_index_from_pct(pct: float) -> int:
    """Map %MaxHR to a zone index 0-4 (Z1<60, Z2 60-70, Z3 70-80, Z4 80-90, Z5>90)."""
    for i, t in enumerate((0.60, 0.70, 0.80, 0.90)):
        if pct < t:
            return i
    return 4


def compute_zone_distribution(activities: list, days: int = 28,
                              global_max_hr: float | None = None) -> dict:
    """
    Compute HR zone distribution (% of time) across the last N days of runs.
    Uses real hr_zones_sec where available; for runs that lack it, falls back
    to estimating from avg_hr vs global_max_hr (whole duration → avg_hr's zone).
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    runs = [
        a for a in activities
        if a.get("activity_type") in RUN_TYPES
        and a.get("date", "") >= cutoff
        and (a.get("distance_km") or 0) > 0.5
    ]

    totals = [0.0, 0.0, 0.0, 0.0, 0.0]
    measured = 0
    estimated = 0
    for run in runs:
        zones = run.get("hr_zones_sec") or [0, 0, 0, 0, 0]
        if sum(zones) > 0:
            for i in range(5):
                totals[i] += zones[i]
            measured += 1
        elif global_max_hr and run.get("avg_hr") and run.get("duration_sec"):
            # Fallback: bucket the whole run into the zone of its avg_hr
            z = _zone_index_from_pct(run["avg_hr"] / global_max_hr)
            totals[z] += run["duration_sec"]
            estimated += 1

    total_sec = sum(totals)
    if total_sec == 0:
        return {"available": False, "runs_analyzed": 0}

    pcts = [round(t / total_sec * 100, 1) for t in totals]
    easy_pct = pcts[0] + pcts[1]   # Z1 + Z2
    hard_pct = pcts[3] + pcts[4]   # Z4 + Z5

    return {
        "available": True,
        "runs_analyzed": measured + estimated,
        "runs_measured": measured,
        "runs_estimated": estimated,
        "z1_pct": pcts[0],
        "z2_pct": pcts[1],
        "z3_pct": pcts[2],
        "z4_pct": pcts[3],
        "z5_pct": pcts[4],
        "easy_pct": round(easy_pct, 1),
        "hard_pct": round(hard_pct, 1),
        "polarization_gap": round(easy_pct - 80, 1),  # deviation from 80% easy target
    }


# ── Fitness Trends ───────────────────────────────────────────────────────────

def compute_efficiency_factor(run: dict) -> float | None:
    """
    EF = speed_m_per_min / avg_hr  (TrainingPeaks standard)
    Only meaningful for Z2 runs (aerobic base work).
    Higher EF over time = improving aerobic fitness.
    """
    pace = run.get("pace_sec_per_km")
    avg_hr = run.get("avg_hr")
    if not pace or not avg_hr or avg_hr <= 0:
        return None
    speed_m_per_min = 1000.0 / pace * 60.0
    return round(speed_m_per_min / avg_hr, 4)


def _linear_trend(values: list[float]) -> float | None:
    """Slope of a simple linear regression (least squares)."""
    n = len(values)
    if n < 3:
        return None
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    num = sum((xs[i] - x_mean) * (values[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    return round(num / den, 4) if den != 0 else None


def compute_fitness_trends(activities: list, global_max_hr: float, weeks: int = 8) -> dict:
    """
    Compute 8-week trends for:
    - Efficiency Factor (EF) on Z2 runs — rising = improving aerobic fitness
    - VO2max trend from Garmin estimates
    - Cadence trend across all runs
    - VDOT estimate from best recent 5K/10K performance
    """
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()
    z2_lo = global_max_hr * 0.60
    z2_hi = global_max_hr * 0.75  # slightly wider than strict Z2 to capture enough runs

    all_runs = [
        a for a in activities
        if a.get("activity_type") in RUN_TYPES
        and a.get("date", "") >= cutoff
        and (a.get("distance_km") or 0) >= 3.0
    ]
    all_runs_sorted = sorted(all_runs, key=lambda x: x["date"])

    # ── EF trend (Z2 runs only) ──────────────────────────────────────────
    z2_runs = [
        r for r in all_runs_sorted
        if r.get("avg_hr") and z2_lo <= r["avg_hr"] <= z2_hi
        and r.get("pace_sec_per_km")
    ]
    ef_values = [compute_efficiency_factor(r) for r in z2_runs]
    ef_values = [v for v in ef_values if v is not None]
    ef_trend = _linear_trend(ef_values)
    ef_current = round(sum(ef_values[-3:]) / 3, 4) if len(ef_values) >= 3 else (ef_values[-1] if ef_values else None)

    # ── VO2max trend ─────────────────────────────────────────────────────
    vo2_runs = [(r["date"], r["vo2max"]) for r in all_runs_sorted if r.get("vo2max")]
    vo2_values = [v for _, v in vo2_runs]
    vo2_trend = _linear_trend(vo2_values)
    vo2_current = vo2_values[-1] if vo2_values else None

    # ── Cadence trend ────────────────────────────────────────────────────
    cad_runs = [r for r in all_runs_sorted if r.get("cadence_spm")]
    cad_values = [r["cadence_spm"] for r in cad_runs]
    cad_trend = _linear_trend(cad_values)
    cad_current = round(sum(cad_values[-4:]) / 4) if len(cad_values) >= 4 else (cad_values[-1] if cad_values else None)

    # ── VDOT estimate ────────────────────────────────────────────────────
    # Jack Daniels formula: VO2 = -4.60 + 0.182258*v + 0.000104*v^2
    # %max = 0.8 + 0.1894393*e^(-0.012778*t) + 0.2989558*e^(-0.1932605*t)
    # VDOT = VO2 / %max
    import math
    vdot = None
    vdot_basis = None
    for label, (lo, hi) in [("5K", (4.5, 5.5)), ("10K", (9.5, 10.5)), ("HM", (20.5, 21.5))]:
        # Only use runs from last 90 days for VDOT (fitness must be current)
        recent_cutoff = (date.today() - timedelta(days=90)).isoformat()
        candidates = [
            a for a in activities
            if a.get("activity_type") in RUN_TYPES
            and lo <= (a.get("distance_km") or 0) <= hi
            and a.get("pace_sec_per_km")
            and a.get("date", "") >= recent_cutoff
        ]
        if candidates:
            best = min(candidates, key=lambda x: x["pace_sec_per_km"])
            t_min = best["pace_sec_per_km"] * best["distance_km"] / 60.0
            v = best["distance_km"] * 1000.0 / t_min  # m/min
            vo2_at_pace = -4.60 + 0.182258 * v + 0.000104 * v ** 2
            pct_max = (0.8 + 0.1894393 * math.exp(-0.012778 * t_min)
                       + 0.2989558 * math.exp(-0.1932605 * t_min))
            vdot_calc = round(vo2_at_pace / pct_max, 1)
            if vdot is None or vdot_calc > vdot:
                vdot = vdot_calc
                pace_s = best["pace_sec_per_km"]
                vdot_basis = f"{label} @ {pace_s // 60}:{pace_s % 60:02d}/km ({best['date']})"

    return {
        "ef": {
            "current": ef_current,
            "trend_slope": ef_trend,
            "trend_direction": ("עולה ✓" if ef_trend and ef_trend > 0.0001 else
                                "יורד ⚠" if ef_trend and ef_trend < -0.0001 else "יציב"),
            "z2_runs_analyzed": len(z2_runs),
            "note": "EF = מהירות(מ'/דק') / דופק — עלייה = שיפור אירובי",
        },
        "vo2max": {
            "current": vo2_current,
            "trend_slope": vo2_trend,
            "trend_direction": ("עולה ✓" if vo2_trend and vo2_trend > 0.01 else
                                "יורד ⚠" if vo2_trend and vo2_trend < -0.01 else "יציב"),
            "readings_analyzed": len(vo2_values),
        },
        "cadence": {
            "current_avg_spm": cad_current,
            "trend_slope": cad_trend,
            "trend_direction": ("עולה" if cad_trend and cad_trend > 0.1 else
                                "יורד" if cad_trend and cad_trend < -0.1 else "יציב"),
            "target_spm": athlete.CADENCE_TARGET,
            "gap_to_target": round(athlete.CADENCE_TARGET - cad_current, 1) if cad_current else None,
        },
        "vdot": {
            "estimate": vdot,
            "basis": vdot_basis,
            "note": "נוסחת Jack Daniels — מבוסס על ביצוע מירבי 90 יום אחרונים",
        },
        "weeks_analyzed": weeks,
    }


# ── 4-Week Fitness Assessment ─────────────────────────────────────────────────

def _vdot_from_pace(distance_km: float, pace_sec_per_km: float) -> float | None:
    """Jack Daniels VDOT from a single effort (distance + pace)."""
    import math
    if not distance_km or not pace_sec_per_km:
        return None
    t_min = pace_sec_per_km * distance_km / 60.0
    if t_min <= 0:
        return None
    v = distance_km * 1000.0 / t_min  # m/min
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v ** 2
    pct = (0.8 + 0.1894393 * math.exp(-0.012778 * t_min)
           + 0.2989558 * math.exp(-0.1932605 * t_min))
    return round(vo2 / pct, 1) if pct else None


def compute_fitness_4week(activities: list, global_max_hr: float) -> dict:
    """
    Current-fitness snapshot from ALL runs in the last 28 days (not a single run).
    This is the canonical fitness measure used at the macro reassessment gates.
    """
    cutoff = (date.today() - timedelta(days=28)).isoformat()
    runs = [
        a for a in activities
        if a.get("activity_type") in RUN_TYPES
        and a.get("date", "") >= cutoff
        and (a.get("distance_km") or 0) >= 1.0
    ]
    if not runs:
        return {"available": False, "runs": 0}

    runs_sorted = sorted(runs, key=lambda x: x["date"])
    total_km = sum(r.get("distance_km") or 0 for r in runs)
    weekly_km = round(total_km / 4.0, 1)

    # VDOT from the best single effort in the 4-week window (≥3 km, real pace)
    vdot, vdot_basis = None, None
    for r in runs_sorted:
        if (r.get("distance_km") or 0) >= 3.0 and r.get("pace_sec_per_km"):
            v = _vdot_from_pace(r["distance_km"], r["pace_sec_per_km"])
            if v and (vdot is None or v > vdot):
                vdot = v
                p = r["pace_sec_per_km"]
                vdot_basis = f"{r['distance_km']:.1f}ק\"מ @ {p//60}:{p%60:02d}/ק\"מ ({r['date']})"

    # Threshold pace proxy = avg pace of runs whose avg_hr sits in Z4 (80–90% max)
    z4_lo, z4_hi = global_max_hr * 0.80, global_max_hr * 0.90
    thr_runs = [r for r in runs_sorted
                if r.get("avg_hr") and z4_lo <= r["avg_hr"] <= z4_hi and r.get("pace_sec_per_km")]
    thr_pace = None
    if thr_runs:
        avg = sum(r["pace_sec_per_km"] for r in thr_runs) / len(thr_runs)
        thr_pace = f"{int(avg)//60}:{int(avg)%60:02d}/ק\"מ"

    # EF on Z2 runs (aerobic efficiency)
    z2_lo, z2_hi = global_max_hr * 0.60, global_max_hr * 0.75
    z2_runs = [r for r in runs_sorted
               if r.get("avg_hr") and z2_lo <= r["avg_hr"] <= z2_hi and r.get("pace_sec_per_km")]
    ef_vals = [compute_efficiency_factor(r) for r in z2_runs]
    ef_vals = [v for v in ef_vals if v is not None]
    ef_avg = round(sum(ef_vals) / len(ef_vals), 4) if ef_vals else None

    return {
        "available": True,
        "window_days": 28,
        "runs": len(runs),
        "weekly_km_avg": weekly_km,
        "total_km": round(total_km, 1),
        "vdot": vdot,
        "vdot_basis": vdot_basis,
        "threshold_pace": thr_pace,
        "threshold_runs": len(thr_runs),
        "ef_z2_avg": ef_avg,
        "z2_runs": len(z2_runs),
    }


# ── Red Flags (deterministic detection) ───────────────────────────────────────

def detect_red_flags(activities: list, metrics: dict) -> list[dict]:
    """
    Deterministic red-flag scan that feeds all three loops.
    Each flag: {flag, severity (🔴/🟡), detail, action}.
    """
    flags: list[dict] = []
    load = metrics.get("load", {})

    # 1. ACWR spike
    acwr = load.get("acwr")
    if acwr is not None and acwr > 1.5:
        flags.append({"flag": "ACWR spike", "severity": "🔴",
                      "detail": f"ACWR={acwr} מעל 1.5 (Gabbett spike zone)",
                      "action": "הורד עומס מיד. אל תוסיף ריצות קשות השבוע."})

    # 2. Monotony
    mono = metrics.get("monotony", {})
    if mono.get("monotony") and mono["monotony"] > 2.0:
        flags.append({"flag": "מונוטוניות גבוהה", "severity": "🟡",
                      "detail": f"מונוטוניות={mono['monotony']} מעל 2.0",
                      "action": "גוון: ימים קשים קשים, קלים קלים. הוסף יום מנוחה."})

    # 3. Cardiac drift on the most recent run
    recent = sorted(
        [a for a in activities if a.get("activity_type") in RUN_TYPES and a.get("hr_drift_bpm") is not None],
        key=lambda x: x["date"])
    if recent:
        last = recent[-1]
        drift = last["hr_drift_bpm"]
        if drift is not None and drift > 12:
            flags.append({"flag": "Cardiac drift חריג", "severity": "🟡",
                          "detail": f"drift +{drift} bpm בריצה {last['date']}",
                          "action": "עייפות/חום/התייבשות. שקול יום קל מחר."})

    # 4. Volume jump — last 7 days vs prior 7 days
    def km_in_window(start_days, end_days):
        lo = (date.today() - timedelta(days=start_days)).isoformat()
        hi = (date.today() - timedelta(days=end_days)).isoformat()
        return sum(a.get("distance_km") or 0 for a in activities
                   if a.get("activity_type") in RUN_TYPES and hi < a.get("date", "") <= lo)
    this_wk = km_in_window(0, 7)
    prior_wk = km_in_window(7, 14)
    if prior_wk > 5 and this_wk > prior_wk * 1.30:
        flags.append({"flag": "קפיצת נפח", "severity": "🟡",
                      "detail": f"נפח השבוע {this_wk:.0f} ק\"מ מול {prior_wk:.0f} בשבוע שעבר (>30%)",
                      "action": "עלייה חדה מדי בנפח. רכך את השבוע הבא."})

    # (הוסר) דגל "Long run 10+ → בדוק ברך" — היה נדלק 7 ימים אחרי כל לונג ומופיע בכל
    # הודעה = רעש. כאב אמיתי מגיע עכשיו דרך היומן (journal) שהמתאמן כותב, ומוזן לניתוח.

    # 6. אי-התאמה סובייקטיבית — Feel הוא סיגנל מוכנות בלבד; דגל רק עם אישור אובייקטיבי.
    #    "הרגשתי חלש" ≠ "אימון גרוע" — שופטים לפי התוצאה (קצב מול מתוכנן), לא לפי ההרגשה.
    planned_by_date = {}
    try:
        wp = json.loads((BASE_DIR / "week_plan.json").read_text(encoding="utf-8"))
        for s in wp.get("sessions", []):
            if s.get("type") == "run":
                planned_by_date[s["date"]] = {"subtype": s.get("subtype", "easy"),
                                              "pace": s.get("pace")}
    except Exception:
        pass

    rated_runs = [a for a in activities
                  if a.get("activity_type") in RUN_TYPES
                  and a.get("date", "") >= (date.today() - timedelta(days=4)).isoformat()
                  and (a.get("rpe") is not None or a.get("feel") is not None)]
    for r in rated_runs[-1:]:
        rpe, feel = r.get("rpe"), r.get("feel")
        p = planned_by_date.get(r["date"], {})
        planned = p.get("subtype")
        weak = (feel is not None and feel <= 2)
        is_quality = planned == "quality" or str(r.get("category", "")).startswith("quality")
        # האם הקצב בפועל נפל מתחת למתוכנן (>5% אטי) — סימן אובייקטיבי לתת-ביצוע
        actual = r.get("pace_sec_per_km")
        planned_sec = _pace_to_sec(p["pace"]) if p.get("pace") else None
        underperformed = bool(actual and planned_sec and actual > planned_sec * 1.05)

        if not is_quality and planned in ("easy", "long", None):
            # ריצה קלה: RPE גבוה (אובייקטיבי) = בעיה. Feel חלש לבד לא מספיק.
            if rpe is not None and rpe >= 7:
                flags.append({
                    "flag": "מאמץ נתפס גבוה בריצה קלה", "severity": "🟡",
                    "detail": f"ריצה קלה ({r['date']}) — RPE {rpe}/10. מאמץ גבוה על אימון קל.",
                    "action": "סימן לתת-התאוששות. הקל בימים הקרובים.",
                })
        elif is_quality and weak and underperformed:
            # איכות: דגל רק אם הרגיש חלש *וגם* הקצב נפל מתחת למתוכנן
            flags.append({
                "flag": "איכות שהרגישה חלשה + תת-ביצוע", "severity": "🟡",
                "detail": f"אימון איכות ({r['date']}) — Feel {feel}/5, וגם הקצב נפל מתחת למתוכנן. צירוף שמעיד על עייפות.",
                "action": "בדוק התאוששות לפני האיכות הבאה.",
            })

    return flags


# ── Last Week Summary ────────────────────────────────────────────────────────

def last_n_days_runs(activities: list, n: int = 7) -> list:
    cutoff = (date.today() - timedelta(days=n)).isoformat()
    runs = [
        a for a in activities
        if a.get("activity_type") in RUN_TYPES
        and a.get("date", "") >= cutoff
        and (a.get("distance_km") or 0) > 0.5
    ]
    return sorted(runs, key=lambda x: x["date"])


def summarize_runs(runs: list) -> dict:
    if not runs:
        return {"count": 0, "total_km": 0, "runs": []}

    total_km = sum(r.get("distance_km") or 0 for r in runs)
    total_load = sum(r.get("exercise_load") or 0 for r in runs)

    run_summaries = []
    for r in runs:
        drift = r.get("hr_drift_bpm")
        zones = r.get("hr_zones_sec") or [0, 0, 0, 0, 0]
        zone_total = sum(zones)
        dominant_zone = zones.index(max(zones)) + 1 if zone_total > 0 else None

        pace = r.get("pace_sec_per_km")
        pace_str = f"{pace // 60}:{pace % 60:02d}/km" if pace else "N/A"

        run_summaries.append({
            "date": r["date"],
            "distance_km": r.get("distance_km"),
            "pace": pace_str,
            "avg_hr": r.get("avg_hr"),
            "load": round(r.get("exercise_load") or 0, 1),
            "dominant_zone": dominant_zone,
            "cardiac_drift_bpm": drift,
            "cadence_spm": r.get("cadence_spm"),
        })

    return {
        "count": len(runs),
        "total_km": round(total_km, 1),
        "total_load": round(total_load, 1),
        "runs": run_summaries,
    }


# ── Readiness ────────────────────────────────────────────────────────────────

def get_readiness(daily: dict) -> dict:
    """Extract last 3 days of sleep + body battery."""
    today = date.today()
    result = {}
    for i in range(3):
        d = (today - timedelta(days=i)).isoformat()
        if d in daily:
            result[d] = daily[d]
    return result


def morning_readiness(daily: dict) -> dict:
    """
    Resolve TODAY's readiness explicitly, flagging stale data.
    The morning loop must judge today's body — not silently use yesterday's.
    A sleep_score of 0/None is treated as 'not synced yet', not a real value.
    """
    today = date.today().isoformat()
    def valid(rec):
        return bool(rec) and rec.get("sleep_score") not in (None, 0)

    today_rec = daily.get(today)
    has_today = valid(today_rec)

    # Most recent day that actually has a real sleep score (for fallback context)
    latest_date, latest_rec = None, None
    for d in sorted(daily.keys(), reverse=True):
        if valid(daily[d]):
            latest_date, latest_rec = d, daily[d]
            break

    used_date = today if has_today else latest_date
    used_rec = today_rec if has_today else latest_rec
    return {
        "today_date": today,
        "has_today": has_today,
        "is_stale": not has_today,
        "used_date": used_date,
        "sleep_score": (used_rec or {}).get("sleep_score") if used_rec else None,
        "body_battery": (used_rec or {}).get("body_battery_morning") if used_rec else None,
    }


# ── Best Performances ────────────────────────────────────────────────────────

def compute_prs(activities: list) -> dict:
    distances = {
        "5K":  (4.5, 5.5),
        "10K": (9.5, 10.5),
        "HM":  (20.5, 21.5),
    }
    prs = {}
    for label, (lo, hi) in distances.items():
        candidates = [
            a for a in activities
            if a.get("activity_type") in RUN_TYPES
            and lo <= (a.get("distance_km") or 0) <= hi
            and a.get("pace_sec_per_km")
        ]
        if candidates:
            best = min(candidates, key=lambda x: x["pace_sec_per_km"])
            p = best["pace_sec_per_km"]
            prs[label] = {
                "pace": f"{p // 60}:{p % 60:02d}/km",
                "date": best["date"],
                "distance_km": best["distance_km"],
            }
    return prs


# ── Strength Training ────────────────────────────────────────────────────────

STRENGTH_TYPES = {
    "strength_training", "jump_rope", "pilates",
    "indoor_cardio", "stair_climbing",
}


def compute_strength_metrics(activities: list, days: int = 7) -> dict:
    """Summarise strength/neuromuscular sessions for the last N days."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    sessions = [
        a for a in activities
        if a.get("activity_type") in STRENGTH_TYPES
        and a.get("date", "") >= cutoff
    ]
    sessions_sorted = sorted(sessions, key=lambda x: x["date"])

    total_load = sum(a.get("exercise_load") or 0 for a in sessions)
    total_min = sum((a.get("duration_sec") or 0) / 60 for a in sessions)

    last = sessions_sorted[-1] if sessions_sorted else None
    days_since_last = None
    if last:
        last_d = date.fromisoformat(last["date"])
        days_since_last = (date.today() - last_d).days

    return {
        "session_count": len(sessions),
        "total_load": round(total_load, 1),
        "total_min": round(total_min),
        "days_since_last": days_since_last,
        "last_session_date": last["date"] if last else None,
        "last_session_load": round(last.get("exercise_load") or 0, 1) if last else None,
        "sessions": [
            {
                "date": s["date"],
                "type": s["activity_type"],
                "duration_min": round((s.get("duration_sec") or 0) / 60),
                "load": round(s.get("exercise_load") or 0, 1),
            }
            for s in sessions_sorted
        ],
    }


def compute_neuromuscular_atl(activities: list, reference_date: date) -> float:
    """
    7-day EWA of strength load — parallel neuromuscular fatigue track.
    Research: strength load decays with ~48-hour half-life; 7-day EWA is a good proxy.
    """
    k7 = 1.0 / 7
    daily: dict[str, float] = {}
    for a in activities:
        if a.get("activity_type") in STRENGTH_TYPES:
            d = a.get("date")
            load = a.get("exercise_load") or 0.0
            if d and load > 0:
                daily[d] = daily.get(d, 0.0) + load

    nm_atl = 0.0
    day = date(2024, 1, 1)
    while day <= reference_date:
        load = daily.get(day.isoformat(), 0.0)
        nm_atl = nm_atl + (load - nm_atl) * k7
        day += timedelta(days=1)
    return round(nm_atl, 1)


# ── History & Memory ────────────────────────────────────────────────────────

def current_week_monday() -> str:
    """Return ISO date string for the Monday of the current week."""
    today = date.today()
    return (today - timedelta(days=today.weekday())).isoformat()


def load_history() -> list[dict]:
    """Return last HISTORY_WEEKS_TO_INJECT weeks from history file."""
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data.get("weeks", [])[-HISTORY_WEEKS_TO_INJECT:]
    except Exception:
        return []


def save_history_entry(entry: dict) -> None:
    """Append a weekly entry; keep last HISTORY_WEEKS_TO_KEEP. Idempotent on same week_of."""
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {"version": 1, "weeks": []}
    else:
        data = {"version": 1, "weeks": []}

    week_of = entry["week_of"]
    data["weeks"] = [w for w in data["weeks"] if w.get("week_of") != week_of]
    data["weeks"].append(entry)
    data["weeks"] = sorted(data["weeks"], key=lambda x: x["week_of"])
    data["weeks"] = data["weeks"][-HISTORY_WEEKS_TO_KEEP:]
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compute_compliance(history: list[dict], current_last_week: dict) -> dict:
    """Compare last week's recommended plan against actual Garmin data."""
    if not history:
        return {"available": False, "reason": "אין היסטוריה קודמת"}
    last = history[-1]
    plan = last.get("recommended_plan") or {}
    if not plan:
        return {"available": False, "reason": "אין תוכנית מומלצת בשבוע הקודם"}

    planned_km = plan.get("total_km_approx")
    planned_runs = plan.get("run_count")
    actual_km = current_last_week.get("total_km", 0)
    actual_runs = current_last_week.get("count", 0)

    result: dict = {
        "available": True,
        "prior_week_of": last.get("week_of"),
        "plan_focus": plan.get("focus", "לא ידוע"),
        "plan_key_workout": plan.get("key_workout", "לא ידוע"),
        "planned_runs": planned_runs,
        "actual_runs": actual_runs,
        "planned_km_approx": planned_km,
        "actual_km": actual_km,
    }
    if planned_km and actual_km:
        pct = round(actual_km / planned_km * 100)
        result["km_compliance_pct"] = pct
        result["compliance_level"] = "מלא" if pct >= 90 else "חלקי" if pct >= 70 else "נמוך"
    return result


def extract_llm_json(report_text: str, start_marker: str = "", end_marker: str = "",
                     aliases: dict | None = None) -> dict:
    """Robust extraction of a JSON object from an LLM report. SINGLE source of
    truth for all *_JSON block parsing (morning/postworkout/weekly/plan/week_plan).

    The model does not reliably emit the literal ---MARKER--- wrappers — at low
    effort it may wrap the object in a ```json fence or print a bare {...}. A
    markers-only regex silently returns {}, which downstream means a dropped
    Telegram message, an unbuilt week plan, or a lost adjustment. Strategy:
      1) explicit markers (what we ask for)
      2) any ```fenced``` block
      3) the last bare {...} object (greedy — handles nested sessions arrays)
    Then normalize field-name aliases so callers rely on canonical keys.
    """
    import re
    candidates = []
    if start_marker and end_marker:
        m = re.search(re.escape(start_marker) + r"\s*(.*?)\s*" + re.escape(end_marker),
                      report_text, re.DOTALL)
        if m:
            candidates.append(m.group(1))
    for fm in re.finditer(r"```(?:json)?\s*(.*?)```", report_text, re.DOTALL):
        candidates.append(fm.group(1).strip())
    bm = re.search(r"(\{.*\})", report_text, re.DOTALL)
    if bm:
        candidates.append(bm.group(1))

    parsed = None
    for cand in candidates:
        try:
            parsed = json.loads(cand)
            break
        except Exception:
            continue
    if not isinstance(parsed, dict):
        return {}

    if aliases:
        for canonical, names in aliases.items():
            if not parsed.get(canonical):
                for n in names:
                    if parsed.get(n):
                        parsed[canonical] = parsed[n]
                        break
    return parsed


def extract_plan_json(report_text: str) -> dict:
    """Extract the structured plan block Claude writes at the end of each report."""
    return extract_llm_json(report_text, "---PLAN_JSON---", "---END_PLAN---")


# ── Structured Week Plan (the bridge to Garmin + calendar) ────────────────────

WEEK_DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]  # Mon..Sun


def _pace_to_sec(pace: str) -> int:
    """'5:10' → 310 שניות/ק"מ. ברירת מחדל 360 אם לא תקין."""
    try:
        m, s = pace.split(":")
        return int(m) * 60 + int(s)
    except Exception:
        return 360


def extract_week_plan(report_text: str) -> dict:
    """חילוץ בלוק WEEK_PLAN_JSON שה-AI כותב בסוף הדוח (מקור-האמת לתוכנית)."""
    return extract_llm_json(report_text, "---WEEK_PLAN_JSON---", "---END_WEEK_PLAN---")


def materialize_week_plan(raw: dict) -> dict:
    """
    ממיר את התוכנית המובנית של ה-AI ל-week_plan.json מלא:
    מוסיף שמות-ימים, תיאורים, ו-steps לריצות (חימום/עיקר/שחרור) — מה שגרמין צריך.
    """
    if not raw or not raw.get("sessions"):
        return {}
    out = {
        "week_of": raw.get("week_of", ""),
        "macro_week": raw.get("macro_week"),
        "phase": raw.get("phase", ""),
        "goal_race": athlete.GOAL_RACE_LABEL,
        "notes": raw.get("notes", "נוצר אוטומטית מהסקירה השבועית."),
        "sessions": [],
    }
    for s in raw["sessions"]:
        d = s.get("date", "")
        try:
            day = WEEK_DAY_NAMES[date.fromisoformat(d).weekday()]
        except Exception:
            day = ""
        if s.get("type") == "run":
            est_km = float(s.get("est_km") or 5)
            pace_sec = _pace_to_sec(s.get("pace", "6:30"))
            total = int(est_km * pace_sec)
            sub = s.get("subtype", "easy")
            if sub == "long":
                steps = [{"kind": "interval", "seconds": total}]
            else:
                # חימום ~9 דק' + עיקר + שחרור ~6 דק'
                main = max(300, total - 540 - 360)
                steps = [
                    {"kind": "warmup", "seconds": 540},
                    {"kind": "interval", "seconds": main},
                    {"kind": "cooldown", "seconds": 360},
                ]
            out["sessions"].append({
                "date": d, "day": day, "type": "run", "subtype": sub,
                "name": s.get("name", "🏃 ריצה"),
                "desc": s.get("desc", s.get("name", "")),
                "est_km": est_km, "steps": steps,
            })
        else:
            out["sessions"].append({
                "date": d, "day": day, "type": "strength", "key": s.get("key", "A"),
            })
    return out


def save_week_plan(raw: dict, prev_week_km: float = 0.0,
                   macro: dict | None = None, acwr: float | None = None) -> tuple[bool, list, bool]:
    """
    שומר week_plan.json — אך ורק אחרי מעבר בשכבת הבטיחות הדטרמיניסטית (safety.py).
    מחזיר (saved, messages, needs_review):
      • saved        — האם נכתב לדיסק.
      • messages     — adjustments + warnings להצגה בשער האישור.
      • needs_review — האם נדרש אישור מפורש.
    תוכנית פגומה מבנית → לא נכתבת (saved=False).
    """
    import safety
    full = materialize_week_plan(raw)
    if not full.get("sessions"):
        return False, ["לא נמצאו אימונים בתוכנית."], False

    plan, adjustments, warnings, needs_review = safety.clamp_and_validate_week_plan(
        full, prev_week_km, macro, acwr)
    if plan is None:
        # דחייה מבנית — לא כותבים שום דבר.
        return False, warnings, True

    plan["plan_metadata"] = safety.build_plan_metadata(adjustments, warnings, needs_review)
    (BASE_DIR / "week_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, adjustments + warnings, needs_review


def format_history_for_prompt(history: list[dict]) -> str:
    """Convert stored JSON history to a compact markdown block for prompt injection.
    JSON for storage, markdown for prompts — 15-34% fewer tokens than raw JSON."""
    if not history:
        return "אין היסטוריה קודמת — זהו הדוח הראשון."
    lines = []
    for w in history:
        m = w.get("metrics", {})
        ws = w.get("week_actual", {})
        plan = w.get("recommended_plan") or {}
        comp = w.get("compliance") or {}
        lines.append(f"**שבוע {w.get('week_of', '?')}**")
        lines.append(f"- CTL={m.get('ctl','?')}  ATL={m.get('atl','?')}  ACWR={m.get('acwr','?')}  TSB={m.get('tsb','?')}")
        lines.append(f"- ביצוע: {ws.get('run_count','?')} ריצות, {ws.get('total_km','?')} ק\"מ")
        if plan:
            lines.append(f"- תוכנית שהומלצה: {plan.get('focus','?')} | מפתח: {plan.get('key_workout','?')}")
        if comp.get("km_compliance_pct"):
            lines.append(f"- ציות לתוכנית: {comp['km_compliance_pct']}% ({comp.get('compliance_level','')})")
        lines.append("")
    return "\n".join(lines).strip()


# ── Knowledge Base ───────────────────────────────────────────────────────────

# סדר עדיפות מאגר הידע — הראשונים נטענים קודם ומקבלים משקל גבוה יותר.
# 1. פרופיל אישי  2. תוכנית מאקרו  3. מסגרת המשוב  4. בסיס ראיות אקדמי  5. ניהול עומסים.
KB_PRIORITY = {
    "user_profile.md": 0,
    "macro_plan.md": 1,
    "feedback_framework.md": 2,
    "academic_research.md": 3,
    "load_management.md": 4,
}


def load_knowledge_base() -> str:
    """קורא את כל קובצי ה-.md לפי עדיפות (אישי → תוכנית → ראיות אקדמיות → השאר).
    כל קובץ מחקר שמוסיפים נכנס אוטומטית."""
    if not KB_DIR.exists():
        return ""
    md_files = sorted(KB_DIR.glob("*.md"))
    md_files.sort(key=lambda p: (KB_PRIORITY.get(p.name, 99), p.name))
    parts = []
    for path in md_files:
        content = path.read_text(encoding="utf-8")
        parts.append(f"## {path.name}\n\n{content}")
    return "\n\n---\n\n".join(parts)


# ── System Prompt ────────────────────────────────────────────────────────────

# M2.3: הקבועים של המתאמן מוזרקים לפרומטים מ-athlete.py — מקור-אמת אחד,
# קוד ופרומט לא יכולים לסתור (למשל קצב Z2 אמיתי מול יעד שגוי בתוכנית).
ATHLETE_PROMPT_VARS = dict(
    z2_low=athlete.Z2_LOW, z2_high=athlete.Z2_HIGH,
    easy_pace=athlete.EASY_PACE_RANGE, threshold_pace=athlete.THRESHOLD_PACE,
    strides_pace=athlete.STRIDES_PACE_RANGE, cadence_target=athlete.CADENCE_TARGET,
    goal_race=athlete.GOAL_RACE_LABEL, long_cap=athlete.LONG_RUN_CAP_KM,
)

SYSTEM_PROMPT_TEMPLATE = """
אתה מאמן ריצה מוסמך — ישיר, מקצועי, ומבוסס על מדע. אתה מדבר בגוף שני לספורטאי.
הדוח שלך נכתב בעברית. אתה אוסר על עצמך "מתמטיקה וירטואלית" — אם נתון לא קיים בנתונים, כתוב "נתון לא זמין".

## בסיס הידע שלך
{knowledge_base}

## עדיפות מקורות (חובה)
בסיס הידע האישי שלמעלה **קודם** לידע כללי שלך. בסתירה בין מקורות, העדף לפי הסדר:
1. מקורות **אקדמיים peer-reviewed** (📗) — הגבוה ביותר.
2. מקורות **מאומתים** (📘 פלטפורמות/ארגונים מקצועיים).
3. מקורות **מהימנים** (📙 מדריכי מאמנים).
4. ידע כללי — רק כשאין כיסוי במאגר.
בנוסף: העדף מקור **עדכני יותר** ו**רמת ראיות גבוהה יותר**. אם ההמלצה נשענת על מקור — ציין אותו.

## כללי דוח
1. אל תחזור על הנתונים הגולמיים — תפרש אותם.
2. כל המלצה על קצב חייבת להתבסס על נתוני דופק מהנתונים, לא על ניחוש.
2א. **ריצת איכות/טמפו/אינטרוולים — לעולם אל תתאר אותה לפי קצב ממוצע אחד** (הממוצע
   מערבב חימום+שחרור+מנוחות ומטעה). השתמש ב"פירוק ריצות איכות השבוע" שבנתונים ונתח
   בנפרד: **חימום · קצב הסט העיקרי · שחרור**. לדוגמה: אל תכתוב "טמפו 5.5ק\"מ @6:01" —
   כתוב "סט עיקרי 3ק\"מ @4:50, חימום+שחרור קלים". אם הפירוק חסר — ציין זאת, אל תמציא ממוצע.
3. אם ACWR > 1.5 — הזהר ברמה גבוהה לפני הכל.
4. אם Body Battery < 50 או Sleep Score < 60 — אסור להמליץ על אימון קשה.
5. כתוב בצורה ישירה: "עשה X", לא "אולי כדאי לשקול X".
6. כל תוכנית שבוע חייבת לכלול ימים, קצב, מרחק, zone.
7. בניתוח שבוע שעבר — התייחס לציות לתוכנית שהמלצת בשבוע הקודם (אם קיימת).
8. בניתוח מגמות — הצבע על שינויים חיוביים או שליליים ביחס לשבועות קודמים.
9. אם Neuromuscular ATL > 15 או "days_since_last" < 2 — אל תמליץ על ריצות מהירות/אינטרוולים יום לאחר אימון כוח.
10. כלול אימוני כוח בתוכנית השבועית — קבע ימים שבהם הכוח ישולב עם הריצה (לא על ימי Z2/שחזור).
11. **חיבור למאקרו (קריטי):** תוכנית השבוע נגזרת מהמיקום בתוכנית 14 השבועות — נפח, מיקוד, ו-long run לפי יעדי הפאזה (Base/Build/Peak/Taper). אם שבוע deload — הורד נפח ~40% ושמור עצימות. אם שבוע גייט — ציין במפורש את הערכת ה-VDOT מ-4 השבועות והאם להאיץ/להאריך את הפאזה.
12. **דגלים אדומים קודמים לכל:** אם יש דגל 🔴 — טפל בו לפני יעדי המאקרו. בטיחות לפני תוכנית.
13. **גיוון אימוני האיכות (חובה — אל תיתן רק טמפו):** המאקרו קובע את **כוונת** האיכות של הפאזה
    (Base=סף/טמפו, Build=intervals סף, Peak=VO2max/race-pace) — כבד אותה. אבל **אל תחזור
    על אותו מבנה איכות מדויק שבוע אחרי שבוע**. גוון את **צורת** הביצוע סביב מטרת הפאזה:
    - **Base:** סובב בין tempo רציף, cruise-intervals (2–3×1.5ק"מ @סף), ו-tempo + strides
      (6–8×100מ' מהירים בסוף). אפשר להוסיף מגע נוירו-מוסקולרי קל (strides/גבעות קצרות) גם
      בשבוע טמפו — שומר על מהירות הרגליים בלי לשבור את ה-Base.
    - **Build:** סובב בין threshold רציף, intervals (5–6×1ק"מ), ו-cruise-intervals ארוכים.
    - **Peak:** סובב בין VO2max (400/800/1000מ'), race-pace continuous, ו-fartlek מובנה.
    - בדוק ב"ציות/היסטוריה" איזה סוג איכות בוצע לאחרונה — והצע **משהו שונה** בצורתו השבוע
      (תוך שמירה על אותה מטרה פיזיולוגית ועצימות הפאזה). אם פאזה מצריכה 2× איכות — שתיהן
      לא זהות (למשל אחת intervals ואחת tempo).
    - הסבר במשפט אחד *למה* בחרת את צורת האיכות הזו השבוע (גיוון/מטרה/מה בוצע לאחרונה).

## התאמת תוכנית לפי ביצוע בפועל (Adaptive)
התוכנית חייבת להגיב למה שהמתאמן *באמת* עשה שבוע שעבר (שדה "ציות לתוכנית"):
- **ציות מלא (≥90%):** התקדם רגיל — אפשר להעלות נפח/עצימות בזהירות (תוך כיבוד ACWR).
- **ציות חלקי (70–89%):** התקדמות מתונה בלבד. אל תקפיץ עומס כדי "לפצות".
- **ציות נמוך (<70%):** אל תעלה עומס כלל. בנֵה תוכנית קרובה למה שבוצע בפועל + תוספת קטנה. אל תנסה "להשלים" אימונים שפוספסו — זה מקפיץ ACWR ומסכן בפציעה.
- **אימון מפתח פוספס:** תן לו עדיפות השבוע (העבר אותו קדימה), אל תוסיף אותו *מעל* התוכנית הרגילה.
- **חריגה כלפי מעלה (ביצע הרבה יותר מהמתוכנן):** הזהר מפני עומס יתר, שקול שבוע קל יותר.
- אם אין היסטוריה/ציות — בנה תוכנית בסיס שמרנית, וציין שזו נקודת התחלה למעקב.
- תמיד הסבר במשפט אחד *איך* התוכנית הותאמה לביצוע של שבוע שעבר.

## פורמט חובה — בסיום הדוח
בסיום הדוח (אחרי כל הסעיפים), הוסף בדיוק את הבלוק הבא (JSON תקני):

---PLAN_JSON---
{{
  "run_count": <מספר ריצות מתוכנן>,
  "total_km_approx": <ק"מ משוערים לשבוע>,
  "focus": "<מיקוד השבוע — לדוגמה: בסיס אירובי / סף חלבי / שחזור>",
  "key_workout": "<תיאור קצר של האימון המרכזי>"
}}
---END_PLAN---

## פורמט חובה שני — תוכנית מובנה לשבוע הבא
אחרי בלוק ה-PLAN_JSON, הוסף בלוק שני עם **כל אימוני השבוע הבא** לפי הסכמה הזו.
זהו הקובץ שיוזן אוטומטית לגרמין וליומן — דייק בו.
- ריצות: type=run, subtype=easy/quality/long, name קצר, est_km, pace בפורמט "m:ss".
- כוח: type=strength, key=A/B/C (A=Pull/משיכה, B=Push/דחיפה, C=Legs/רגליים). פיצול PPL לפי הפרופיל.
- כבד את כל הכללים: ריצה בבוקר/כוח בערב, רגליים (C) רחוק מאיכות/לונג, long ≤{long_cap} ק"מ, 80/20.
- **חובה (ידע אישי):** הריצה שאחרי יום רגליים (C) היא **ריצת התאוששות קלה (Z1)** — לא base/Z2 ולא איכות. רגליים מתישים אותו ופוגעים בריצות הבאות. אל תשבץ C יום לפני לונג; ושמור ≥48ש' בין C ללונג/איכות.
- **חובה — המשכיות בין שבועות:** ראה את "רצף אימוני כוח" (האימון האחרון של שבוע שעבר). **התחל את השבוע באימון הבא ברוטציה, לא באותו אימון** — אחרת ייווצרו שני אימוני Push (או Pull) ברצף חוצה-שבועות. שמור גם בתוך השבוע: לעולם לא אותו אימון פלג-גוף עליון יומיים ברצף.
- **מבנה השבוע של הגיא (חובה — "עושה סדר" 22.06):**
  • **שבת = ריצת הנפח** (long/volume) של השבוע.
  • **היום שאחרי כוח רגליים (C) = ריצת התאוששות קלה מאוד (Z1)** — קצרה וקלה, לא נפח.
  • **היום שאחרי אינטרוולים = בלי ריצה** (מנוחה מריצה; כוח עליון מותר).
  • **כל שאר הימים ורסטיליים** — חופש לשבץ נפח/קל בתוכם לפי 80/20 והמאקרו.
- **חובה — אל תחתוך נפח כדי "לשחק בטוח":** התאמות (יום מנוחה, ריצת התאוששות) משנות **מיקום ועצימות**, לא את **סך הק"מ השבועי**. שמור על יעד הנפח של המאקרו (אלא אם דגל בטיחות אמיתי: ACWR>1.5 / פציעה / deload). אם מורידים יום ריצה — פזר את הק"מ לימים אחרים, אל תאבד אותם.
- **חובה — strides:** בכל אימון עם strides, ה-desc חייב לכלול **קצב + סיבה**: "6×100מ' בקצב ~{strides_pace}/ק\"מ (מהיר ורגוע, **לא ספרינט**), קדנס {cadence_target}+, התאוששות מלאה (הליכה) בין חזרות. מטרה: כלכליות ריצה + קצב צעדים מהיר (הפער של הגיא) + גיוס נוירו-שרירי והכנה לקצב המרוץ — בלי לצבור עייפות."
- **חובה — בחינת היתכנות שבועית (אדפטיבית):** המאקרו הוא **שלד**, לא חוק. לפני סגירת יעד הנפח, בחן אותו מול המצב **בפועל**: ACWR, בסיס כרוני (ממוצע 4 שבועות), ציות שבוע שעבר, ותחושת המתאמן.
  • יעד המאקרו קופץ **>12%** מעל מה שבוצע שבוע שעבר, או דוחף **ACWR>1.4** → **הקטן** ליעד בר-ביצוע (~+10% מהבפועל).
  • התאושש מצוין + ציות מלא + היעד שמרני מדי → אפשר **להעלות** מעט (עד גבול הבטיחות).
  • הבחן בין **נפח ריצה אמיתי** ל**הליכה/Z1** (עומס ~אפסי — לא נספר כקפיצה).
  • סיים תמיד עם משפט: "**היעד הזה בר-ביצוע השבוע כי...**" (מבוסס נתונים). זה מה שהופך את התוכנית לחיה ולא תיאורטית.
- date = תאריך מלא YYYY-MM-DD. week_of = יום ראשון של השבוע הבא.

---WEEK_PLAN_JSON---
{{
  "week_of": "<YYYY-MM-DD>",
  "macro_week": <מספר שבוע במאקרו>,
  "phase": "<Base/Build/Peak/Taper>",
  "sessions": [
    {{"date": "<YYYY-MM-DD>", "type": "strength", "key": "B"}},
    {{"date": "<YYYY-MM-DD>", "type": "run", "subtype": "quality", "name": "סף 3 ק\"מ @ 5:10", "est_km": 5.5, "pace": "5:10"}}
  ]
}}
---END_WEEK_PLAN---

## פורמט חובה שלישי — הודעת הטלגרם המובנית
אחרי WEEK_PLAN_JSON, הוסף בלוק שלישי עם תמצית מובנית לטלגרם.

### עקרונות כתיבה (מחייבים — כתוב כמו מאמן אישי, לא כמו מערכת BI)
1. **אל תחזור על אותה תובנה.** אם זיהית בעיה מרכזית (למשל יותר מדי זמן ב-Z3) — ציין אותה
   **פעם אחת בלבד**, במקום המתאים ביותר. לא בכותרת, גם בניתוח, גם בנקודות, גם בדגש.
2. **כל מדד חייב לקבל משמעות.** אסור מספר חשוף. לא "מונוטוניות 2.01" אלא
   "השבוע היה מעט אחיד בעומסים (מונוטוניות 2.01), עם פחות הפרדה בין ימים קלים לקשים".
   כל מספר עונה על "למה אכפת לי מזה?".
3. **תרגם נתונים לשפה אנושית.** לא "VDOT 36.9 מול 38.3" אלא "הפער הצטמצם ל-1.4 נקודות בלבד,
   היעד בהישג יד אם המגמה תימשך".
4. **בלי ז'רגון.** אסור: "קיטוב לפני נפח", "On-track", "junk miles", "אופטימיזציית עצימות",
   "הרג את ה-Z3". העדף שפת מאמן אמיתי.
5. **התמקד בעיקר.** בחר **נושא מרכזי אחד** שמוביל את הסיכום. בסיום הקריאה הספורטאי צריך לדעת:
   "מה הדבר הכי חשוב שעליי לעבוד עליו השבוע".

### מילוי השדות
- **headline** = 🧭 המיקוד המרכזי — **משפט אחד** ברור ופרקטי (לא טכני). הנושא שמוביל את כל הסיכום.
- **compass** = 🎯 תמונת מצב לקראת היעד — 2–4 משפטים: איפה אתה מול {goal_race}, מה הפער, האם
  הכיוון חיובי, מה הגורם המרכזי שיקדם. הקשר — לא הצפת מספרים.
- **week_analysis** = 📊 ניתוח השבוע — פסקה (5–6 משפטים מקס'): מה עבד, מה פחות, מה למדנו.
  לא רשימת נתונים יבשה. ריצת איכות — לפי מקטעים (כלל 2א), לא קצב ממוצע.
- **wins** = ✅ נקודות חוזק — 2–4 פריטים, כל אחד **משמעות** ולא נתון גולמי
  ("התאוששות טובה והגעה רענן לרוב האימונים", לא "BB 86–100").
- **concerns** = ⚠️ לתשומת לב — עד 3 פריטים, כל אחד בתבנית **בעיה → משמעות**.
- **plan_summary** = 🗓️ תוכנית השבוע הבא — תמציתי בלבד, **ללא ניתוח** (רק יום: אימון).
- **focus** = 🎯 דגש השבוע — **משימה אחת בלבד**, קונקרטית.
- **tip** = 💡 טיפ מעשי — טיפ **אחד** אופרטיבי, מבוסס נתוני השבוע, שאפשר לבצע כבר באימון הבא.

---WEEKLY_REPORT_JSON---
{{
  "headline": "<משפט אחד — המיקוד המרכזי, פרקטי ולא טכני>",
  "compass": "<2-4 משפטים: איפה אתה מול {goal_race}, הפער, הכיוון>",
  "week_analysis": "<פסקה 5-6 משפטים: מה עבד/לא, מה למדנו>",
  "wins": ["<חוזק 1 — משמעות>", "<חוזק 2 — משמעות>"],
  "concerns": ["<בעיה → משמעות>", "..."],
  "plan_summary": ["<יום: אימון קצר>", "..."],
  "focus": "<משימה אחת קונקרטית>",
  "tip": "<טיפ מעשי אחד, מבוסס נתוני השבוע>"
}}
---END_WEEKLY_REPORT---

## שער הכרעה — קונפליקט מאקרו↔מציאות
אם בנתונים סומן דגל קונפליקט (המאקרו דורש עליית נפח אבל המציאות מסויגת) — **אל תכריע לבד**.
ב-WEEK_PLAN_JSON החזר במקום "sessions" שני שדות: "variant_a" (נאמן למאקרו) ו-"variant_b"
(שמרני, קרוב לבוצע) — כל אחד מערך sessions מלא לפי אותה סכמה. הוסף "conflict": true ו-
"tradeoff": "<משפט מסביר>". ב-headline הסבר שנדרשת בחירה (A/B).
"""


# ── Trend Formatting ────────────────────────────────────────────────────────

def _format_trends(trends: dict) -> str:
    if not trends:
        return "נתוני מגמות לא זמינים."
    ef = trends.get("ef", {})
    vo2 = trends.get("vo2max", {})
    cad = trends.get("cadence", {})
    vdot = trends.get("vdot", {})
    lines = [
        f"**Efficiency Factor (Z2 בלבד):** נוכחי={ef.get('current','?')} | מגמה={ef.get('trend_direction','?')} (slope={ef.get('trend_slope','?')}) | {ef.get('z2_runs_analyzed',0)} ריצות",
        f"**VO2max (גרמין):** נוכחי={vo2.get('current','?')} | מגמה={vo2.get('trend_direction','?')} (slope={vo2.get('trend_slope','?')}) | {vo2.get('readings_analyzed',0)} מדידות",
        f"**קדנס:** נוכחי={cad.get('current_avg_spm','?')} spm | מגמה={cad.get('trend_direction','?')} | פער מיעד 180: {cad.get('gap_to_target','?')} spm",
        f"**VDOT (Jack Daniels):** {vdot.get('estimate','?')} | בסיס: {vdot.get('basis','?')}",
    ]
    return "\n".join(lines)


# ── User Prompt ──────────────────────────────────────────────────────────────

def build_user_prompt(metrics: dict, history: list[dict], compliance: dict) -> str:
    history_md = format_history_for_prompt(history)
    compliance_md = (
        f"- שבוע קודם: {compliance['prior_week_of']}\n"
        f"- מיקוד מומלץ היה: {compliance['plan_focus']}\n"
        f"- אימון מפתח מומלץ: {compliance['plan_key_workout']}\n"
        f"- ריצות: תוכנן {compliance['planned_runs']}, בוצע {compliance['actual_runs']}\n"
        f"- ק\"מ: תוכנן ~{compliance['planned_km_approx']}, בוצע {compliance['actual_km']}"
        + (f"\n- ציות: {compliance['km_compliance_pct']}% ({compliance['compliance_level']})" if compliance.get('km_compliance_pct') else "")
        if compliance.get("available") else f"- {compliance.get('reason', 'לא זמין')}"
    )

    _last_seq = (history[-1].get("strength_sequence") if history else None) or []
    last_strength_md = (
        f"רצף הכוח שבוע שעבר: {' → '.join(_last_seq)} · **האחרון היה {_last_seq[-1]}**. "
        f"המשך מכאן — אל תתחיל את השבוע באותו אימון (Push/Pull) שסיים את השבוע שעבר."
        if _last_seq else "אין רצף כוח קודם — התחל רוטציה רגילה."
    )

    try:
        import journal
        journal_md = journal.recent_notes_md(14)
    except Exception:
        journal_md = "אין הערות מהמתאמן."

    macro_md = format_macro_for_prompt(metrics.get("macro", {}))

    f4 = metrics.get("fitness_4week", {})
    if f4.get("available"):
        fitness_md = (
            f"- VDOT (4 שבועות): {f4.get('vdot','?')} | בסיס: {f4.get('vdot_basis','?')}\n"
            f"- נפח שבועי ממוצע: {f4.get('weekly_km_avg','?')} ק\"מ ({f4.get('runs')} ריצות ב-28 יום)\n"
            f"- קצב סף משוער (Z4): {f4.get('threshold_pace','לא זמין')} ({f4.get('threshold_runs',0)} ריצות)\n"
            f"- EF ממוצע (Z2): {f4.get('ef_z2_avg','?')} ({f4.get('z2_runs',0)} ריצות)"
        )
    else:
        fitness_md = "אין מספיק ריצות ב-4 השבועות האחרונים למדידת כושר."

    red_flags = metrics.get("red_flags", [])
    if red_flags:
        flags_md = "\n".join(
            f"- {rf['severity']} **{rf['flag']}** — {rf['detail']} → {rf['action']}"
            for rf in red_flags
        )
    else:
        flags_md = "אין דגלים אדומים פעילים. ✓"

    return f"""
## נתוני האתלט — {date.today().isoformat()}

### 🎯 מיקום בתוכנית המאקרו (חיבור מיקרו↔מאקרו)
{macro_md}

**חובה:** תוכנית השבוע חייבת להיגזר מהמיקום במאקרו למעלה — נפח, מיקוד, ו-long run לפי יעדי הפאזה, מותאמים לביצוע בפועל.

### 📊 כושר נוכחי (נמדד מ-4 שבועות, לא אימון בודד)
{fitness_md}

### 🚩 דגלים אדומים
{flags_md}

### היסטוריה — 4 שבועות אחרונים
{history_md}

### ציות לתוכנית שבוע שעבר
{compliance_md}

### 🗒️ הערות המתאמן (יומן — חובה להתחשב!)
{journal_md}
**אם הגיא דיווח על שינוי שביצע (קיצר ריצה), כאב, שינה גרועה או עייפות — קח בחשבון: אל תסמן כחוסר-ציות מה שהיה החלטה מודעת, והתאם את השבוע הבא בהתאם (למשל עומס/התאוששות).**

### המשכיות אימוני כוח (חובה)
{last_strength_md}

### עומס אימונים (CTL/ATL)
- CTL (כושר כרוני, 42 יום): {metrics['load']['ctl']}
- ATL (עייפות חריפה, 7 יום): {metrics['load']['atl']}
- TSB (מאזן): {metrics['load']['tsb']}
- ACWR (יחס עומס): {metrics['load']['acwr'] or 'לא ניתן לחשב (CTL=0)'} {metrics['acwr_status']['flag']} ({metrics['acwr_status']['level']})
  → {metrics['acwr_status']['message']}
- קצב עלייה ב-4 שבועות: {metrics['load']['ramp_rate_4w']}

### מונוטוניות אימון (Foster) — 7 ימים
- מונוטוניות: {metrics['monotony'].get('monotony', 'לא זמין')} {metrics['monotony'].get('flag', '')} ({metrics['monotony'].get('level', '')})
- Strain (עומס×מונוטוניות): {metrics['monotony'].get('strain', 'לא זמין')}
  → {metrics['monotony'].get('message', '')}

### ערנות / מוכנות (3 ימים אחרונים)
{json.dumps(metrics['readiness'], ensure_ascii=False, indent=2)}

### התפלגות Zones (28 יום אחרונים)
{json.dumps(metrics['zones'], ensure_ascii=False, indent=2)}

### שבוע שעבר (7 ימים אחרונים)
{json.dumps(metrics['last_week'], ensure_ascii=False, indent=2)}

### שיאים אישיים
{json.dumps(metrics['prs'], ensure_ascii=False, indent=2)}

### Max HR (מדוד מנתוני גרמין)
{metrics['global_max_hr']} bpm

### אימוני כוח — שבוע שעבר
{json.dumps(metrics['strength'], ensure_ascii=False, indent=2)}

### עומס נוירומוסקולרי (Neuromuscular ATL, 7 יום)
{metrics['nm_atl']} (לעומת Aerobic ATL: {metrics['load']['atl']})

### מגמות כושר (8 שבועות אחרונים)
{_format_trends(metrics['trends'])}

---

כתוב דוח אימונים מלא בעברית עם הסעיפים הבאים:

## 1. מצב נוכחי — עייפות / ערנות / כושר
ניתוח קצר (3-5 משפטים) על המצב הנוכחי. אם יש היסטוריה, ציין מגמות.

## 2. ניתוח שבוע שעבר
פירוט לכל אימון: מה היה טוב, מה לשפר. כולל ניתוח zones, קצב דופק.
אם יש ציות לתוכנית — העריך את הביצוע מול ההמלצה.

## 3. תוכנית שבוע הבא
לכל יום: ריצה / מנוחה / כוח. לריצות: zone, מרחק, קצב יעד בדקות:שניות לק"מ.

## 4. אזהרות וסיכונים
ACWR (כולל דגל הצבע 🔴/🟡/🟢), מונוטוניות אימון, ramp rate, דריפט, עומס נוירומוסקולרי, כל דגל אדום רלוונטי.
אם דגל ה-ACWR אדום או צהוב — התייחס אליו ראשון. אם מונוטוניות מעל 2.0 — הזהר על חדגוניות.

## 5. מגמות כושר
EF, VO2max, קדנס, VDOT — מה השתנה? לאן פנים? מה המשמעות לאימון?
"""


# ── Morning Readiness Loop ────────────────────────────────────────────────────

POSTWORKOUT_SYSTEM = """
אתה מאמן ריצה אישי. זוהי **אנליזת אחרי-אימון** — אחרי שהמתאמן סיים אימון היום.
תפקידך לתת משוב מפורט על האימון, להתאים את אימון מחר, ולזהות דגלים אדומים.

## בסיס הידע שלך
{knowledge_base}

## פירוש RPE ו-Feel (חשוב!)
- **Feel = סיגנל מוכנות סובייקטיבי, לא מדד איכות.** "הרגיש חלש" ≠ "אימון גרוע".
- שפוט את האימון לפי **התוצאה האובייקטיבית** (קצב מול מתוכנן, דופק, drift) — לא לפי ההרגשה.
- אם הרגיש חלש אבל **ביצע טוב** (עמד/שיפר קצב, דופק סביר) → זה **חיובי** (דחף דרך תחושה, הגוף היה מסוגל). אל תזהיר.
- דאגה רק כש**גם** ההרגשה חלשה **וגם** הביצוע נפל (קצב אטי מהמתוכנן/דופק גבוה). RPE נמוך בקצב מהיר = כושר טוב.

## מבנה הניתוח (3 חלקים — חובה את כולם)
### חלק א' — משוב מפורט
- מתוכנן מול בוצע: מרחק, קצב, זונות דופק, משך.
- איכות ביצוע: עמד בקצב היעד? cardiac drift? עקביות splits? דפוס pacing?
- ציון compliance (0-100) ומה היה טוב / מה לשפר.
- הקשר מאקרו: האם האימון תרם למטרת הפאזה הנוכחית?

### חלק ב' — אדפטציה לאימון מחר
- אם היום היה קשה מהצפוי → מחר קל יותר.
- אם הוחמץ/קוצר → השלמה חלקית בלבד (לא 100%, מסכן ACWR).
- אם היה קל וטוב → מחר כמתוכנן (אל תוסיף עומס).

### חלק ג' — דגלים אדומים 🚩
התייחס לדגלים שזוהו. כל כאב ברך/קרסול אחרי 10+ ק"מ = 🔴.

## כללים
1. ישיר וקונקרטי. מבוסס נתונים, לא ניחוש.
2. אל תמציא נתון שלא קיים — כתוב "לא זמין".
3. בטיחות לפני התקדמות.
4. **ריצה קלה/Z2 — שפוט לפי דופק, לא קצב!** אם הדופק ב-Z2 ({z2_low}–{z2_high}), הקצב (גם {easy_pace}) הוא **נכון ומכוון** — הקצב הקל נגזר מהכושר האירובי, זו לא "טעות" ולא "איטי מהיעד". **אסור** לרשום ב-improve "קצב איטי מהיעד" לריצה קלה שרצה בדופק הנכון. יעד הקצב בתוכנית הוא הערכה בלבד; הדופק גובר.
5. **ה-improve חייבים להיות דברים אמיתיים לשיפור** (קדנס, זמן ב-Z3, יציבות) — לא "רצת לאט" כשרצת נכון לפי דופק.

## פורמט פלט (בסוף, אחרי הניתוח המילולי — JSON תקני להודעת הטלגרם):
- "planned" = שם האימון הקונקרטי מ-week_plan (למשל "Long Run 9 ק\"מ Z2"), לא תיאור מאקרו כללי.
- "actual" = מרחק · קצב · משך · דופק ממוצע · **קדנס** · **GCT (פגיעה בקרקע)**.
- "improve" = בדיוק 2 דגשים. **בחר לפי "משפחות מדדי ריצה" בבסיס הידע** — מדדים מאותה משפחה (קדנס↔יחס אנכי↔GCT = turnover) הם **תיקון אחד**: עוגן אחד לשורש, לא דגש לכל מדד. בחר את 2 המשפחות החורגות ביותר.
  **כל דגש = משפט אחד קצר עם שרשרת מלאה: מדד → פירוש קצר → פעולה עם עוגן שקל לזכור בריצה.**
  דוגמה טובה (מאחדת משפחה): "קדנס 171 (מעט נמוך) — וממנו גם יחס אנכי גבוה ו-GCT ארוך → העלה קצב צעדים, חשוב 'רגליים מהירות וקלות, נמוך לקרקע'." (מדד→שורש→עוגן אחד).
  דוגמה רעה (אסור): "יחס אנכי גבוה, תשפר." (אין פירוש, אין עוגן) — או שני דגשים נפרדים לקדנס וליחס אנכי (זו כפילות — אותה משפחה).
  מבוסס **נתוני אמת בלבד**. **אסור** להמציא אירועים (double session, ריצת בוקר) — נותחה פעילות אחת.
- "keep" = **משפט אחד קצר** בשרשרת: מדד → **למה זה טוב** → חיזוק. מסתובב בין **קדנס · GCT · יציבות קצב · נשימה · drift · צעד**. דופק **לא** הדגש (מובן מאליו) — לכל היותר הערת-צד.
- **חובה — כל מדד שאתה מזכיר מקבל "אז מה":** פירוש קצר (תקין/גבוה/נמוך + מה המשמעות). **אל תזרוק מספר בלי משמעות.** אם מדד לא תורם להחלטה — אל תזכיר אותו בכלל.
- **פעולות = אופרטיביות וקונקרטיות**, לא כלליות. "בדוק ברך" → "בדוק כאב/נוקשות בברך לפני היציאה". תמיד עוגן שאפשר לזכור תוך כדי ריצה.
- "red_flags" = רק מהרשימה הדטרמיניסטית שניתנה. ריק [] אם אין. **אל תמציא דגלים.**
- "next" = אימון מחר. **אם היום שבת** — התוכנית לשבוע הבא עדיין לא קיימת, אז **אל תדבר על האימון הבא/התוכנית**; תן רק **מילה טובה קצרה** על סגירת השבוע.
---POSTWORKOUT_JSON---
{{
  "category": "<קטגוריה בעברית: ריצה קלה | טמפו | אינטרוולים | ריצה ארוכה | כוח>",
  "planned": "<שם האימון הקונקרטי של היום מהתוכנית>",
  "actual": "<מרחק · קצב · משך · דופק ממוצע · קדנס · GCT>",
  "improve": ["<דגש לשיפור 1 — מנתוני האימון בלבד>", "<דגש לשיפור 2>"],
  "keep": "<דגש שימור — קדנס/GCT/יציבות/נשימה, לא דופק>",
  "red_flags": ["<רק מהרשימה הדטרמיניסטית; ריק אם אין>"],
  "next": "<אימון מחר>"
}}
---END_POSTWORKOUT---
"""


def _next_sessions_md(run_done_today: bool = False) -> str:
    """מחזיר את האימונים המתוכננים להמשך היום + מחר מ-week_plan.json (לשדה next).
    run_done_today=True → מדלג על ריצת היום (כבר בוצעה) כדי לא להמציא double session.
    בשבת (סוף השבוע) → אין תוכנית לשבוע הבא עדיין (נבנית בערב), אז לא מדברים על ההמשך."""
    if date.today().weekday() == 5:  # שבת = היום האחרון בשבוע, לפני בניית התוכנית החדשה
        return ("היום שבת — הריצה המסכמת של השבוע. התוכנית לשבוע הבא עדיין לא קיימת "
                "(נבנית הערב). שדה next = מילה טובה קצרה על סגירת השבוע, **בלי** המלצת אימון/תוכנית.")
    wp = BASE_DIR / "week_plan.json"
    if not wp.exists():
        return "אין week_plan.json — הסק את אימון מחר מהפאזה במאקרו."
    try:
        plan = json.loads(wp.read_text(encoding="utf-8"))
    except Exception:
        return "week_plan.json לא קריא — הסק מהמאקרו."
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    sessions = plan.get("sessions", [])

    def _fmt(s):
        if s.get("type") == "run":
            nm = (s.get("name") or f"ריצה {s.get('subtype','')}").strip()
            prefix = "" if nm[:1] in "🏃🚶" else "🏃 "
            return f"{prefix}{nm}"
        return f"💪 כוח {s.get('key','')}"

    # האימון/ים הבא/ים = היום מה שנשאר (כוח, או ריצה אם עוד לא בוצעה), אחרת
    # היום הקרוב ביותר בעתיד עם אימונים. **כל הסוגים** (ריצה + כוח), לפי התוכנית בפועל —
    # לא ניחוש מהמאקרו, ולא רק ריצות.
    today_remaining = [s for s in sessions if s.get("date") == today
                       and (s.get("type") == "strength"
                            or (s.get("type") == "run" and not run_done_today))]
    if today_remaining:
        day, group = today, today_remaining
    else:
        future = sorted({s.get("date") for s in sessions if s.get("date", "") > today})
        if not future:
            return "אין אימון נוסף מתוכנן השבוע."
        day = future[0]
        group = [s for s in sessions if s.get("date") == day]

    if day == today:
        label = "היום (בהמשך)"
    elif day == tomorrow:
        label = "מחר"
    else:
        wd = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][date.fromisoformat(day).weekday()]
        label = f"{wd} ({day[5:]})"
    return f"{label}: " + " + ".join(_fmt(s) for s in group)


def _todays_planned_run_md() -> str:
    """שם האימון המתוכנן של היום מ-week_plan.json — לעיגון שדה planned (לא ניחוש מהמאקרו)."""
    wp = BASE_DIR / "week_plan.json"
    try:
        plan = json.loads(wp.read_text(encoding="utf-8"))
    except Exception:
        return "—"
    today = date.today().isoformat()
    runs = [s for s in plan.get("sessions", []) if s.get("date") == today and s.get("type") == "run"]
    if not runs:
        return "אין ריצה מתוכננת היום בתוכנית."
    return " · ".join((s.get("name") or s.get("subtype", "ריצה")) +
                      (f" — {s['desc']}" if s.get("desc") else "") for s in runs)


def _format_workout_segments(workout: dict) -> str:
    """
    מפרק את ה-laps לחימום / סט עיקרי / שחרור עם קצב+דופק לכל מקטע.
    זה מה שמאפשר משוב לא-גנרי ("הרבע השלישי נפל 8 שנ'/ק\"מ") במקום "כל הכבוד".
    """
    laps = workout.get("laps") or []
    valid = [l for l in laps if (l.get("distance_km") or 0) >= 0.2 and l.get("pace_sec_per_km")]
    if len(valid) < 3:
        return ""

    paces = [l["pace_sec_per_km"] for l in valid]
    fastest = min(paces)
    thresh = fastest * 1.15

    def _pace(s):
        return f"{s//60}:{s%60:02d}"

    rows = []
    for i, l in enumerate(valid, 1):
        p = l["pace_sec_per_km"]
        tag = "🔥 עבודה" if p <= thresh else "🟢 קל"
        rows.append(
            f"  {i}. {l.get('distance_km')}ק\"מ · {_pace(p)}/ק\"מ · "
            f"דופק {l.get('avg_hr','?')} · {tag}"
        )
    return "### פירוק לפי הקפות (חימום / סט / שחרור)\n" + "\n".join(rows)


def build_postworkout_prompt(metrics: dict, workout: dict | None) -> str:
    macro_md = format_macro_for_prompt(metrics.get("macro", {}))
    red_flags = metrics.get("red_flags", [])
    flags_md = "\n".join(
        f"- {rf['severity']} {rf['flag']}: {rf['detail']} → {rf['action']}"
        for rf in red_flags) or "אין דגלים אדומים. ✓"

    if not workout:
        workout_md = "לא נמצא אימון להיום בנתונים."
    else:
        p = workout.get("pace_sec_per_km")
        pace_str = f"{p//60}:{p%60:02d}/ק\"מ" if p else "לא זמין"
        zones = workout.get("hr_zones_sec") or [0, 0, 0, 0, 0]
        workout_md = (
            f"- תאריך: {workout['date']}\n"
            f"- סוג: {workout.get('activity_type')} | קטגוריה: {workout.get('category','?')}\n"
            f"- מרחק: {workout.get('distance_km')} ק\"מ | קצב ממוצע: {pace_str}\n"
            f"- דופק ממוצע: {workout.get('avg_hr')} | מקס: {workout.get('max_hr')}\n"
            f"- משך: {round((workout.get('duration_sec') or 0)/60)} דק'\n"
            f"- קדנס: {workout.get('cadence_spm','—')} spm | GCT (פגיעה בקרקע): {workout.get('gct_ms','—')} ms | אורך צעד: {workout.get('stride_length_m','—')} מ'\n"
            f"- תנודה אנכית: {workout.get('vertical_oscillation_cm','—')} ס\"מ | יחס אנכי: {workout.get('vertical_ratio_pct','—')}% | נשימה ממוצעת: {workout.get('avg_respiration','—')}\n"
            f"- cardiac drift: {workout.get('hr_drift_bpm','לא זמין')} bpm\n"
            f"- 🧠 דירוג סובייקטיבי: RPE {workout.get('rpe','—')}/10 · Feel {workout.get('feel','—')}/5 "
            f"(השווה לדופק/קצב — אי-התאמה = סימן עייפות)\n"
            f"- זונות (שניות Z1-Z5): {zones}\n"
            f"- 100m splits: {'כן ('+str(len(workout['splits_100m']))+' מקטעים)' if workout.get('splits_100m') else 'לא זמין'}"
        )

    run_done_today = bool(
        workout and workout.get("date") == date.today().isoformat()
        and workout.get("activity_type") in RUN_TYPES)

    try:
        import journal
        _note = journal.todays_note_md()
    except Exception:
        _note = ""
    note_md = (f"\n### 🗒️ הערת המתאמן היום (חובה להתחשב!)\n{_note}\n"
               f"**אם דיווח על שינוי מודע (קיצר), כאב או שינה גרועה — אל תזהיר על "
               f"\"חוסר ביצוע\"; התייחס לזה כהחלטה נכונה והתאם את ההמלצה למחר.**\n"
               if _note else "")

    return f"""
## ניתוח אחרי אימון — {date.today().isoformat()}
{note_md}
### האימון שתוכנן להיום (מקור-אמת — מ-week_plan.json)
{_todays_planned_run_md()}
**שדה "planned" = האימון הזה בדיוק (השם הקונקרטי), לא תיאור כללי מהמאקרו.**

### מיקום במאקרו (הקשר פאזה בלבד)
{macro_md}

### האימון שבוצע היום (נתוני אמת — זו הפעילות היחידה היום)
{workout_md}
⚠️ נותחה **פעילות אחת** היום (זו שלמעלה). אל תמציא אימונים נוספים — אין ריצת בוקר נוספת, אין double session. נתח רק את מה שמופיע כאן.

{_format_workout_segments(workout) if workout else ""}

### דגלים אדומים שזוהו (דטרמיניסטי — אל תוסיף דגלים שלא ברשימה)
{flags_md}

### עומס נוכחי
- ATL: {metrics['load']['atl']} | TSB: {metrics['load']['tsb']} | ACWR: {metrics['load']['acwr'] or 'לא זמין'} {metrics['acwr_status']['flag']}

### מתוכנן בהמשך (לשדה next)
{_next_sessions_md(run_done_today)}

---

תן ניתוח ב-3 חלקים: (א) משוב מפורט, (ב) אדפטציה לאימון מחר, (ג) דגלים אדומים.
סיים בבלוק ה-JSON לפי הפורמט.
"""


def latest_workout_today(activities: list) -> dict | None:
    """Return today's most recent run/strength workout, if any (for post-workout analysis)."""
    today = date.today().isoformat()
    todays = [a for a in activities if a.get("date") == today]
    if not todays:
        # Fall back to the single most recent workout overall
        runs = sorted([a for a in activities if a.get("activity_type") in RUN_TYPES],
                      key=lambda x: x.get("date", ""))
        return runs[-1] if runs else None
    runs = [a for a in todays if a.get("activity_type") in RUN_TYPES]
    return (runs or todays)[-1]


# ── Shared Metrics Builder ────────────────────────────────────────────────────

def build_metrics(data: dict) -> dict:
    """Compute the full metrics bundle shared by all three loops."""
    activities = data.get("activities", [])
    daily = data.get("daily", {})
    global_max_hr = data.get("global_max_hr") or float(athlete.MAX_HR_FALLBACK)

    daily_load = build_daily_load(activities)
    load_metrics = compute_ctl_atl(daily_load, date.today())
    acwr_flag = acwr_status(load_metrics["acwr"])
    monotony = compute_training_monotony(daily_load, date.today())
    zones = compute_zone_distribution(activities, days=28, global_max_hr=global_max_hr)
    last_week_runs = last_n_days_runs(activities, n=7)
    last_week = summarize_runs(last_week_runs)
    # ריצות איכות של השבוע (עם laps) — לפירוק חימום/סט/שחרור בסיכום השבועי
    last_week_quality = [a for a in last_week_runs
                         if str(a.get("category", "")).startswith("quality")]
    readiness = get_readiness(daily)
    readiness_today = morning_readiness(daily)
    prs = compute_prs(activities)
    trends = compute_fitness_trends(activities, global_max_hr, weeks=8)
    strength = compute_strength_metrics(activities, days=7)
    nm_atl = compute_neuromuscular_atl(activities, date.today())
    macro = get_macro_week(date.today())
    fitness_4week = compute_fitness_4week(activities, global_max_hr)

    metrics = {
        "load": load_metrics,
        "acwr_status": acwr_flag,
        "monotony": monotony,
        "zones": zones,
        "last_week": last_week,
        "last_week_quality": last_week_quality,
        "readiness": readiness,
        "readiness_today": readiness_today,
        "prs": prs,
        "global_max_hr": global_max_hr,
        "trends": trends,
        "strength": strength,
        "nm_atl": nm_atl,
        "macro": macro,
        "fitness_4week": fitness_4week,
    }
    metrics["red_flags"] = detect_red_flags(activities, metrics)
    metrics["run_weather"] = _today_run_weather()
    return metrics


def _today_run_weather() -> dict | None:
    """אם מתוכננת ריצה היום — המלצת מיקום (חוץ/חדר כושר) לפי מזג אוויר.
    מבדיל ארוכה/קצרה. נכשל בשקט אם אין רשת/מודול/תוכנית."""
    try:
        import weather
        wp_file = BASE_DIR / "week_plan.json"
        if not wp_file.exists():
            return None
        wp = json.loads(wp_file.read_text(encoding="utf-8"))
        today = date.today().isoformat()
        for s in wp.get("sessions", []):
            if s.get("date") == today and s.get("type") == "run":
                is_long = s.get("subtype") == "long"
                when = today + ("T08:00" if is_long else "T07:00")
                return weather.recommend(when, is_long)
    except Exception:
        return None
    return None


# מודל לכל לולאה — לפי איזון עלות/איכות שנבחר:
#   אחרי אימון (ניתוח) → Sonnet · שבועי (תכנון) → Opus
MODEL_POSTWORKOUT = "claude-sonnet-4-6"
MODEL_WEEKLY = "claude-opus-4-8"

# Haiku 4.5 לא תומך ב-effort / adaptive thinking (יחזיר 400). Sonnet/Opus כן.
_ADAPTIVE_MODELS = {"claude-sonnet-4-6", "claude-opus-4-8"}


def _stream_report(client, system_prompt: str, user_prompt: str,
                   max_tokens: int = 4096, effort: str = "high",
                   model: str = MODEL_WEEKLY) -> str:
    """Stream a Claude response to stdout and return the full text.
    effort tunes cost: 'low' (morning), 'medium' (post-workout), 'high' (weekly).
    effort/adaptive-thinking applied only on models that support them (Sonnet/Opus)."""
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system_prompt,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if model in _ADAPTIVE_MODELS:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": effort}
    full = ""
    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full += text
    return full


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("שגיאה: ANTHROPIC_API_KEY לא מוגדר.")
        print("הגדר את המשתנה לפני הרצה:")
        print("  Windows:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
        print("  Linux/Mac: export ANTHROPIC_API_KEY='sk-ant-...'")
        print("בסביבת GitHub Actions: הוסף כ-Secret בשם ANTHROPIC_API_KEY")
        sys.exit(1)

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "weekly"
    if mode not in ("weekly", "postworkout"):
        print(f"מצב לא מוכר: {mode}. השתמש ב: weekly | postworkout")
        sys.exit(1)

    print("טוען נתוני גרמין...")
    data = load_data()

    print("מחשב מדדים...")
    metrics = build_metrics(data)
    load_metrics = metrics["load"]
    macro = metrics["macro"]
    print(f"CTL={load_metrics['ctl']}  ATL={load_metrics['atl']}  ACWR={load_metrics['acwr']} {metrics['acwr_status']['flag']}")
    if macro.get("status") == "active":
        print(f"מאקרו: שבוע {macro['week_num']}/{macro['total_weeks']} · פאזת {macro['phase']}"
              + (" · DELOAD" if macro['deload'] else "") + (" · גייט" if macro['gate'] else ""))
    if metrics["red_flags"]:
        print(f"🚩 {len(metrics['red_flags'])} דגלים אדומים")

    print("טוען בסיס ידע...")
    knowledge_base = load_knowledge_base()
    client = anthropic.Anthropic()

    if mode == "postworkout":
        run_postworkout(client, knowledge_base, metrics, data)
    else:
        run_weekly(client, knowledge_base, metrics)


# ── Mode Runners ──────────────────────────────────────────────────────────────

def _format_weekly_analysis_section(analysis: dict) -> str:
    """שלב 1 כטקסט ל-prompt — עובדות דטרמיניסטיות + כותרת אדפטיבית + דגל קונפליקט."""
    p = analysis.get("priority", {})
    conf = analysis.get("conflict", {})
    lines = [
        "## ניתוח דטרמיניסטי מקדים (עובדות — הסתמך עליהן, אל תמציא)",
        f"**כותרת אדפטיבית (המסר #1 לשבוע):** {p.get('headline','')}",
        f"- מצפן/סף: {analysis.get('threshold_progress',{}).get('verdict','')}",
        f"- ציות: {analysis.get('compliance',{}).get('verdict','')}",
        f"- איזון זונות: {analysis.get('zone_balance',{}).get('verdict','')}",
        f"- עומס: {analysis.get('load_trajectory',{}).get('verdict','')}",
        f"- מאקרו: {analysis.get('macro_adherence',{}).get('verdict','')}",
        f"- כוח: {analysis.get('strength_balance',{}).get('verdict','')}",
    ]
    if conf.get("conflict"):
        lines.append(
            f"**⚖️ שער הכרעה — קונפליקט:** {conf.get('summary','')} "
            f"→ החזר variant_a (מאקרו, {conf.get('macro_target_km')}ק\"מ) "
            f"ו-variant_b (שמרני, {conf.get('conservative_target_km')}ק\"מ).")
    return "\n".join(lines) + "\n\n"


def _format_weekly_quality_segments(metrics: dict) -> str:
    """
    פירוק ריצות האיכות של השבוע לחימום/סט-עיקרי/שחרור (מתוך laps).
    בלי זה ה-LLM מתאר ריצת טמפו לפי קצב ממוצע מטעה (חימום+שחרור מערבבים אותו).
    """
    quality = metrics.get("last_week_quality") or []
    if not quality:
        return ""
    blocks = []
    for w in quality:
        seg = _format_workout_segments(w)
        cat = w.get("category", "quality")
        if seg:
            blocks.append(f"**{w.get('date','?')} · {cat} · {w.get('distance_km','?')}ק\"מ**\n{seg}")
        else:
            blocks.append(f"**{w.get('date','?')} · {cat} · {w.get('distance_km','?')}ק\"מ** "
                          f"(אין פירוק laps — אל תתאר לפי קצב ממוצע, ציין שהפירוק חסר)")
    if not blocks:
        return ""
    return ("## פירוק ריצות איכות השבוע (חובה — נתח לפי מקטעים, לא קצב ממוצע)\n"
            + "\n\n".join(blocks) + "\n\n")


def _parse_weekly_report_json(report_text: str) -> dict:
    """Extract the ---WEEKLY_REPORT_JSON--- block (the structured Telegram report).
    Hardened via the shared extractor — a markers-only parse here silently drops
    the weekly Telegram message, the same failure that hit the postworkout loop."""
    return extract_llm_json(report_text, "---WEEKLY_REPORT_JSON---", "---END_WEEKLY_REPORT---",
                            aliases={"headline": ("headline", "title"),
                                     "compass": ("compass", "vdot_gap"),
                                     "week_analysis": ("week_analysis", "analysis"),
                                     "wins": ("wins", "win"),
                                     "concerns": ("concerns", "concern"),
                                     "plan_summary": ("plan_summary", "plan"),
                                     "focus": ("focus", "tip")})


def _send_weekly_telegram(wr: dict, safety_messages: list, needs_review: bool,
                          test: bool = False) -> int | None:
    """שולח את הדוח השבועי המובנה (A–F) לטלגרם."""
    try:
        import telegram_notify as tg
    except ImportError:
        print("⚠️  telegram_notify לא זמין — מדלג על טלגרם.")
        return None

    wins = wr.get("wins") or []
    plan = wr.get("plan_summary") or []
    # concerns: list חדש; נופל אחורה ל-concern בודד לתאימות לאחור
    concerns = wr.get("concerns")
    if not concerns and wr.get("concern"):
        concerns = [wr["concern"]]
    concerns = concerns or []
    # escape לתוכן LLM (& < >) — תו בודד שובר את מצב ה-HTML של טלגרם → 400 (תקלה חוזרת).
    import html as _html
    def _e(s): return _html.escape(str(s))
    header = "🧪 <b>בדיקה — אל תפעל לפי זה</b>\n\n📅 <b>סיכום שבועי</b>" if test else "📅 <b>סיכום שבועי</b>"
    lines = [
        header,
        "",
        f"🧭 <b>המיקוד המרכזי</b>\n{_e(wr.get('headline','—'))}",
        "",
        f"🎯 <b>תמונת מצב לקראת היעד</b>\n{_e(wr.get('compass','—'))}",
        "",
        f"📊 <b>ניתוח השבוע</b>\n{_e(wr.get('week_analysis','—'))}",
    ]
    if wins:
        lines += ["", "✅ <b>נקודות חוזק</b>"] + [f"• {_e(w)}" for w in wins]
    if concerns:
        lines += ["", "⚠️ <b>לתשומת לב</b>"] + [f"• {_e(c)}" for c in concerns]
    if plan:
        lines += ["", "🗓️ <b>תוכנית השבוע הבא</b>"] + [f"• {_e(d)}" for d in plan]
    if wr.get("focus"):
        lines += ["", f"🎯 <b>דגש השבוע:</b> {_e(wr['focus'])}"]
    if wr.get("tip"):
        lines += ["", f"💡 <b>טיפ מעשי:</b> {_e(wr['tip'])}"]
    if safety_messages:
        lines += ["", "🛡️ <b>בטיחות</b>"] + [f"• {_e(m)}" for m in safety_messages]
    if needs_review:
        lines += ["", "⚠️ נדרש אישורך המפורש לפני סנכרון לגרמין."]
    else:
        lines += ["", "💬 <b>השב עם שינויים</b> (למשל \"שישי 5 ק\"מ, שבת 10, חמישי בלי ריצה\"), או <b>\"אשר\"</b> להעלאה לגרמין."]

    mid = tg.send_message("\n".join(lines))
    print(f"✅ דוח שבועי נשלח לטלגרם (message_id={mid})" if mid
          else "⚠️  דוח שבועי לא נשלח (אין credentials)")
    return mid


WEEKLY_STATE_FILE = BASE_DIR / "weekly_state.json"


def _handle_weekly_conflict(raw_week: dict, analysis: dict, metrics: dict,
                            prev_week_km: float, dry: bool = False) -> None:
    """
    שער הכרעה A/B: שולח לטלגרם את שתי האפשרויות (מאקרו מול שמרני) וכותב
    weekly_state.json. לא כותב week_plan.json — זה קורה ב-check_weekly_choice.py
    אחרי שתבחר. שני הווריאנטים נשמרים גולמיים + הקשר לבטיחות.
    """
    import time as _time
    conf = analysis["conflict"]
    base = {k: raw_week.get(k) for k in ("week_of", "macro_week", "phase")}
    state = {
        "date": date.today().isoformat(),
        "status": "pending_choice",
        "sent_at_unix": _time.time(),
        "base": base,
        "variant_a": raw_week.get("variant_a"),
        "variant_b": raw_week.get("variant_b"),
        "prev_week_km": prev_week_km,
        "macro": metrics.get("macro"),
        "acwr": metrics["load"].get("acwr"),
        "tradeoff": raw_week.get("tradeoff", ""),
    }
    if dry:
        print("🧪 בדיקה — weekly_state.json לא נכתב (שאלת A/B תישלח לתצוגה בלבד).")
    else:
        WEEKLY_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
        print(f"⚖️  weekly_state.json נכתב (status=pending_choice).")

    try:
        import telegram_notify as tg
    except ImportError:
        return
    a_km = conf.get("macro_target_km")
    b_km = conf.get("conservative_target_km")
    test_hdr = "🧪 <b>בדיקה — אל תפעל לפי זה</b>\n\n" if dry else ""
    text = (
        f"{test_hdr}📅 <b>סיכום שבועי — נדרשת הכרעה</b>\n\n"
        f"🧭 {analysis['priority']['headline']}\n\n"
        f"⚖️ <b>{conf.get('summary','')}</b>\n"
        f"{state['tradeoff']}\n\n"
        f"<b>A</b> · נאמן למאקרו — {a_km} ק\"מ (התקדמות מהירה, סיכון מעט גבוה)\n"
        f"<b>B</b> · שמרני — {b_km} ק\"מ (בטוח, קרוב למה שבוצע)\n\n"
        f"השב <b>A</b> או <b>B</b> ואבנה את התוכנית בהתאם."
    )
    mid = tg.send_message(text)
    print(f"✅ שאלת A/B נשלחה (message_id={mid})" if mid else "⚠️  A/B לא נשלח")


def run_weekly(client, knowledge_base: str, metrics: dict) -> None:
    """Weekly review — the macro-driven plan for next week. Saves history. Chat."""
    import os
    dry = bool(os.environ.get("WEEKLY_DRY_RUN"))
    if dry:
        print("🧪 מצב בדיקה (WEEKLY_DRY_RUN) — לא ייכתבו week_plan/היסטוריה/state.")
    history = load_history()
    compliance = compute_compliance(history, metrics["last_week"])
    if compliance.get("available"):
        print(f"ציות שבוע שעבר: {compliance.get('km_compliance_pct', '?')}% ({compliance.get('compliance_level', '?')})")

    # שלב 1: ניתוח דטרמיניסטי מקדים (weekly_analysis.py) — עובדות + כותרת אדפטיבית + קונפליקט
    import weekly_analysis as wa
    analysis = wa.build_weekly_analysis(metrics, compliance)
    print(f"🧭 כותרת השבוע: {analysis['priority']['headline']}")
    if analysis["conflict"]["conflict"]:
        print(f"⚖️  קונפליקט מאקרו↔מציאות: {analysis['conflict']['summary']}")

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=knowledge_base,
                                                  **ATHLETE_PROMPT_VARS)
    user_prompt = (_format_weekly_analysis_section(analysis)
                   + _format_weekly_quality_segments(metrics)
                   + build_user_prompt(metrics, history, compliance))

    print(f"🤖 מודל: {MODEL_WEEKLY} (שבועי — תכנון כבד)")
    print("קורא ל-Claude Opus (weekly, streaming)...\n")
    # 20000: דוח A–F מלא + 3 בלוקי JSON (PLAN+WEEK_PLAN+WEEKLY_REPORT) + חשיבה אדפטיבית.
    # ב-8192 (20.06) הבלוק האחרון WEEKLY_REPORT_JSON נחתך באמצע → הדוח לא נשלח לטלגרם.
    # שבועי רץ פעם בשבוע — תקרה גבוהה זולה ומונעת truncation לתמיד.
    full_response = _stream_report(client, system_prompt, user_prompt, max_tokens=20000)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    REPORT_FILE.write_text(f"# דוח מאמן שבועי — {timestamp}\n\n{full_response}\n", encoding="utf-8")

    plan_json = extract_plan_json(full_response)
    if not plan_json:
        print("\n⚠️  לא נמצא בלוק PLAN_JSON בדוח.")

    # ── כתיבת week_plan.json המובנה (הגשר לגרמין + יומן) ──────────────────
    # עובר דרך שכבת הבטיחות הדטרמיניסטית (safety.py) לפני כל כתיבה.
    raw_week = extract_week_plan(full_response)

    # דריסה דטרמיניסטית של "מתוכנן" — מספר הריצות והק"מ נלקחים מהסשנים האמיתיים
    # של ה-WEEK_PLAN, לא ממספר שה-LLM כתב ב-PLAN_JSON. אי-התאמה ביניהם גרמה
    # ל"ציות חלקי 4/5" שגוי גם כשבוצעה כל התוכנית (20.06). כך הציות מדויק.
    if plan_json is not None:
        _run_sessions = [s for s in ((raw_week or {}).get("sessions") or [])
                         if s.get("type") == "run"]
        if _run_sessions:
            plan_json["run_count"] = len(_run_sessions)
            plan_json["total_km_approx"] = round(sum((s.get("est_km") or 0) for s in _run_sessions), 1)
    prev_week_km = metrics["last_week"].get("total_km", 0) or 0
    safety_messages: list[str] = []
    needs_review = False
    is_conflict = bool(raw_week and raw_week.get("conflict")
                       and (raw_week.get("variant_a") or raw_week.get("variant_b")))
    if is_conflict:
        # שער הכרעה A/B — לא כותבים week_plan עד שתבחר
        _handle_weekly_conflict(raw_week, analysis, metrics, prev_week_km, dry=dry)
        needs_review = True
    elif raw_week and dry:
        print("🧪 בדיקה — week_plan.json לא נכתב (היה עובר שכבת בטיחות ב-prod).")
    elif raw_week:
        saved, safety_messages, needs_review = save_week_plan(
            raw_week, prev_week_km=prev_week_km,
            macro=metrics.get("macro"), acwr=metrics["load"].get("acwr"))
        if saved:
            n = len(raw_week.get("sessions", []))
            print(f"✅ week_plan.json עודכן — {n} אימונים לשבוע {raw_week.get('week_of','?')}.")
            print("   → זורם אוטומטית ליומן. לגרמין: דורש אישורך (push_week.py).")
        else:
            print("🛑 התוכנית נדחתה בשכבת הבטיחות — week_plan.json לא עודכן:")
            for m in safety_messages:
                print(f"   • {m}")
    else:
        print("⚠️  לא נמצא WEEK_PLAN_JSON תקין — week_plan.json לא עודכן.")

    # התראות/התאמות בטיחות — מוצגות בשער האישור (ונשלחות לטלגרם אם זמין)
    if safety_messages:
        print("\n🛡️ בטיחות:")
        for m in safety_messages:
            print(f"   • {m}")
        if needs_review:
            print("   ⚠️ נדרש אישור מפורש שלך לפני סנכרון (needs_review).")
        try:
            import telegram_notify as _tg
            ack = "\n⚠️ נדרש אישור מפורש לפני סנכרון." if needs_review else ""
            _tg.send_message("🛡️ <b>בטיחות תוכנית שבועית</b>\n" +
                             "\n".join(f"• {m}" for m in safety_messages) + ack)
        except Exception:
            pass

    # ── שליחת דוח שבועי מובנה לטלגרם (סעיפים A–F) ─────────────────────────
    # בקונפליקט — _handle_weekly_conflict כבר שלח הודעת A/B משולבת, לא משכפלים.
    weekly_report = _parse_weekly_report_json(full_response)
    if weekly_report and not is_conflict:
        try:
            _send_weekly_telegram(weekly_report, safety_messages, needs_review, test=dry)
            # חותמת זמן לשער העריכה: weekly_revise.py יחפש תשובות שנשלחו אחרי רגע זה.
            if not dry:
                WEEKLY_STATE_FILE.write_text(json.dumps(
                    {"status": "pending_review", "sent_at": __import__("time").time(),
                     "week_of": current_week_monday()}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
        except Exception as exc:
            print(f"⚠️  שגיאה בשליחת דוח שבועי לטלגרם: {exc}")
    elif not weekly_report and not is_conflict:
        print("⚠️  לא נמצא WEEKLY_REPORT_JSON — דוח טלגרם לא נשלח.")

    load_metrics = metrics["load"]
    compliance_to_store = {k: v for k, v in compliance.items() if k != "available"}
    macro = metrics["macro"]
    thr = analysis.get("threshold_progress", {})
    history_entry = {
        "week_of": current_week_monday(),
        "generated_at": timestamp,
        "headline": analysis["priority"]["headline"],
        "threshold_snapshot": {
            "current_vdot": thr.get("current_vdot"),
            "required_vdot": thr.get("required_vdot"),
            "vdot_gap": thr.get("vdot_gap"),
            "threshold_pace": thr.get("threshold_pace"),
        },
        "macro": {
            "week_num": macro.get("week_num"),
            "phase": macro.get("phase"),
            "deload": macro.get("deload"),
            "gate": macro.get("gate"),
        },
        "metrics": {
            "ctl": load_metrics["ctl"], "atl": load_metrics["atl"],
            "tsb": load_metrics["tsb"], "acwr": load_metrics["acwr"],
            "ramp_rate_4w": load_metrics["ramp_rate_4w"],
        },
        "fitness_4week": metrics["fitness_4week"],
        "zones_28d": {"easy_pct": metrics["zones"].get("easy_pct"),
                      "hard_pct": metrics["zones"].get("hard_pct")},
        "week_actual": {
            "run_count": metrics["last_week"]["count"],
            "total_km": metrics["last_week"]["total_km"],
            "total_load": metrics["last_week"].get("total_load", 0),
        },
        "red_flags": metrics["red_flags"],
        "recommended_plan": plan_json,
        "compliance": compliance_to_store,
        # רצף אימוני הכוח של השבוע (A/B/C לפי תאריך) — כדי שתכנון השבוע הבא
        # ימשיך מהאימון האחרון ולא יחזור על אותו אימון (Push/Pull) ברצף חוצה-שבועות.
        "strength_sequence": [s.get("key") for s in
                              sorted(((raw_week or {}).get("sessions") or []),
                                     key=lambda x: x.get("date", ""))
                              if s.get("type") == "strength" and s.get("key")],
    }
    if dry:
        print("🧪 בדיקה — היסטוריה לא נכתבה.")
    else:
        save_history_entry(history_entry)
        print(f"\nהיסטוריה עודכנה: {HISTORY_FILE}\nהדוח נשמר: {REPORT_FILE}")

    print("\nרוצה לשוחח עם המאמן? (Enter = כן | q = לא)")
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "q"
    if answer not in CHAT_EXIT_PHRASES:
        chat_mode(client, knowledge_base, full_response)


def _parse_postworkout_json(report_text: str) -> dict:
    """Extract the post-workout JSON, tolerant of how the model wrapped it.

    Uses the shared extract_llm_json hardening: the model (Sonnet at effort=medium)
    doesn't always emit the literal ---POSTWORKOUT_JSON---/---END_POSTWORKOUT---
    markers — it may wrap the object in a ```json fence or print a bare {...}.
    Try each strategy in order, then normalize field-name aliases so the Telegram
    sender finds the keys it expects. A brittle parser here silently drops the
    notification AND marks the run analyzed, so the message is lost for good.
    """
    return extract_llm_json(
        report_text, "---POSTWORKOUT_JSON---", "---END_POSTWORKOUT---",
        aliases={"category": ("category", "type", "workout_type", "קטגוריה"),
                 "planned": ("planned", "planned_workout"),
                 "actual": ("actual", "actual_workout", "performed"),
                 "improve": ("improve", "improvements", "improve_points"),
                 "keep": ("keep", "maintain", "strength"),
                 "red_flags": ("red_flags", "flags", "warnings"),
                 "next": ("next", "next_workout", "upcoming")})


def _send_postworkout_telegram(pw: dict) -> int | None:
    """Send the post-workout analysis to Telegram in the agreed skeleton format."""
    try:
        import telegram_notify as tg
    except ImportError:
        print("⚠️  telegram_notify לא זמין — מדלג על Telegram.")
        return None

    # חובה לברוח מתווי HTML (& < >) בכל תוכן מה-LLM — אחרת תו בודד כמו "דופק <130"
    # שובר את מצב ה-HTML של טלגרם → 400 Bad Request → ההודעה לא נשלחת (תקלה חוזרת 22.06).
    import html as _html
    def _e(s): return _html.escape(str(s))
    today = date.today().strftime("%d/%m/%Y")
    category = _e(pw.get("category", "אימון"))
    planned = _e(pw.get("planned", "—"))
    actual = _e(pw.get("actual", "—"))
    improve = [_e(x) for x in (pw.get("improve") or [])]
    keep = _e(pw.get("keep", "—"))
    red_flags = [_e(f) for f in (pw.get("red_flags") or []) if f and str(f).strip()]
    nxt = _e(pw.get("next", "—"))

    lines = [
        f"🏃 <b>ניתוח אימון — {today}</b>",
        "",
        f"📍 <b>{category}</b>",
        f"מתוכנן: {planned}",
        f"בפועל:  {actual}",
        "",
        "📈 <b>2 דברים לשיפור</b>",
    ]
    for i, imp in enumerate(improve[:2], 1):
        lines.append(f"{i}. {imp}")
    lines += ["", "✅ <b>לשמר</b>", keep]
    if red_flags:
        lines += ["", "⚠️ <b>דגלים אדומים</b>"]
        lines += [f"• {f}" for f in red_flags]
    else:
        lines += ["", "🚩 <b>דגלים אדומים:</b> אין ✅"]
    lines += ["", f"📅 <b>בהמשך / מחר</b>", nxt]

    message_id = tg.send_message("\n".join(lines))
    if message_id:
        print(f"✅ Telegram נשלח (message_id={message_id})")
    else:
        print("⚠️  Telegram לא נשלח (אין credentials או שגיאה)")
    return message_id


ANALYZED_RUNS_FILE = BASE_DIR / "analyzed_runs.json"


def _load_analyzed_runs() -> set:
    """קבוצת activity_id של ריצות שכבר נותחו (dedup חוצה-זמן — לא תלוי שעה)."""
    if not ANALYZED_RUNS_FILE.exists():
        return set()
    try:
        data = json.loads(ANALYZED_RUNS_FILE.read_text(encoding="utf-8"))
        return set(str(x) for x in data.get("analyzed", []))
    except Exception:
        return set()


MAX_POSTWORKOUT_ATTEMPTS = 3  # תקרת ניסיונות חוזרים לפני ויתור (חוסם בזבוז API אינסופי)


def _load_pw_pending() -> dict:
    """מונה כשלונות פתוחים per activity_id (ניסיון חוזר עד התקרה)."""
    if not ANALYZED_RUNS_FILE.exists():
        return {}
    try:
        data = json.loads(ANALYZED_RUNS_FILE.read_text(encoding="utf-8"))
        return {str(k): int(v) for k, v in (data.get("pending") or {}).items()}
    except Exception:
        return {}


def _write_analyzed_payload(analyzed: set, pending: dict) -> None:
    payload = {"version": 1, "analyzed": sorted(analyzed)[-200:], "pending": pending}
    ANALYZED_RUNS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")


def _mark_run_analyzed(activity_id) -> None:
    """מסמן ריצה כנותחה (אחרי שליחה מוצלחת) — ומנקה את מונה הכשלונות שלה."""
    analyzed = _load_analyzed_runs()
    analyzed.add(str(activity_id))
    pending = _load_pw_pending()
    pending.pop(str(activity_id), None)
    _write_analyzed_payload(analyzed, pending)


def _postworkout_fail(activity_id, reason: str) -> None:
    """כשל ניתוח/שליחה: מגדיל מונה ומנסה שוב בריצה הבאה. אחרי MAX ניסיונות —
    מוותר ומסמן כנותח כדי לא לבזבז API לנצח. כך כשל חולף נרפא לבד, וכשל מתמשך נחסם."""
    pending = _load_pw_pending()
    n = pending.get(str(activity_id), 0) + 1
    if n >= MAX_POSTWORKOUT_ATTEMPTS:
        print(f"⚠️  {reason} — ניסיון {n}/{MAX_POSTWORKOUT_ATTEMPTS}: מוותר ומסמן כנותח.")
        _mark_run_analyzed(activity_id)  # מנקה pending בעצמו
    else:
        pending[str(activity_id)] = n
        _write_analyzed_payload(_load_analyzed_runs(), pending)
        print(f"⚠️  {reason} — ניסיון {n}/{MAX_POSTWORKOUT_ATTEMPTS}: לא מסמן, ינסה שוב בריצה הבאה.")


def latest_unanalyzed_run_today(activities: list, analyzed: set) -> dict | None:
    """הריצה האחרונה של היום שעדיין לא נותחה (לפי activity_id). None אם אין."""
    today = date.today().isoformat()
    todays_runs = [a for a in activities
                   if a.get("date") == today
                   and a.get("activity_type") in RUN_TYPES
                   and str(a.get("activity_id")) not in analyzed]
    if not todays_runs:
        return None
    return sorted(todays_runs, key=lambda a: a.get("start_time", ""))[-1]


REVISE_SYSTEM = """אתה עוזר שמעדכן תוכנית אימונים שבועית לפי בקשת שינוי של המתאמן (הגיא) בשפה חופשית.
מקבל: התוכנית הנוכחית (JSON) + בקשת שינוי בעברית. מוציא: תוכנית מעודכנת **באותה סכמה בדיוק**.

## חוקים (קריטי)
- שנה **רק** מה שהתבקש במפורש. כל שאר הסשנים נשארים **זהים** (date, name, est_km, key).
- כוח: key A=משיכה/Pull · B=דחיפה/Push · C=רגליים/Legs. נסה לשמור A×2, B×2, C×1.
- "בלי ריצה ביום X" / "X בלי ריצה" → הסר את סשן ה**ריצה** של אותו יום (השאר סשן כוח אם קיים).
- "X בלי התאוששות" → הסר את ריצת ההתאוששות של אותו יום.
- "יום X N ק\"מ" / "X = N" → עדכן est_km של ריצת אותו יום ל-N, ועדכן name בהתאם, ו-steps[0].seconds ≈ N*390.
- שבת = ריצת הנפח. long ≤ {long_cap} ק\"מ.
- **אל תמציא** ימים/אימונים שלא התבקשו. אל תשנה את week_of/macro_week/phase.
- כל סשן ריצה: {{date, type:"run", subtype:"easy|quality|long", name, est_km, steps:[{{"kind":"interval","seconds":N}}]}}.
- כל סשן כוח: {{date, type:"strength", key:"A|B|C"}}.

החזר **רק** את בלוק ה-JSON בין המרקרים, בלי טקסט נוסף:
---WEEK_PLAN_JSON---
{{ "week_of": "...", "macro_week": N, "phase": "...", "sessions": [...] }}
---END_WEEK_PLAN---"""
# format בהגדרה: מזריק את קבועי-המתאמן וגם מקרוס {{}}→{} בדוגמת ה-JSON —
# קודם התבנית נשלחה raw וה-LLM ראה סוגריים כפולים מילוליים (באג רדום שתוקן כאן).
REVISE_SYSTEM = REVISE_SYSTEM.format(**ATHLETE_PROMPT_VARS)


def run_revise(reply_text: str, dry: bool = False) -> tuple[bool, list]:
    """מעדכן את week_plan.json לפי בקשת שינוי חופשית (מטלגרם). עובר שכבת בטיחות.
    מחזיר (saved, messages). מאפס approved (דורש אישור מחדש)."""
    wp = BASE_DIR / "week_plan.json"
    if not wp.exists():
        print("⚠️  אין week_plan.json לעדכן.")
        return False, []
    plan = json.loads(wp.read_text(encoding="utf-8"))
    user_prompt = (f"## התוכנית הנוכחית\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
                   f"## בקשת השינוי של הגיא\n{reply_text}\n\n"
                   f"החזר את התוכנית המעודכנת בבלוק WEEK_PLAN_JSON (רק מה שהתבקש).")
    client = anthropic.Anthropic()
    print(f"🔧 מעדכן תוכנית לפי: {reply_text!r}")
    full = _stream_report(client, REVISE_SYSTEM, user_prompt,
                          max_tokens=8000, effort="medium", model=MODEL_POSTWORKOUT)
    raw = extract_week_plan(full)
    if not raw or not raw.get("sessions"):
        print("⚠️  פרסור התוכנית המעודכנת נכשל — לא שונה דבר.")
        return False, []
    raw["week_of"] = plan.get("week_of")  # לעולם לא משנים את השבוע
    if dry:
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return True, []
    macro = get_macro_week()
    saved, messages, _ = save_week_plan(
        raw, macro=macro if macro.get("status") == "active" else None)
    return saved, messages


def run_postworkout(client, knowledge_base: str, metrics: dict, data: dict) -> None:
    """
    ניתוח אחרי אימון — EVENT-DRIVEN. רץ פעמים רבות ביום; מנתח **רק** אם יש
    ריצה חדשה של היום שעדיין לא נותחה (dedup לפי activity_id). כך לא משנה
    מתי רצת — תמיד נתפוס, אף פעם לא פעמיים, ו-Sonnet נקרא רק כשבאמת צריך.
    """
    analyzed = _load_analyzed_runs()
    workout = latest_unanalyzed_run_today(data.get("activities", []), analyzed)
    if not workout:
        print("אין ריצה חדשה לנתח היום (או שכבר נותחה) — מדלג, ללא קריאת API.")
        return

    system_prompt = POSTWORKOUT_SYSTEM.format(knowledge_base=knowledge_base,
                                              **ATHLETE_PROMPT_VARS)
    user_prompt = build_postworkout_prompt(metrics, workout)
    print(f"🤖 מודל: {MODEL_POSTWORKOUT} (אחרי אימון — אמצע)")
    print(f"מנתח ריצה {workout.get('activity_id')} מ-{workout.get('start_time','?')} (streaming)...\n")
    # max_tokens=16000: ניתוח מפורט (3 חלקים + קדנס/GCT/planned) + חשיבה אדפטיבית
    # + בלוק POSTWORKOUT_JSON בסוף. ב-8192 (22.06) הפלט נחתך באמצע → אין JSON →
    # אין טלגרם. תקרה גבוהה זולה (ריצה אחת/יום) ומונעת truncation לתמיד.
    full = _stream_report(client, system_prompt, user_prompt, max_tokens=16000,
                          effort="medium", model=MODEL_POSTWORKOUT)
    out = BASE_DIR / "postworkout_report.md"
    out.write_text(f"# ניתוח אחרי אימון — {datetime.now():%Y-%m-%d %H:%M}\n\n{full}\n", encoding="utf-8")
    print(f"\n\nנשמר: {out}")

    aid = workout.get("activity_id")
    # פלט ריק = קריאת API נכשלה/נחתכה → ניסיון חוזר (עד התקרה).
    if not full.strip():
        _postworkout_fail(aid, "הניתוח חזר ריק")
        return

    # ── Parse POSTWORKOUT_JSON and send Telegram notification ──────────────
    pw_json = _parse_postworkout_json(full)
    if not pw_json:
        # נחתך/חסר JSON → ניסיון חוזר בריצה הבאה (לא מסמן — אחרת ההודעה אובדת).
        _postworkout_fail(aid, "לא נמצא POSTWORKOUT_JSON (כנראה נחתך)")
        return
    # דריסת שדה next בערך **דטרמיניסטי** מהתוכנית בפועל (ריצה+כוח, היום הקרוב) —
    # ה-LLM נטה להמציא "אימון הבא" מהמאקרו (למשל טמפו שכבר היה). זה מדייק אותו.
    _run_done = bool(workout and workout.get("date") == date.today().isoformat()
                     and workout.get("activity_type") in RUN_TYPES)
    pw_json["next"] = _next_sessions_md(_run_done)
    try:
        msg_id = _send_postworkout_telegram(pw_json)
    except Exception as exc:
        _postworkout_fail(aid, f"שגיאת שליחת Telegram: {exc}")
        return
    # _send_postworkout_telegram מחזיר None בכשל (אין credentials/שגיאת API) ולא זורק —
    # לכן בודקים את ערך ההחזרה, לא רק חריגה. None → ניסיון חוזר, לא מסמן.
    if not msg_id:
        _postworkout_fail(aid, "Telegram לא נשלח (אין credentials/שגיאה)")
        return
    # רק אחרי שליחה מאומתת (message_id חוקי) — מסמן כנותח.
    _mark_run_analyzed(aid)
    print(f"✅ ניתוח נשלח לטלגרם (message_id={msg_id}) וסומן כנותח.")


# ── Interactive Chat Mode ─────────────────────────────────────────────────────

CHAT_EXIT_PHRASES = {"quit", "exit", "q", "יציאה", "סיום", "bye"}

CHAT_SYSTEM = """
אתה מאמן ריצה אישי. יש לך את הדוח השבועי המלא בזיכרון.
ענה בצורה קצרה וישירה — זוהי שיחה, לא דוח.
אם המתאמן מספר על שינוי (עייפות, כאב, שינוי בתוכנית) — עדכן את ההמלצה בהתאם לנתונים.
תמיד ספק תשובה קונקרטית: מה לעשות היום/מחר/השבוע.
"""


def _stream_chat_response(client: "anthropic.Anthropic", messages: list[dict], system: str) -> str:
    """Stream a chat response, return full text."""
    from rich.live import Live
    from rich.markdown import Markdown

    full_text = ""
    with Live("", refresh_per_second=15, vertical_overflow="visible") as live:
        with client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=1024,
            # Cache the coach-persona + knowledge-base prefix across chat turns
            system=[{"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                live.update(Markdown(full_text))
    return full_text


def chat_mode(client: "anthropic.Anthropic", knowledge_base: str, report_text: str) -> None:
    """
    Interactive REPL after weekly report generation.
    Report injected as first assistant message — Claude 'remembers' it.
    Conversation history kept in-memory; prompt-cached system prompt reduces cost.
    """
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        from rich.prompt import Prompt
    except ImportError:
        print("\n[rich לא מותקן — מריץ בלי עיצוב. pip install rich]\n")
        Console = None  # type: ignore

    console = Console() if Console else None

    # System: coach persona + knowledge base (cached prefix)
    system = f"{CHAT_SYSTEM}\n\n## בסיס הידע שלך\n{knowledge_base}"

    # Seed history: report is the first assistant turn
    messages: list[dict] = [
        {"role": "user", "content": "צור את הדוח השבועי שלי."},
        {"role": "assistant", "content": report_text},
    ]

    if console:
        console.print(Panel(
            "[bold cyan]מצב שיחה עם המאמן[/]\n"
            "[dim]שאל שאלות, דווח על שינויים, קבל התאמות לתוכנית.\n"
            "כתוב [bold]quit[/] או [bold]יציאה[/] לסיום.[/]",
            border_style="cyan"
        ))
    else:
        print("\n=== מצב שיחה עם המאמן ===")
        print("(quit / יציאה לסיום)\n")

    while True:
        try:
            if console:
                user_input = Prompt.ask("[bold yellow]אתה[/]").strip()
            else:
                user_input = input("\nאתה: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input or user_input.lower() in CHAT_EXIT_PHRASES:
            break

        messages.append({"role": "user", "content": user_input})

        if console:
            console.print("[bold green]מאמן:[/]")
        else:
            print("\nמאמן:")

        response = _stream_chat_response(client, messages, system)
        messages.append({"role": "assistant", "content": response})

        # Keep history bounded: seed (2) + last 20 turns = 22 messages max
        if len(messages) > 22:
            messages = messages[:2] + messages[-20:]

    if console:
        console.print("[dim]השיחה הסתיימה.[/]")
    else:
        print("\nהשיחה הסתיימה.")


if __name__ == "__main__":
    main()
