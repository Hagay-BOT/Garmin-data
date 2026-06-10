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


BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data.json"
KB_DIR = BASE_DIR / "knowledge_base"
REPORT_FILE = BASE_DIR / "coach_report.md"


# ── Load data ────────────────────────────────────────────────────────────────

def load_data() -> dict:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


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
    start = date(2024, 1, 1)
    day = start
    days_walked = 0

    while day <= reference_date:
        ds = day.isoformat()
        load = daily_load.get(ds, 0.0)
        ctl = ctl + (load - ctl) * k42
        atl = atl + (load - atl) * k7
        days_walked += 1

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


# ── Zone Distribution ────────────────────────────────────────────────────────

def compute_zone_distribution(activities: list, days: int = 28) -> dict:
    """
    Compute HR zone distribution (% of time) across the last N days of runs.
    Only uses activities with actual hr_zones_sec data.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    runs = [
        a for a in activities
        if a.get("activity_type") == "running"
        and a.get("date", "") >= cutoff
        and sum(a.get("hr_zones_sec") or [0]) > 0
    ]

    totals = [0, 0, 0, 0, 0]
    for run in runs:
        zones = run.get("hr_zones_sec") or [0, 0, 0, 0, 0]
        for i in range(5):
            totals[i] += zones[i]

    total_sec = sum(totals)
    if total_sec == 0:
        return {"available": False, "runs_analyzed": 0}

    pcts = [round(t / total_sec * 100, 1) for t in totals]
    easy_pct = pcts[0] + pcts[1]   # Z1 + Z2
    hard_pct = pcts[3] + pcts[4]   # Z4 + Z5
    z3_pct = pcts[2]

    return {
        "available": True,
        "runs_analyzed": len(runs),
        "z1_pct": pcts[0],
        "z2_pct": pcts[1],
        "z3_pct": pcts[2],
        "z4_pct": pcts[3],
        "z5_pct": pcts[4],
        "easy_pct": round(easy_pct, 1),
        "hard_pct": round(hard_pct, 1),
        "polarization_gap": round(easy_pct - 80, 1),  # deviation from 80% easy target
    }


# ── Last Week Summary ────────────────────────────────────────────────────────

def last_n_days_runs(activities: list, n: int = 7) -> list:
    cutoff = (date.today() - timedelta(days=n)).isoformat()
    runs = [
        a for a in activities
        if a.get("activity_type") == "running"
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
            if a.get("activity_type") == "running"
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


# ── Knowledge Base ───────────────────────────────────────────────────────────

def load_knowledge_base() -> str:
    kb_files = [
        "user_profile.md",
        "load_management.md",
        "polarized_training.md",
        "running_economy.md",
        "recovery_protocols.md",
        "periodization.md",
    ]
    parts = []
    for fname in kb_files:
        path = KB_DIR / fname
        if path.exists():
            content = path.read_text(encoding="utf-8")
            parts.append(f"## {fname}\n\n{content}")
    return "\n\n---\n\n".join(parts)


# ── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """
אתה מאמן ריצה מוסמך — ישיר, מקצועי, ומבוסס על מדע. אתה מדבר בגוף שני לספורטאי.
הדוח שלך נכתב בעברית. אתה אוסר על עצמך "מתמטיקה וירטואלית" — אם נתון לא קיים בנתונים, כתוב "נתון לא זמין".

## בסיס הידע שלך
{knowledge_base}

## כללי דוח
1. אל תחזור על הנתונים הגולמיים — תפרש אותם.
2. כל המלצה על קצב חייבת להתבסס על נתוני דופק מהנתונים, לא על ניחוש.
3. אם ACWR > 1.5 — הזהר ברמה גבוהה לפני הכל.
4. אם Body Battery < 50 או Sleep Score < 60 — אסור להמליץ על אימון קשה.
5. כתוב בצורה ישירה: "עשה X", לא "אולי כדאי לשקול X".
6. כל תוכנית שבוע חייבת לכלול ימים, קצב, מרחק, zone.
"""


# ── User Prompt ──────────────────────────────────────────────────────────────

def build_user_prompt(metrics: dict) -> str:
    return f"""
## נתוני האתלט — {date.today().isoformat()}

### עומס אימונים (CTL/ATL)
- CTL (כושר כרוני, 42 יום): {metrics['load']['ctl']}
- ATL (עייפות חריפה, 7 יום): {metrics['load']['atl']}
- TSB (מאזן): {metrics['load']['tsb']}
- ACWR (יחס עומס): {metrics['load']['acwr'] or 'לא ניתן לחשב (CTL=0)'}
- קצב עלייה ב-4 שבועות: {metrics['load']['ramp_rate_4w']}

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

---

כתוב דוח אימונים מלא בעברית עם הסעיפים הבאים:

## 1. מצב נוכחי — עייפות / ערנות / כושר
ניתוח קצר (3-5 משפטים) על המצב הנוכחי.

## 2. ניתוח שבוע שעבר
פירוט לכל אימון: מה היה טוב, מה לשפר. כולל ניתוח zones, קצב דופק.

## 3. תוכנית שבוע הבא
לכל יום: ריצה / מנוחה / כוח. לריצות: zone, מרחק, קצב יעד בדקות:שניות לק"מ.

## 4. אזהרות וסיכונים
ACWR, ramp rate, דריפט, כל דגל אדום רלוונטי.
"""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("שגיאה: ANTHROPIC_API_KEY לא מוגדר.")
        print("הגדר את המשתנה לפני הרצה:")
        print("  Windows:  $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
        print("  Linux/Mac: export ANTHROPIC_API_KEY='sk-ant-...'")
        print("בסביבת GitHub Actions: הוסף כ-Secret בשם ANTHROPIC_API_KEY")
        sys.exit(1)

    print("טוען נתוני גרמין...")
    data = load_data()

    activities = data.get("activities", [])
    daily = data.get("daily", {})
    global_max_hr = data.get("global_max_hr") or 201.0

    print("מחשב מדדי עומס...")
    daily_load = build_daily_load(activities)
    load_metrics = compute_ctl_atl(daily_load, date.today())
    zones = compute_zone_distribution(activities, days=28)
    last_week_runs = last_n_days_runs(activities, n=7)
    last_week = summarize_runs(last_week_runs)
    readiness = get_readiness(daily)
    prs = compute_prs(activities)

    metrics = {
        "load": load_metrics,
        "zones": zones,
        "last_week": last_week,
        "readiness": readiness,
        "prs": prs,
        "global_max_hr": global_max_hr,
    }

    print(f"CTL={load_metrics['ctl']}  ATL={load_metrics['atl']}  ACWR={load_metrics['acwr']}")

    print("טוען בסיס ידע...")
    knowledge_base = load_knowledge_base()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=knowledge_base)
    user_prompt = build_user_prompt(metrics)

    print("קורא ל-Claude Opus (streaming)...")
    client = anthropic.Anthropic()

    full_response = ""
    with client.messages.stream(
        model="claude-opus-4-8",
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_response += text

    print("\n\nשומר דוח...")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_content = f"# דוח מאמן — {timestamp}\n\n{full_response}\n"
    REPORT_FILE.write_text(report_content, encoding="utf-8")

    print(f"הדוח נשמר: {REPORT_FILE}")


if __name__ == "__main__":
    main()
