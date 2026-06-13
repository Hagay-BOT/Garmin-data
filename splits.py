"""
חישוב מקטעי מרחק קבועים (ברירת מחדל 100מ') מתוך זרם הנתונים המפורט של גרמין.
משמש גם את fetch_garmin.py (קדימה) וגם את backfill_splits.py (היסטורי).

הרעיון: get_activity_details מחזיר דגימה לכל ~שנייה עם מרחק מצטבר, זמן, דופק.
אנחנו חותכים את הזרם כל 100מ' ומחשבים קצב ודופק ממוצע לכל מקטע — כך
אינטרוולים קצרים (200/300/400מ') מתגלים גם אם ה-Auto Lap בשעון גס יותר.
"""
from typing import Any

# שמות אפשריים לכל מדד (גרמין משתנה מעט בין דגמים/גרסאות)
_DISTANCE_KEYS = ("sumDistance", "sumDistanceInMeters")
_HR_KEYS = ("directHeartRate", "heartRate")
_SPEED_KEYS = ("directSpeed", "directGradeAdjustedSpeed")
_TIME_SEC_KEYS = ("sumMovingDuration", "sumDuration", "sumElapsedDuration", "directElapsedDuration")
_TIMESTAMP_KEYS = ("directTimestamp",)


def _find_index(descriptors: list, candidates: tuple) -> int | None:
    for d in descriptors:
        if d.get("metricsType") in candidates or d.get("key") in candidates:
            idx = d.get("metricsIndex")
            if idx is not None:
                return idx
    return None


def descriptor_types(details: dict) -> list:
    """אבחון: מחזיר את כל סוגי המדדים הזמינים בפעילות."""
    descs = details.get("metricDescriptors", []) or []
    return [d.get("metricsType") or d.get("key") for d in descs]


def compute_segments(details: dict, seg_meters: float = 100.0) -> list[dict]:
    """
    מחזיר רשימת מקטעים, כל אחד:
      {seg, distance_m, pace_sec_per_km, avg_hr, duration_sec}
    אם חסרים נתוני מרחק/זמן — מחזיר רשימה ריקה (fail-safe).
    """
    descs = details.get("metricDescriptors", []) or []
    samples = details.get("activityDetailMetrics", []) or []
    if not descs or not samples:
        return []

    di = _find_index(descs, _DISTANCE_KEYS)
    hi = _find_index(descs, _HR_KEYS)
    si = _find_index(descs, _SPEED_KEYS)
    ti = _find_index(descs, _TIME_SEC_KEYS)
    tsi = _find_index(descs, _TIMESTAMP_KEYS) if ti is None else None
    if di is None or (si is None and ti is None and tsi is None):
        return []

    def _val(vals, idx):
        if idx is None or idx >= len(vals):
            return None
        return vals[idx]

    def _time_of(vals):
        if ti is not None:
            return _val(vals, ti)                 # שניות
        ts = _val(vals, tsi)
        return ts / 1000.0 if ts is not None else None  # ms → שניות

    def _pace_from_speed(spd_sum, spd_n):
        """קצב (שנ'/ק\"מ) מהמהירות הממוצעת — עמיד לעצירות ולרעשי GPS."""
        if not spd_n:
            return None
        mean = spd_sum / spd_n                    # m/s
        if mean <= 0:
            return None
        pace = round(1000.0 / mean)
        return pace if 100 <= pace <= 3600 else None  # סינון ערכים לא אנושיים

    segments: list[dict] = []
    boundary = seg_meters
    seg_start_time = None
    seg_start_dist = 0.0
    hr_sum = hr_n = 0.0
    spd_sum = spd_n = 0.0
    seg_idx = 1

    for s in samples:
        vals = s.get("metrics", [])
        dist = _val(vals, di)
        if dist is None:
            continue
        t = _time_of(vals)
        if seg_start_time is None:
            seg_start_time = t if t is not None else 0.0

        hr = _val(vals, hi)
        if hr is not None:
            hr_sum += hr
            hr_n += 1
        spd = _val(vals, si)
        if spd is not None and spd > 0:
            spd_sum += spd
            spd_n += 1

        while dist >= boundary:
            seg_dur = (t - seg_start_time) if t is not None else None
            # מעדיפים קצב מזמן-תנועה (כמו ה-laps של גרמין); נפילה למהירות
            # רק כשהזמן לא הגיוני (קפיצת GPS / pause) — ואז למהירות הממוצעת.
            pace_time = round(seg_dur / (seg_meters / 1000.0)) if seg_dur and seg_dur > 0 else None
            pace_speed = _pace_from_speed(spd_sum, spd_n)
            pace = pace_time if (pace_time and 100 <= pace_time <= 3600) else pace_speed
            segments.append({
                "seg": seg_idx,
                "distance_m": round(boundary),
                "pace_sec_per_km": pace,
                "avg_hr": round(hr_sum / hr_n) if hr_n else None,
                "duration_sec": round(seg_dur, 1) if seg_dur is not None else None,
            })
            seg_idx += 1
            seg_start_time = t
            seg_start_dist = boundary
            boundary += seg_meters
            hr_sum = hr_n = 0.0
            spd_sum = spd_n = 0.0

    return segments
