"""
מייצר קובץ ICS (יומן אוניברסלי) מ-week_plan.json — ללא הרשאות Google.
המשתמש נרשם פעם אחת לכתובת ה-ICS ב-Google Calendar, והיומן מתרענן לבד.

כללי תזמון:
  ריצה קצרה → 07:00 (מסתיימת לפני 8:40, זמן למקלחת)
  ריצה ארוכה → 08:00 (גמיש, אין עבודה)
  כוח        → 18:00 (ערב)
לריצות מתווספת המלצת מזג אוויר (חוץ/חדר כושר) לפי weather.py.

שימוש:
  python calendar_sync.py            → כותב calendar/training.ics
  python calendar_sync.py --print    → מדפיס לבדיקה
"""
import sys
import json
import calendar
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).parent
PLAN_FILE = BASE / "week_plan.json"
OUT_FILE = BASE / "calendar" / "training.ics"


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """התאריך האחרון בחודש שהוא היום-בשבוע הנתון (Mon=0..Sun=6)."""
    d = date(year, month, calendar.monthrange(year, month)[1])
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def israel_utc_offset(d: date) -> int:
    """+3 בשעון קיץ (IDT), +2 בשעון חורף (IST). בלי תלות ב-tzdata.
    שעון קיץ: מיום שישי שלפני יום ראשון האחרון במרץ עד יום ראשון האחרון באוקטובר."""
    dst_start = _last_weekday(d.year, 3, 6) - timedelta(days=2)   # שישי לפני
    dst_end = _last_weekday(d.year, 10, 6)
    return 3 if dst_start <= d < dst_end else 2

STRENGTH = {
    "A": "💪 כוח A — Push (חזה/יד אחורית/כתפיים)",
    "B": "💪 כוח B — Pull (גב/יד קדמית)",
    "C": "🦵 כוח C — Legs (רגליים)",
}

# (שעת התחלה, משך בדקות) לכל סוג
TIMING = {
    "run_short": ("07:00", 45),
    "run_long":  ("08:00", 75),
    "strength":  ("18:00", 60),
}


def _utc(local_dt: datetime) -> str:
    """המרת זמן מקומי (ישראל) ל-UTC בפורמט ICS, לפי היסט שעון ישראל."""
    utc_dt = local_dt - timedelta(hours=israel_utc_offset(local_dt.date()))
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


# תחזית מהימנה רק עד 3 ימים קדימה — מעבר לכך מחכים לרענון הקרוב
FORECAST_HORIZON_DAYS = 3


def _weather_note(date_str: str, hour: str, is_long: bool) -> str:
    days_out = (date.fromisoformat(date_str) - date.today()).days
    if days_out < 0:
        return ""                      # ריצה שעברה
    if days_out > FORECAST_HORIZON_DAYS:
        return "\\n\\n🌦️ התחזית תתעדכן ~3 ימים לפני הריצה."
    try:
        import weather
        rec = weather.recommend(f"{date_str}T{hour}", is_long)
        if rec and "error" not in rec:
            return f"\\n\\n🌦️ {rec['verdict']} — {rec['message']}"
    except Exception:
        pass
    return ""


def build_events() -> list[dict]:
    plan = json.loads(PLAN_FILE.read_text(encoding="utf-8"))
    events = []
    for s in plan.get("sessions", []):
        d = s["date"]
        if s["type"] == "run":
            is_long = s.get("subtype") == "long"
            hour, dur = TIMING["run_long" if is_long else "run_short"]
            summary = s.get("name", "🏃 ריצה")
            desc = (s.get("desc", "") + _weather_note(d, hour, is_long)).strip()
            uid = f"{d}-run-{s.get('subtype','x')}"
        else:
            hour, dur = TIMING["strength"]
            key = s.get("key", "?")
            summary = STRENGTH.get(key, f"כוח {key}")
            desc = {"A": "Push: חזה, יד אחורית, כתפיים.",
                    "B": "Pull: גב, יד קדמית.",
                    "C": "רגליים: סקוואט, hip thrust, calf raises."}.get(key, "")
            uid = f"{d}-strength-{key}"
        h, m = map(int, hour.split(":"))
        start = datetime.fromisoformat(d).replace(hour=h, minute=m)
        end = start + timedelta(minutes=dur)
        events.append({"uid": uid, "summary": summary, "desc": desc,
                       "start": start, "end": end})
    return events


def to_ics(events: list[dict]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//garmin-coach//training//HE", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", "X-WR-CALNAME:אימוני ריצה וכוח",
        "X-WR-TIMEZONE:Asia/Jerusalem", "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
    ]
    for e in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['uid']}@garmin-coach",
            f"DTSTAMP:{now}",
            f"DTSTART:{_utc(e['start'])}",
            f"DTEND:{_utc(e['end'])}",
            f"SUMMARY:{e['summary']}",
            f"DESCRIPTION:{e['desc']}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    events = build_events()
    ics = to_ics(events)
    if "--print" in sys.argv:
        print(ics)
        return
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(ics, encoding="utf-8")
    print(f"נכתב {OUT_FILE} · {len(events)} אירועים")


if __name__ == "__main__":
    main()
