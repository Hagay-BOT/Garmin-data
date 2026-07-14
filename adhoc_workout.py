# -*- coding: utf-8 -*-
"""
adhoc_workout.py — העלאת אימון-כוח חד-פעמי (משבצת-זמן, בלי סטים) לגרמין + הודעת טלגרם.

כלי-טיול/אד-הוק: כשהמבנה הרגיל (PPL) לא רלוונטי — למשל פול-באדי בחו"ל.
קלט דרך env (מה-workflow):
  ADHOC_NAME    — שם האימון בשעון
  ADHOC_DATES   — תאריכים מופרדים בפסיק (YYYY-MM-DD,...)
  ADHOC_MINUTES — משך בדקות
  TELEGRAM_FILE — קובץ טקסט לשליחה בטלגרם (אופציונלי; HTML מותר)
"""
import os
from pathlib import Path

from garmin_client import login

STRENGTH_SPORT = {"sportTypeId": 5, "sportTypeKey": "strength_training", "displayOrder": 5}


def build_timeslot(name: str, minutes: int) -> dict:
    secs = float(minutes * 60)
    return {
        "workoutName": name,
        "description": "אימון אד-הוק (ראה פירוט בטלגרם).",
        "sportType": STRENGTH_SPORT,
        "estimatedDurationInSecs": int(secs),
        "workoutSegments": [{
            "segmentOrder": 1, "sportType": STRENGTH_SPORT,
            "workoutSteps": [{
                "type": "ExecutableStepDTO", "stepOrder": 1,
                "stepType": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
                "endCondition": {"conditionTypeId": 2, "conditionTypeKey": "time",
                                 "displayOrder": 2, "displayable": True},
                "endConditionValue": secs,
                "targetType": {"workoutTargetTypeId": 1,
                               "workoutTargetTypeKey": "no.target", "displayOrder": 1},
            }],
        }],
    }


def main() -> None:
    name = os.environ["ADHOC_NAME"]
    dates = [d.strip() for d in os.environ["ADHOC_DATES"].split(",") if d.strip()]
    minutes = int(os.environ.get("ADHOC_MINUTES", "60"))

    client = login()
    for d in dates:
        res = client.upload_workout(build_timeslot(name, minutes))
        wid = res.get("workoutId") or res.get("workoutid")
        if not wid:
            raise ValueError(f"תגובת העלאה ללא workoutId: {res}")
        client.schedule_workout(wid, d)
        print(f"✅ {d} · {name} · id {wid}")

    tg_file = os.environ.get("TELEGRAM_FILE", "")
    if tg_file and Path(tg_file).exists():
        import telegram_notify as tg
        mid = tg.send_message(Path(tg_file).read_text(encoding="utf-8"))
        print(f"📱 רשימת התרגילים נשלחה לטלגרם (message_id={mid})")


if __name__ == "__main__":
    main()
