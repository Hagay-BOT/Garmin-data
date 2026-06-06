"""
Debug script: discovers actual Garmin API field names for recovery HR, stamina, and laps.
Saves full raw API responses to debug_output.json.
"""
import os, json, sys
from garminconnect import Garmin, GarminConnectAuthenticationError

email = os.environ.get("GARMIN_EMAIL")
password = os.environ.get("GARMIN_PASSWORD")
if not email or not password:
    print("ERROR: GARMIN_EMAIL or GARMIN_PASSWORD not set", file=sys.stderr)
    sys.exit(1)

client = Garmin(email, password)
client.login()

# Get the 3 most recent activities
activities = client.get_activities(0, 5)
runs = [a for a in activities if a.get("activityType", {}).get("typeKey") == "running"]
if not runs:
    runs = activities[:1]

activity = runs[0]
activity_id = activity.get("activityId")
print(f"Using activity: {activity_id} on {activity.get('startTimeLocal','')[:10]}")

output = {
    "activity_id": activity_id,
    "batch_summary_keys": sorted(activity.keys()),
    "batch_recovery_hr": activity.get("recoveryHeartRate"),
    "batch_beginStamina": activity.get("beginningStamina"),
    "batch_endStamina": activity.get("endingStamina"),
    "batch_fields_with_values": {k: v for k, v in activity.items()
                                  if v is not None and k not in ("activityType", "summaryDTO")},
}

# get_activity (single activity summary with basic splits)
try:
    single = client.get_activity(activity_id)
    output["single_activity_keys"] = sorted(single.keys()) if isinstance(single, dict) else type(single).__name__
    output["single_recovery_hr"] = single.get("recoveryHeartRate") if isinstance(single, dict) else None
    output["single_beginStamina"] = single.get("beginningStamina") if isinstance(single, dict) else None
    # Print all non-null fields
    if isinstance(single, dict):
        output["single_fields_with_values"] = {k: v for k, v in single.items()
                                                 if v is not None and not isinstance(v, (dict, list))}
except Exception as e:
    output["single_error"] = str(e)

# get_activity_splits (laps)
try:
    splits = client.get_activity_splits(activity_id)
    output["splits_type"] = type(splits).__name__
    if isinstance(splits, dict):
        output["splits_keys"] = sorted(splits.keys())
        # Find the list of laps
        for k, v in splits.items():
            if isinstance(v, list) and len(v) > 0:
                output[f"splits_{k}_count"] = len(v)
                output[f"splits_{k}_first_item_keys"] = sorted(v[0].keys()) if isinstance(v[0], dict) else str(v[0])
    elif isinstance(splits, list):
        output["splits_count"] = len(splits)
        if splits:
            output["splits_first_item_keys"] = sorted(splits[0].keys()) if isinstance(splits[0], dict) else str(splits[0])
except Exception as e:
    output["splits_error"] = str(e)

# get_activity_hr_in_timezones
try:
    hr_zones = client.get_activity_hr_in_timezones(activity_id)
    output["hr_zones_type"] = type(hr_zones).__name__
    if isinstance(hr_zones, list):
        output["hr_zones_count"] = len(hr_zones)
        if hr_zones:
            output["hr_zones_first"] = hr_zones[0]
    elif isinstance(hr_zones, dict):
        output["hr_zones_keys"] = sorted(hr_zones.keys())
        output["hr_zones_sample"] = hr_zones
except Exception as e:
    output["hr_zones_error"] = str(e)

# get_activity_details - check for recovery HR and stamina in details
try:
    details = client.get_activity_details(activity_id)
    if isinstance(details, dict):
        output["details_top_keys"] = sorted(details.keys())
        # Search for stamina/recovery in summaryDTO
        summary_dto = details.get("summaryDTO", {})
        if summary_dto:
            output["details_summaryDTO_keys"] = sorted(summary_dto.keys())
            output["details_recovery_hr"] = summary_dto.get("recoveryHeartRate")
            output["details_beginStamina"] = summary_dto.get("beginningStamina")
            output["details_endStamina"] = summary_dto.get("endingStamina")
        # Search for any key containing "recovery" or "stamina"
        def find_keys(d, prefix=""):
            found = {}
            if isinstance(d, dict):
                for k, v in d.items():
                    full_key = f"{prefix}.{k}" if prefix else k
                    if any(x in k.lower() for x in ["recovery", "stamina", "endhr"]):
                        found[full_key] = v
                    found.update(find_keys(v, full_key))
            return found
        output["details_recovery_stamina_fields"] = find_keys(details)
except Exception as e:
    output["details_error"] = str(e)

with open("debug_output.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print("OK: Saved debug output to debug_output.json")
