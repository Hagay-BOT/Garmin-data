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
_TIME_SEC_KEYS = ("sumElapsedDuration", "sumDuration", "sumMovingDuration", "directElapsedDuration")
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
    ti = _find_index(descs, _TIME_SEC_KEYS)
    tsi = _find_index(descs, _TIMESTAMP_KEYS) if ti is None else None
    if di is None or (ti is None and tsi is None):
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

    segments: list[dict] = []
    boundary = seg_meters
    seg_start_time = None
    seg_start_dist = 0.0
    hr_sum = 0.0
    hr_n = 0
    seg_idx = 1

    for s in samples:
        vals = s.get("metrics", [])
        dist = _val(vals, di)
        t = _time_of(vals)
        if dist is None or t is None:
            continue
        if seg_start_time is None:
            seg_start_time = t

        hr = _val(vals, hi)
        if hr is not None:
            hr_sum += hr
            hr_n += 1

        # חצינו גבול מקטע (יכול לחצות כמה גבולות אם הדגימה דלילה)
        while dist >= boundary:
            seg_dist = boundary - seg_start_dist
            seg_dur = t - seg_start_time
            pace = round(seg_dur / (seg_dist / 1000.0)) if seg_dist > 0 and seg_dur > 0 else None
            segments.append({
                "seg": seg_idx,
                "distance_m": round(boundary),
                "pace_sec_per_km": pace,
                "avg_hr": round(hr_sum / hr_n) if hr_n else None,
                "duration_sec": round(seg_dur, 1),
            })
            seg_idx += 1
            seg_start_time = t
            seg_start_dist = boundary
            boundary += seg_meters
            hr_sum = 0.0
            hr_n = 0

    return segments
