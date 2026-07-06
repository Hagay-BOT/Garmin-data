# -*- coding: utf-8 -*-
"""
Health report (M1.3) — dead-man's switch for a project that must run unattended.

Checks every subsystem's freshness/state deterministically (no LLM) and sends a
weekly one-message summary to Telegram. Silent failures become visible:
  - data.json staleness (fetch pipeline dead? cron disabled? secrets expired?)
  - postworkout: last analyzed run vs last run in data; open retry counters
  - weekly plan: week_plan.json covers the current week? approved?
  - journal capture: last note timestamp
  - GitHub 60-day cron-disable risk: days since last commit

Also usable as a heartbeat: the workflow that runs this commits a timestamp file,
which itself resets GitHub's 60-day scheduled-workflow disable timer.
"""
import json
import datetime
import subprocess
from pathlib import Path

import telegram_notify as tg

BASE = Path(__file__).parent
NOW = datetime.datetime.now(datetime.timezone.utc)
TODAY = datetime.date.today()


def _age_days(path: Path) -> float | None:
    """Days since file's last git commit (repo truth, not fs mtime)."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", path.name],
            capture_output=True, text=True, cwd=BASE, timeout=30)
        ts = int(out.stdout.strip())
        return round((NOW.timestamp() - ts) / 86400, 1)
    except Exception:
        return None


def _load(name: str) -> dict:
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_report() -> tuple[str, bool]:
    """Returns (message, all_ok)."""
    lines, ok = [], True

    def item(good: bool, text: str, warn_only: bool = False):
        nonlocal ok
        icon = "✅" if good else ("🟡" if warn_only else "🔴")
        if not good and not warn_only:
            ok = False
        lines.append(f"{icon} {text}")

    # 1. Data freshness — updates 3×/day; >1.5d stale = pipeline problem
    age = _age_days(BASE / "data.json")
    item(age is not None and age <= 1.5,
         f"נתוני גרמין: עודכנו לפני {age} ימים" if age is not None else "נתוני גרמין: לא ניתן לקבוע")

    # 2. Postworkout: any run in data newer than last analyzed?
    data = _load("data.json")
    analyzed = set(str(x) for x in _load("analyzed_runs.json").get("analyzed", []))
    pending = _load("analyzed_runs.json").get("pending", {})
    run_types = {"running", "treadmill_running", "trail_running"}
    cutoff = (TODAY - datetime.timedelta(days=2)).isoformat()
    recent_unanalyzed = [a for a in data.get("activities", [])
                         if a.get("activity_type") in run_types
                         and a.get("date", "") >= cutoff
                         and str(a.get("activity_id")) not in analyzed]
    item(not recent_unanalyzed,
         "ניתוח אחרי-אימון: אין ריצות שלא נותחו" if not recent_unanalyzed
         else f"ניתוח אחרי-אימון: {len(recent_unanalyzed)} ריצות אחרונות ללא ניתוח!")
    if pending:
        item(False, f"ניסיונות-ניתוח פתוחים: {pending}", warn_only=True)

    # 3. Weekly plan covers current week (Sunday anchor)?
    plan = _load("week_plan.json")
    week_of = plan.get("week_of", "")
    sunday = (TODAY - datetime.timedelta(days=(TODAY.weekday() + 1) % 7)).isoformat()
    item(week_of == sunday,
         f"תוכנית שבועית: מכסה את השבוע ({week_of})" if week_of == sunday
         else f"תוכנית שבועית: ישנה! (week_of={week_of}, צריך {sunday})")
    item(bool(plan.get("approved")), f"אישור תוכנית: {'מאושרת' if plan.get('approved') else 'ממתינה לאישור'}",
         warn_only=True)

    # 4. Journal capture alive (warn-only — ok if user simply wrote nothing)
    notes = _load("journal.json").get("notes", [])
    last_note = notes[-1]["date"] if notes else "—"
    item(True, f"יומן: הערה אחרונה {last_note}")

    # 5. GitHub 60-day scheduled-workflow disable risk
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct"],
                             capture_output=True, text=True, cwd=BASE, timeout=30)
        idle_days = round((NOW.timestamp() - int(out.stdout.strip())) / 86400, 1)
        item(idle_days < 45, f"פעילות ריפו: קומיט אחרון לפני {idle_days} ימים"
             + ("" if idle_days < 45 else " — ⚠️ GitHub מכבה cron אחרי 60!"))
    except Exception:
        item(False, "פעילות ריפו: לא ניתן לקבוע", warn_only=True)

    header = "💚 <b>דוח בריאות שבועי — הכל תקין</b>" if ok else "🚨 <b>דוח בריאות שבועי — נדרשת תשומת לב</b>"
    return header + "\n\n" + "\n".join(lines), ok


def main():
    msg, ok = build_report()
    print(msg.replace("<b>", "").replace("</b>", ""))
    # Heartbeat stamp — committed by the workflow; resets GitHub's 60-day timer.
    (BASE / "heartbeat.txt").write_text(NOW.isoformat(timespec="seconds") + "\n", encoding="utf-8")
    mid = tg.send_message(msg)
    print(f"telegram message_id={mid}" if mid else "⚠️ Telegram לא נשלח")


if __name__ == "__main__":
    main()
