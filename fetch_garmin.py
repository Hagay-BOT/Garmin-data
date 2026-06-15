import os
import json
import sys
import time
from datetime import date, datetime, timezone, timedelta
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError
from splits import compute_segments

email = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")
if not email or not password:
    print("ERROR: GARMIN_EMAIL or GARMIN_PASSWORD not set", file=sys.stderr)
    sys.exit(1)

try:
    client = Garmin(email, password)
    client.login()
except GarminConnectAuthenticationError as e:
    print(f"ERROR: Authentication failed — {e}", file=sys.stderr)
    sys.exit(1)
except GarminConnectConnectionError as e:
    print(f"ERROR: Connection failed — {e}", file=sys.stderr)
    sys.exit(1)

START_DATE = "2024-01-01"
end_date = date.today().isoformat()
OVERLAP_DAYS = 5  # re-process the last few days each run to catch edits / late syncs

# ── Incremental: reuse existing data.json, only fetch what is new ──────────────
existing_records: dict = {}
existing_daily: dict = {}
existing_max_hr = 0
try:
    with open("data.json", encoding="utf-8") as f:
        _prev = json.load(f)
    for _r in _prev.get("activities", []):
        if _r.get("activity_id"):
            existing_records[_r["activity_id"]] = _r
    existing_daily = _prev.get("daily", {}) or {}
    existing_max_hr = _prev.get("global_max_hr") or 0
except (FileNotFoundError, json.JSONDecodeError):
    pass

if existing_records:
    _latest = max((r.get("date") or "" for r in existing_records.values()))
    fetch_start = (date.fromisoformat(_latest) - timedelta(days=OVERLAP_DAYS)).isoformat()
    print(f"Incremental: {len(existing_records)} cached activities, fetching from {fetch_start}")
else:
    fetch_start = START_DATE
    print(f"No cache — full fetch from {START_DATE}")

STRENGTH_TYPES = {"strength_training", "weightlifting", "fitness_equipment", "gym", "indoor_cardio"}
# Activity types treated as a run (treadmill + trail included)
RUN_TYPES = {"running", "treadmill_running", "trail_running"}

def classify_quality_subtype(anaerobic_eff, max_hr, avg_hr, ascent_m, dist_km):
    """
    תת-קטגוריה של ריצת איכות (נקרא רק כשיודעים שזו ריצת איכות):
      quality_intervals — אינטרוואלים   (anaerobic גבוה / HR spike חד)
      quality_hills     — עליות          (עלייה גבוהה לק"מ)
      quality_segments  — מקטעים        (מאמץ מעורב, fartlek-style)
      quality_tempo     — קצב/טמפו      (ברירת מחדל — מאמץ sustained)
    """
    anaerobic_eff = anaerobic_eff or 0
    max_hr   = max_hr  or 0
    avg_hr   = avg_hr  or 0
    ascent_m = ascent_m or 0
    dist_km  = max(dist_km or 1, 0.1)

    hr_spike      = max_hr / avg_hr if avg_hr > 0 else 1.0
    ascent_per_km = ascent_m / dist_km

    # אינטרוואלים: anaerobic גבוה או HR spike בולט
    if anaerobic_eff >= 2.5 or hr_spike >= 1.28:
        return "quality_intervals"

    # עליות: >25m/km או >120m כולל
    if ascent_per_km >= 25 or ascent_m >= 120:
        return "quality_hills"

    # מקטעים: anaerobic בינוני — מאמץ מעורב לא מובנה
    if anaerobic_eff >= 1.5:
        return "quality_segments"

    # קצב/טמפו: ברירת מחדל לריצת איכות
    return "quality_tempo"


# תוויות Garmin שמעידות על בסיס (ריצה קלה/שחזור)
_BASE_LABELS   = {"RECOVERY", "AEROBIC_BASE", "NO_BENEFIT", "MINOR"}
# תוויות Garmin שמעידות בוודאות על ריצת עצימות (אינטרוואלים / VO2max)
_HIIT_LABELS   = {"ANAEROBIC_CAPACITY", "SPEED", "VO2MAX"}
# תוויות Garmin שמעידות על ריצת איכות (טמפו / LT)
_QUALITY_LABELS = {"TEMPO", "LACTATE_THRESHOLD", "OVERREACHING", "MAINTAINING"}


def classify(type_key, aerobic_effect, anaerobic_effect=None,
             max_hr=None, avg_hr=None, ascent_m=None, dist_km=None,
             training_effect_label=None):
    """
    סיווג פעילות לקטגוריה.

    היררכיה:
      1. לא ריצה → strength / other
      2. תווית Garmin ידועה → BASE / HIIT → סיווג ישיר
      3. תווית TEMPO/LT → classify_quality_subtype
      4. Fallback (אין תווית): aerobic_effect > 3.5 → quality, אחרת base
    """
    if type_key in STRENGTH_TYPES:
        return "strength"
    if type_key not in RUN_TYPES:
        return "other"

    label = (training_effect_label or "").upper().strip()

    # --- שכבה 1: תוויות בסיס ← base_run ישיר ---
    if label in _BASE_LABELS:
        return "base_run"

    # --- שכבה 2: HIIT / VO2max ← quality_intervals ישיר ---
    if label in _HIIT_LABELS:
        return "quality_intervals"

    # --- שכבה 3: TEMPO / LT ← תת-קטגוריה של איכות ---
    if label in _QUALITY_LABELS:
        return classify_quality_subtype(anaerobic_effect, max_hr, avg_hr, ascent_m, dist_km)

    # --- שכבה 4: Fallback (אין תווית או תווית לא מוכרת) ---
    # סף גבוה יותר (3.5 במקום 2.5) כדי להקטין false-positives
    if (aerobic_effect or 0) > 3.5:
        return classify_quality_subtype(anaerobic_effect, max_hr, avg_hr, ascent_m, dist_km)
    return "base_run"

try:
    activities = client.get_activities_by_date(fetch_start, end_date)
except Exception as e:
    print(f"ERROR: Failed to fetch activities — {e}", file=sys.stderr)
    sys.exit(1)

global_max_hr = max([existing_max_hr] + [(a.get("maxHR") or 0) for a in activities]) or 180

if not activities:
    print("WARNING: No activities found in range", file=sys.stderr)

records = []
for activity in activities:
    type_key = activity.get("activityType", {}).get("typeKey", "other")
    activity_id = activity.get("activityId")
    if not activity_id:
        continue

    avg_speed = activity.get("averageSpeed", 0)
    pace_sec_per_km = round(1000 / avg_speed) if avg_speed and avg_speed > 0 else None
    distance_m = activity.get("distance", 0)
    distance_km = round(distance_m / 1000, 2) if distance_m else None
    cadence_raw = activity.get("averageRunningCadenceInStepsPerMinute")
    cadence_spm = round(cadence_raw) if cadence_raw else None
    aerobic_effect = activity.get("aerobicTrainingEffect")
    anaerobic_effect = activity.get("anaerobicTrainingEffect")
    tss = activity.get("trainingStressScore")

    gps_points = []
    hr_drift_bpm = None
    temperature = None
    laps = []
    splits_100m = []

    # Extra fields from activity summary
    max_speed = activity.get("maxSpeed", 0)
    best_pace_sec_per_km = round(1000 / max_speed) if max_speed and max_speed > 0 else None
    max_cadence_raw = activity.get("maxRunningCadenceInStepsPerMinute")
    max_cadence_spm = round(max_cadence_raw) if max_cadence_raw else None
    # GCT from batch summary (avgGroundContactTime is in miliseconds)
    gct_raw = activity.get("avgGroundContactTime")
    gct_ms = round(gct_raw) if gct_raw else None
    stride_raw = activity.get("avgStrideLength")
    stride_length_m = round(stride_raw / 100, 2) if stride_raw else None
    vert_osc = activity.get("avgVerticalOscillation")
    vert_ratio = activity.get("avgVerticalRatio")
    vo2max = activity.get("vO2MaxValue")
    exercise_load = activity.get("activityTrainingLoad") or activity.get("exerciseLoad")
    active_cal = activity.get("activeKilocalories")
    total_cal = activity.get("calories")
    sweat_raw = activity.get("waterEstimated")
    sweat_ml = round(sweat_raw) if sweat_raw else None
    bb_impact = activity.get("differenceBodyBattery")          # correct field name
    avg_resp = activity.get("avgRespirationRate")
    max_resp = activity.get("maxRespirationRate")
    mod_min = activity.get("moderateIntensityMinutes")
    vig_min = activity.get("vigorousIntensityMinutes")
    ascent_raw = activity.get("elevationGain")
    descent_raw = activity.get("elevationLoss")
    total_ascent_m = round(ascent_raw) if ascent_raw else None
    total_descent_m = round(descent_raw) if descent_raw else None
    training_effect_label = activity.get("trainingEffectLabel")

    category = classify(type_key, aerobic_effect, anaerobic_effect,
                        activity.get("maxHR"), activity.get("averageHR"),
                        activity.get("elevationGain"), distance_km,
                        training_effect_label)

    # HR zones from batch summary fields (seconds per zone, direct from Garmin)
    hr_zones_sec = [
        round(activity.get("hrTimeInZone_1") or 0),
        round(activity.get("hrTimeInZone_2") or 0),
        round(activity.get("hrTimeInZone_3") or 0),
        round(activity.get("hrTimeInZone_4") or 0),
        round(activity.get("hrTimeInZone_5") or 0),
    ]

    # Recovery HR and stamina come from summaryDTO of get_activity()
    recovery_hr = None
    stamina_start = None
    stamina_end = None

    if type_key in RUN_TYPES:
        # Single-activity summary for recovery HR + stamina
        try:
            act_summary = client.get_activity(activity_id)
            summary_dto = act_summary.get("summaryDTO", {}) if isinstance(act_summary, dict) else {}
            recovery_hr = summary_dto.get("recoveryHeartRate")
            stamina_start = summary_dto.get("beginPotentialStamina")
            stamina_end = summary_dto.get("endPotentialStamina")
        except Exception:
            pass

        try:
            details = client.get_activity_details(activity_id)
            geo = details.get("geoPolylineDTO", {}).get("polyline", [])
            gps_points = [
                {"lat": p["lat"], "lon": p["lon"]}
                for p in geo[::10]
                if "lat" in p and "lon" in p
            ]
            # Temperature from details
            weather = details.get("weatherDTO") or {}
            temperature = weather.get("temperature") or details.get("avgTemperature")

            # Cardiac drift from per-second HR metrics
            descriptors = details.get("metricDescriptors", [])
            metrics_data = details.get("activityDetailMetrics", [])
            hr_idx = next(
                (d["metricsIndex"] for d in descriptors
                 if d.get("metricsType") in ("directHeartRate", "heartRate")),
                None
            )
            if hr_idx is not None and metrics_data and global_max_hr > 0:
                hr_vals = []
                for m_entry in metrics_data:
                    vals = m_entry.get("metrics", [])
                    if hr_idx < len(vals) and vals[hr_idx] is not None:
                        hr_vals.append(float(vals[hr_idx]))
                if hr_vals:
                    third = max(1, len(hr_vals) // 3)
                    hr_drift_bpm = round(
                        sum(hr_vals[-third:]) / third - sum(hr_vals[:third]) / third, 1
                    )

            # מקטעי 100מ' — רק לריצות איכות (לראות אינטרוולים קצרים)
            if str(category).startswith("quality_"):
                splits_100m = compute_segments(details, seg_meters=100.0)
        except Exception:
            pass

        # Lap data via get_activity_splits (lapDTOs with averageRunCadence)
        try:
            lap_data = client.get_activity_splits(activity_id)
            lap_list = lap_data.get("lapDTOs") or [] if isinstance(lap_data, dict) else []
            for i, lap in enumerate(lap_list):
                lap_spd = lap.get("averageSpeed", 0)
                cad_raw = lap.get("averageRunCadence")
                laps.append({
                    "lap": i + 1,
                    "distance_km": round((lap.get("distance") or 0) / 1000, 2),
                    "duration_sec": int(lap.get("duration") or 0),
                    "pace_sec_per_km": round(1000 / lap_spd) if lap_spd and lap_spd > 0 else None,
                    "avg_hr": lap.get("averageHR"),
                    "cadence_spm": round(cad_raw) if cad_raw else None,
                })
        except Exception:
            pass

        time.sleep(0.5)

    records.append({
        "activity_id": activity_id,
        "date": activity.get("startTimeLocal", "")[:10],
        "start_time": activity.get("startTimeLocal", ""),
        "activity_type": type_key,
        "category": category,
        "distance_km": distance_km,
        "duration_sec": int(activity.get("duration", 0)),
        "pace_sec_per_km": pace_sec_per_km,
        "best_pace_sec_per_km": best_pace_sec_per_km,
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "recovery_hr": recovery_hr,
        "cadence_spm": cadence_spm,
        "max_cadence_spm": max_cadence_spm,
        "gct_ms": gct_ms,
        "stride_length_m": stride_length_m,
        "vertical_oscillation_cm": vert_osc,
        "vertical_ratio_pct": vert_ratio,
        "aerobic_effect": aerobic_effect,
        "anaerobic_effect": anaerobic_effect,
        "training_effect_label": training_effect_label,
        "training_stress_score": tss,
        "exercise_load": exercise_load,
        "vo2max": vo2max,
        "stamina_start_pct": round(stamina_start) if stamina_start is not None else None,
        "stamina_end_pct": round(stamina_end) if stamina_end is not None else None,
        "active_calories": active_cal,
        "total_calories": total_cal,
        "sweat_loss_ml": sweat_ml,
        "body_battery_impact": bb_impact,
        "avg_respiration": avg_resp,
        "max_respiration": max_resp,
        "moderate_intensity_min": mod_min,
        "vigorous_intensity_min": vig_min,
        "total_ascent_m": total_ascent_m,
        "total_descent_m": total_descent_m,
        "temperature": temperature,
        "gps": gps_points,
        "hr_zones_sec": hr_zones_sec,
        "hr_drift_bpm": hr_drift_bpm,
        "laps": laps,
        "splits_100m": splits_100m,
    })

# ── Merge freshly-processed activities back into the cached set ───────────────
_fetched_count = len(records)
_merged = dict(existing_records)
for _r in records:
    _merged[_r["activity_id"]] = _r          # new/updated records override cache
records = sorted(_merged.values(), key=lambda r: r.get("date") or "")
print(f"Activities: {_fetched_count} fetched/updated, {len(records)} total")

# נעליים / ציוד מגרמין קונקט
shoes_output = []
try:
    profile = client.get_user_profile()
    user_id = str(profile.get("id") or profile.get("userId") or "")
    if user_id:
        gear_list = client.get_gear(user_id)
        for g in (gear_list or []):
            if str(g.get("gearTypeName", "")).lower() in ("shoes", "running shoes", "shoe"):
                shoes_output.append({
                    "name": g.get("displayName", ""),
                    "total_km": round((g.get("totalDistance") or 0) / 1000, 1),
                    "activity_count": g.get("totalActivities", 0),
                    "max_km": 700,
                })
except Exception:
    pass

# שינה + Body Battery + קלוריות — מצטבר: מטמון נשמר, נמשכים רק ימים חדשים + 14 אחרונים
today_dt = date.today()
last_14_days = {(today_dt - timedelta(days=i)).isoformat() for i in range(14)}
daily = dict(existing_daily)  # reuse every previously-fetched day
# Always refresh the last 14 days; fetch any new activity date not yet cached
_candidate_dates = {r["date"] for r in records if r.get("date")} | last_14_days
to_fetch = sorted(d for d in _candidate_dates if d in last_14_days or d not in existing_daily)
print(f"Daily: fetching {len(to_fetch)} days (reusing {len(existing_daily)} cached)")

for d in to_fetch:
    sleep_score = None
    body_battery = None
    calories_resting = None
    calories_active = None
    try:
        sleep_data = client.get_sleep_data(d)
        sleep_score = (sleep_data.get("dailySleepDTO", {})
                       .get("sleepScores", {})
                       .get("overall", {})
                       .get("value"))
    except Exception:
        pass
    try:
        bb_data = client.get_body_battery(d, d)
        # רמת ה-BD האמיתית נמצאת ב-bodyBatteryValuesArray (לא בשדה "charged"!).
        # השיא היומי ≈ הערך בהתעוררות, כי הסוללה מגיעה לשיא אחרי טעינת הלילה.
        levels = []
        for day in (bb_data or []):
            for entry in (day.get("bodyBatteryValuesArray") or []):
                lvl = None
                if isinstance(entry, (list, tuple)) and len(entry) >= 3:
                    lvl = entry[2]                      # [timestamp, status, level, ...]
                elif isinstance(entry, dict):
                    lvl = entry.get("level") or entry.get("bodyBatteryLevel")
                if isinstance(lvl, (int, float)):
                    levels.append(lvl)
        body_battery = max(levels) if levels else None
    except Exception:
        pass
    try:
        stats = client.get_stats(d)
        calories_resting = stats.get("bmrKilocalories")
        calories_active = stats.get("activeKilocalories")
    except Exception:
        pass
    time.sleep(0.3)
    daily[d] = {
        "sleep_score": sleep_score,
        "body_battery_morning": body_battery,
        "calories_resting": calories_resting,
        "calories_active": calories_active,
    }

output = {
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "activities": sorted(records, key=lambda r: r["date"]),
    "daily": daily,
    "shoes": shoes_output,
    "global_max_hr": global_max_hr,
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

run_count = sum(1 for r in records if r["activity_type"] in RUN_TYPES)
print(f"OK: Saved {len(records)} activities ({run_count} runs) to data.json")
