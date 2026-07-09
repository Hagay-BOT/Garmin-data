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
