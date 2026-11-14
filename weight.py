# -*- coding: utf-8 -*-
"""
weight.py — מעקב משקל (14.11.2026). המטרה של הגיא: ירידה במשקל וחזרה לכושר.

מקור-האמת: השקילות ב-Garmin Connect (משקל חכם, או הזנה ידנית באפליקציה).
fetch_garmin מושך get_weigh_ins לטווח, והמודול הזה מפענח וממזג ל-data.json["weight"]:
    {"YYYY-MM-DD": {"kg": 80.2, "body_fat": 21.5 | None}}

הפענוח סלחני בכוונה: garminconnect לא-רשמית ומבנה התשובה לא אומת מול החשבון של
הגיא (הפרויקט היה קפוא כשנכתב). גרמין מחזיר משקל בגרמים; ערך מעל 500 = גרמים.
"""
from __future__ import annotations

from datetime import datetime, timezone

KG_MIN, KG_MAX = 30.0, 250.0     # מחוץ לטווח = לא משקל גוף, מדלגים


def _to_kg(v) -> float | None:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v > 500:                  # גרמים
        v /= 1000.0
    return round(v, 1) if KG_MIN <= v <= KG_MAX else None


def _entry_date(e: dict, fallback: str = "") -> str:
    d = e.get("calendarDate") or e.get("summaryDate") or fallback
    if d:
        return str(d)[:10]
    ts = e.get("date") or e.get("timestampGMT") or e.get("samplePk")
    if isinstance(ts, (int, float)) and ts > 10**11:      # epoch ms
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
    return ""


def parse_weigh_ins(resp) -> dict:
    """תשובת get_weigh_ins / get_body_composition → {date: {"kg", "body_fat"}}.
    מכיר את שלושת המבנים הידועים: dailyWeightSummaries (latestWeight / allWeightMetrics),
    dateWeightList, ורשימה שטוחה. שקילה אחרונה ביום גוברת."""
    out: dict = {}
    if not resp:
        return out

    def put(e: dict, fallback_date: str = "") -> None:
        if not isinstance(e, dict):
            return
        kg = _to_kg(e.get("weight"))
        d = _entry_date(e, fallback_date)
        if kg is None or not d:
            return
        fat = e.get("bodyFat")
        out[d] = {"kg": kg,
                  "body_fat": round(float(fat), 1) if isinstance(fat, (int, float)) and fat > 0 else None}

    if isinstance(resp, list):
        for e in resp:
            put(e)
        return out
    for day in resp.get("dailyWeightSummaries") or []:
        d = str(day.get("summaryDate") or "")[:10]
        latest = day.get("latestWeight")
        if isinstance(latest, dict):
            put(latest, d)
        else:
            for e in day.get("allWeightMetrics") or []:
                put(e, d)
    for e in resp.get("dateWeightList") or []:
        put(e)
    return out


def merge(existing: dict | None, new: dict | None) -> dict:
    """מצטבר: שקילות ישנות נשמרות, יום שנמשך מחדש מתעדכן. ממוין לפי תאריך."""
    merged = dict(existing or {})
    merged.update(new or {})
    return dict(sorted(merged.items()))


def summary(weights: dict, since: str = "") -> dict:
    """סיכום לתצוגה ולפרומט: אחרון, ראשון מאז since, שינוי, ממוצע 7 שקילות אחרונות."""
    items = [(d, w["kg"]) for d, w in sorted((weights or {}).items()) if d >= since]
    if not items:
        return {"available": False}
    last7 = [kg for _, kg in items[-7:]]
    return {"available": True, "count": len(items),
            "first_date": items[0][0], "first_kg": items[0][1],
            "last_date": items[-1][0], "last_kg": items[-1][1],
            "change_kg": round(items[-1][1] - items[0][1], 1),
            "avg7_kg": round(sum(last7) / len(last7), 1)}
