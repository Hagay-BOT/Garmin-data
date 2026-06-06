import os
import json
import sys
import time
from datetime import date, datetime, timezone
from garminconnect import Garmin, GarminConnectAuthenticationError, GarminConnectConnectionError

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

STRENGTH_TYPES = {"strength_training", "weightlifting", "fitness_equipment", "gym", "indoor_cardio"}

def classify(type_key, aerobic_effect):
    if type_key in STRENGTH_TYPES:
        return "strength"
    if type_key == "running":
        return "quality_run" if (aerobic_effect or 0) > 2.5 else "base_run"
    return "other"

try:
    activities = client.get_activities_by_date(START_DATE, end_date)
except Exception as e:
    print(f"ERROR: Failed to fetch activities — {e}", file=sys.stderr)
    sys.exit(1)

global_max_hr = max((a.get("maxHR") or 0 for a in activities), default=180)

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

    gct_ms = None
    gps_points = []
    hr_zones_sec = [0, 0, 0, 0, 0]
    hr_drift_bpm = None
    temperature = None
    laps = []

    # Extra fields from activity summary
    max_speed = activity.get("maxSpeed", 0)
    best_pace_sec_per_km = round(1000 / max_speed) if max_speed and max_speed > 0 else None
    max_cadence_raw = activity.get("maxRunningCadenceInStepsPerMinute")
    max_cadence_spm = round(max_cadence_raw) if max_cadence_raw else None
    stride_raw = activity.get("avgStrideLength")
    stride_length_m = round(stride_raw / 100, 2) if stride_raw else None
    vert_osc = activity.get("avgVerticalOscillation")
    vert_ratio = activity.get("avgVerticalRatio")
    vo2max = activity.get("vO2MaxValue")
    stamina_start = activity.get("beginningStamina")
    stamina_end = activity.get("endingStamina")
    exercise_load = activity.get("activityTrainingLoad") or activity.get("exerciseLoad")
    active_cal = activity.get("activeKilocalories")
    total_cal = activity.get("calories")
    sweat_raw = activity.get("waterEstimated")
    sweat_ml = round(sweat_raw) if sweat_raw else None
    bb_impact = activity.get("bodyBatteryDrainedDuringActivity")
    avg_resp = activity.get("avgRespirationRate")
    max_resp = activity.get("maxRespirationRate")
    mod_min = activity.get("moderateIntensityMinutes")
    vig_min = activity.get("vigorousIntensityMinutes")
    ascent_raw = activity.get("elevationGain")
    descent_raw = activity.get("elevationLoss")
    total_ascent_m = round(ascent_raw) if ascent_raw else None
    total_descent_m = round(descent_raw) if descent_raw else None
    training_effect_label = activity.get("trainingEffectLabel")
    recovery_hr = activity.get("recoveryHeartRate")

    if type_key == "running":
        try:
            details = client.get_activity_details(activity_id)
            gct_ms = details.get("avgGroundContactTime")
            if gct_ms is None:
                for m in details.get("connectIQMeasurements", []):
                    if "groundContact" in str(m.get("key", "")).lower():
                        gct_ms = m.get("value")
                        break
            geo = details.get("geoPolylineDTO", {}).get("polyline", [])
            gps_points = [
                {"lat": p["lat"], "lon": p["lon"]}
                for p in geo[::10]
                if "lat" in p and "lon" in p
            ]
            # Temperature from details
            weather = details.get("weatherDTO") or {}
            temperature = weather.get("temperature") or details.get("avgTemperature")

            # HR zones & cardiac drift from per-second metrics
            descriptors = details.get("metricDescriptors", [])
            metrics_data = details.get("activityDetailMetrics", [])
            hr_idx = next((d["metricsIndex"] for d in descriptors
                          if d.get("metricsType") == "directHeartRate"), None)
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
                    zone_thresholds = [0.60, 0.70, 0.80, 0.90, 1.01]
                    for hr in hr_vals:
                        pct = hr / global_max_hr
                        z = next((i for i, t in enumerate(zone_thresholds) if pct < t), 4)
                        hr_zones_sec[z] += 1
        except Exception:
            pass

        # Lap data
        try:
            lap_data = client.get_activity_laps(activity_id)
            if isinstance(lap_data, dict):
                lap_list = lap_data.get("lapDTOs") or lap_data.get("laps") or []
            else:
                lap_list = lap_data or []
            for i, lap in enumerate(lap_list):
                lap_spd = lap.get("averageSpeed", 0)
                laps.append({
                    "lap": i + 1,
                    "distance_km": round((lap.get("distance") or 0) / 1000, 2),
                    "duration_sec": int(lap.get("duration") or 0),
                    "pace_sec_per_km": round(1000 / lap_spd) if lap_spd and lap_spd > 0 else None,
                    "avg_hr": lap.get("averageHR"),
                    "cadence_spm": round(lap.get("averageRunningCadenceInStepsPerMinute")) if lap.get("averageRunningCadenceInStepsPerMinute") else None,
                })
        except Exception:
            pass

        time.sleep(0.5)

    records.append({
        "activity_id": activity_id,
        "date": activity.get("startTimeLocal", "")[:10],
        "start_time": activity.get("startTimeLocal", ""),
        "activity_type": type_key,
        "category": classify(type_key, aerobic_effect),
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
        "stamina_start_pct": stamina_start,
        "stamina_end_pct": stamina_end,
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
    })

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

# שינה + Body Battery לכל יום אימון
unique_dates = sorted(set(r["date"] for r in records))
daily = {}

for d in unique_dates:
    sleep_score = None
    body_battery = None
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
        if bb_data:
            vals = [b.get("charged", 0) for b in bb_data if b.get("charged") is not None]
            body_battery = max(vals) if vals else None
    except Exception:
        pass
    time.sleep(0.3)
    daily[d] = {"sleep_score": sleep_score, "body_battery_morning": body_battery}

output = {
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "activities": sorted(records, key=lambda r: r["date"]),
    "daily": daily,
    "shoes": shoes_output,
    "global_max_hr": global_max_hr,
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

run_count = sum(1 for r in records if r["activity_type"] == "running")
print(f"OK: Saved {len(records)} activities ({run_count} runs) to data.json")
