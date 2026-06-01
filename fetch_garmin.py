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

    avg_speed = activity.get("averageSpeed", 0)  # m/s
    pace_sec_per_km = round(1000 / avg_speed) if avg_speed and avg_speed > 0 else None

    distance_m = activity.get("distance", 0)
    distance_km = round(distance_m / 1000, 2) if distance_m else None

    gct_ms = None
    try:
        details = client.get_activity_details(activity_id)
        gct_ms = details.get("avgGroundContactTime")
        if gct_ms is None:
            for m in details.get("connectIQMeasurements", []):
                if "groundContact" in str(m.get("key", "")).lower():
                    gct_ms = m.get("value")
                    break
    except Exception:
        pass

    time.sleep(0.5)

    runs.append({
        "date": activity.get("startTimeLocal", "")[:10],
        "distance_km": distance_km,
        "duration_sec": int(activity.get("duration", 0)),
        "pace_sec_per_km": pace_sec_per_km,
        "avg_hr": activity.get("averageHR"),
        "max_hr": activity.get("maxHR"),
        "cadence_spm": activity.get("averageRunningCadenceInStepsPerMinute"),
        "gct_ms": gct_ms,
    })

output = {
    "last_updated": datetime.now(timezone.utc).isoformat(),
    "runs": sorted(runs, key=lambda r: r["date"]),
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"OK: Saved {len(runs)} runs to data.json")
