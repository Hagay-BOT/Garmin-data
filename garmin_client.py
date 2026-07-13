# -*- coding: utf-8 -*-
"""
garmin_client.py — נקודת-הכניסה היחידה להתחברות גרמין (M9.2).

garminconnect היא ספרייה לא-רשמית — נקודת-הכשל החיצונית הגדולה של הפרויקט.
בידוד ההתחברות כאן = שינוי-API של גרמין מתוקן בקובץ אחד, וכל הנתיבים מקבלים
את אותה הקשחת retry/backoff (עד כה רק fetch_garmin נהנה ממנה; נתיבי ה-push
נפלו על ה-429 הראשון).

שימוש:  from garmin_client import login  →  client = login()
"""
import os
import sys
import time
import logging

logger = logging.getLogger("garmin_client")


def login(attempts: int = 4):
    """התחברות עם retry+backoff (20/40/60ש') — 429/timeout חולפים לא מפילים ריצה.
    חסרים credentials או כשל מתמשך → SystemExit רועש (fail-fast, לא דגימה שקטה)."""
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("שגיאה: GARMIN_EMAIL / GARMIN_PASSWORD לא מוגדרים.", file=sys.stderr)
        sys.exit(1)

    from garminconnect import Garmin
    for attempt in range(1, attempts + 1):
        try:
            client = Garmin(email, password)
            client.login()
            print("✅ התחברות לגרמין הצליחה")
            return client
        except Exception as e:  # noqa: BLE001 — סוג השגיאה משתנה (429/timeout/JWT)
            if attempt >= attempts:
                print(f"ERROR: Garmin login failed after {attempt} attempts — {e}",
                      file=sys.stderr)
                sys.exit(1)
            wait = attempt * 20
            logger.warning("Garmin login attempt %d failed (%s) — retrying in %ds",
                           attempt, str(e)[:90], wait)
            time.sleep(wait)


# ── M4.1 · reconcile: האמת היא לוח-השנה של גרמין, לא קובץ מקומי ──────────────

OUR_MARKERS = ("🏃", "💪", "🦵", "🚶")  # קונבנציית-השמות שלנו — מזהה את האימונים שאנחנו יצרנו


def scheduled_workouts(client, start_iso: str, end_iso: str) -> list[dict]:
    """כל האימונים המתוזמנים בלוח גרמין בטווח התאריכים (כולל) — האמת מהשעון.
    מחזיר [{'date','name','workout_id','schedule_id','ours'}]. עמיד לווריאציות
    בשמות-השדות של ה-API (calendarItems/title/workoutId וכו')."""
    import datetime
    start = datetime.date.fromisoformat(start_iso)
    end = datetime.date.fromisoformat(end_iso)
    months, cur = [], start.replace(day=1)
    while cur <= end:
        months.append((cur.year, cur.month))
        cur = (cur.replace(day=28) + datetime.timedelta(days=5)).replace(day=1)
    items = []
    for y, m in months:
        cal = client.get_scheduled_workouts(y, m) or {}
        raw = (cal.get("calendarItems") or cal.get("items")
               or (cal if isinstance(cal, list) else []))
        for it in raw:
            if (it.get("itemType") or "workout") != "workout":
                continue
            d = it.get("date") or it.get("scheduleDate") or ""
            if not (start_iso <= d[:10] <= end_iso):
                continue
            name = it.get("title") or it.get("workoutName") or ""
            items.append({
                "date": d[:10], "name": name,
                "workout_id": it.get("workoutId") or it.get("workoutUuid"),
                "schedule_id": it.get("id") or it.get("scheduleId"),
                "ours": name.startswith(OUR_MARKERS),
            })
    return items
