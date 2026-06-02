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

try:
    activities = client.get_activities_by_date(START_DATE, end_date, activitytype="running")
except Exception as e:
    print(f"ERROR: Failed to fetch activities — {e}", file=sys.stderr)
    sys.exit(1)

if not activities:
    print("WARNING: No running activities found in range", file=sys.stderr)

runs = []
for activity in activities:
    type_key = activity.get("activityType", {}).get("typeKey", "")
    if type_key != "running":
        continue

    activity_id = activity.get("activityId")
    if not activity_id:
        continue

    avg_speed = activity.get("averageSpeed", 0)
    pace_sec_per_km = round(1000 / avg_speed) if avg_speed and avg_speed > 0 else None

    distance_m = activity.get("distance", 0)
    distance_km = round(distance_m / 1000, 2) if distance_m else None

    gct_ms = None
    gps_points = []
    try:
        details = client.get_activity_details(activity_id)

        # GCT
        gct_ms = details.get("avgGroundContactTime")
        if gct_ms is None:
            for m in details.get("connectIQMeasurements", []):
                if "groundContact" in str(m.get("key", "")).lower():
                    gct_ms = m.get("value")
                    break

        # GPS — דגימה כל 10 נקודות לחיסכון בנפח
        geo = details.get("geoPolylineDTO", {}).get("polyline", [])
        gps_points = [
            {"lat": p["lat"], "lon": p["lon"]}
            for p in geo[::10]
            if "lat" in p and "lon" in p
        ]
    except Exception:
        pass  # GCT ו-GPS לא קריטיים — ממשיך בלעדיהם

    time.sleep(0.5)  # מניעת rate limiting

    runs.append({
        "date": activity.get("startTimeLocal", "")[:10],
        "distance_km": distance_km,
        "duration_sec": int(activity.get("duration", 0)),
        "pace_sec_per_km": pace_sec_per_km,
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "cadence_spm": round(activity.get("averageRunningCadenceInStepsPerMinute") or 0) or None,
        "gct_ms": gct_ms,
        "gps": gps_points,
    })

output = {
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "runs": sorted(runs, key=lambda r: r["date"]),
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"OK: Saved {len(runs)} runs to data.json")
