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

START_DATE = "2026-04-01"
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
        except Exception:
            pass
        time.sleep(0.5)

    records.append({
        "date": activity.get("startTimeLocal", "")[:10],
        "activity_type": type_key,
        "category": classify(type_key, aerobic_effect),
        "distance_km": distance_km,
        "duration_sec": int(activity.get("duration", 0)),
        "pace_sec_per_km": pace_sec_per_km,
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "cadence_spm": cadence_spm,
        "gct_ms": gct_ms,
        "aerobic_effect": aerobic_effect,
        "anaerobic_effect": anaerobic_effect,
        "training_stress_score": tss,
        "gps": gps_points,
    })

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
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

run_count = sum(1 for r in records if r["activity_type"] == "running")
print(f"OK: Saved {len(records)} activities ({run_count} runs) to data.json")
