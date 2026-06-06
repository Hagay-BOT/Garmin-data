"""
Debug script v2: checks summaryDTO for recovery HR and stamina fields.
"""
import os, json, sys
from garminconnect import Garmin

email = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")
if not email or not password:
    print("ERROR: GARMIN_EMAIL or GARMIN_PASSWORD not set", file=sys.stderr)
    sys.exit(1)

client = Garmin(email, password)
client.login()

activities = client.get_activities(0, 5)
runs = [a for a in activities if a.get("activityType", {}).get("typeKey") == "running"]
activity = runs[0]
activity_id = activity.get("activityId")
print(f"Activity: {activity_id}")

output = {"activity_id": activity_id}

# summaryDTO deep dive
try:
    single = client.get_activity(activity_id)
    summary = single.get("summaryDTO", {})
    output["summaryDTO_all_keys"] = sorted(summary.keys()) if isinstance(summary, dict) else str(type(summary))
    output["summaryDTO_non_null"] = {k: v for k, v in summary.items()
                                      if v is not None and not isinstance(v, (dict, list))} if isinstance(summary, dict) else {}
except Exception as e:
    output["single_error"] = str(e)

# Check first lap from splits for cadence field value
try:
    splits = client.get_activity_splits(activity_id)
    laps = splits.get("lapDTOs", [])
    if laps:
        lap = laps[0]
        output["first_lap_sample"] = {k: v for k, v in lap.items() if v is not None and not isinstance(v, (dict, list))}
        output["first_lap_cadence_fields"] = {k: v for k, v in lap.items() if "cadence" in k.lower() or "run" in k.lower()}
except Exception as e:
    output["splits_error"] = str(e)

# Check heartRateDTOs from details for cardiac drift
try:
    details = client.get_activity_details(activity_id, maxchart=500)
    hr_dtos = details.get("heartRateDTOs", [])
    output["heartRateDTOs_count"] = len(hr_dtos)
    if hr_dtos:
        output["heartRateDTOs_first"] = hr_dtos[0]
        output["heartRateDTOs_last"] = hr_dtos[-1]
except Exception as e:
    output["details_error"] = str(e)

with open("debug_output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print("OK: Saved debug_output.json")
