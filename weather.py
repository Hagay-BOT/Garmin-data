"""
המלצת מיקום ריצה לפי מזג אוויר — חוץ או חדר כושר.
מבדיל בין ריצה ארוכה (רגישה יותר לחום, חשיפה ממושכת) לקצרה.
מקור: Open-Meteo (חינמי, ללא מפתח API). מיקום: מזוהה מ-GPS של הריצה האחרונה.

שימוש:
  python weather.py 2026-06-20T08:00 long
  python weather.py 2026-06-16T07:00 short
"""
import sys
import json
import urllib.request
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).parent
DATA_FILE = BASE / "data.json"

# ספי החלטה (ישראל — החום הוא השיקול המרכזי)
THRESHOLDS = {
    "short": {"feels": 33, "rain_prob": 60, "precip": 2.0, "wind": 40},
    "long":  {"feels": 29, "rain_prob": 50, "precip": 1.0, "wind": 35},
}


def latest_run_location(activities: list) -> tuple[float, float] | None:
    """ממוצע lat/lon מהריצה האחרונה עם GPS."""
    for a in sorted(activities, key=lambda x: x.get("date", ""), reverse=True):
        pts = a.get("gps")
        if pts and isinstance(pts, list):
            lats = [p["lat"] for p in pts if isinstance(p, dict) and "lat" in p]
            lons = [p["lon"] for p in pts if isinstance(p, dict) and "lon" in p]
            if lats and lons:
                return round(sum(lats) / len(lats), 4), round(sum(lons) / len(lons), 4)
    return None


def get_forecast(lat: float, lon: float) -> dict:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=temperature_2m,apparent_temperature,precipitation_probability,"
           "precipitation,wind_speed_10m&timezone=Asia/Jerusalem&forecast_days=16")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _nearest_hour_index(times: list[str], when_iso: str) -> int:
    """אינדקס השעה הקרובה ביותר ל-when_iso ברשימת הזמנים."""
    target = datetime.fromisoformat(when_iso[:16])
    best_i, best_d = 0, None
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t)
        diff = abs((dt - target).total_seconds())
        if best_d is None or diff < best_d:
            best_i, best_d = i, diff
    return best_i


def run_recommendation(forecast: dict, when_iso: str, is_long: bool) -> dict:
    h = forecast["hourly"]
    i = _nearest_hour_index(h["time"], when_iso)
    feels = h["apparent_temperature"][i]
    temp = h["temperature_2m"][i]
    rain_prob = h["precipitation_probability"][i] or 0
    precip = h["precipitation"][i] or 0
    wind = h["wind_speed_10m"][i] or 0

    kind = "long" if is_long else "short"
    th = THRESHOLDS[kind]

    reasons = []
    if feels >= th["feels"]:
        reasons.append(f"מרגיש {feels:.0f}° (מעל {th['feels']}°)")
    if rain_prob >= th["rain_prob"]:
        reasons.append(f"סיכוי גשם {rain_prob}%")
    if precip >= th["precip"]:
        reasons.append(f"משקעים {precip}מ\"מ")
    if wind >= th["wind"]:
        reasons.append(f"רוח {wind:.0f} קמ\"ש")

    indoor = bool(reasons)
    # התראת borderline — קרוב לסף החום
    borderline = (not indoor) and (feels >= th["feels"] - 3)

    if indoor:
        verdict = "🏋️ חדר כושר / הליכון"
        msg = "תנאי חוץ לא נוחים: " + " · ".join(reasons) + ". עדיף פנים."
    elif borderline:
        verdict = "🌤️ חוץ — אבל גבולי"
        msg = f"מרגיש {feels:.0f}°, קרוב לסף. שתה הרבה, צא מוקדם, ושקול הליכון אם לא נעים."
    else:
        verdict = "🏃 חוץ"
        msg = f"תנאים נוחים: {temp:.0f}° (מרגיש {feels:.0f}°), גשם {rain_prob}%, רוח {wind:.0f} קמ\"ש."

    return {
        "verdict": verdict, "indoor": indoor, "borderline": borderline,
        "message": msg, "when": h["time"][i],
        "temp": temp, "feels": feels, "rain_prob": rain_prob,
        "precip": precip, "wind": wind, "run_kind": kind,
    }


def recommend(when_iso: str, is_long: bool) -> dict:
    """נקודת כניסה ראשית — מזהה מיקום, שולף תחזית, מחזיר המלצה."""
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    loc = latest_run_location(data.get("activities", []))
    if not loc:
        return {"error": "אין נתוני GPS לזיהוי מיקום."}
    fc = get_forecast(*loc)
    rec = run_recommendation(fc, when_iso, is_long)
    rec["location"] = loc
    return rec


if __name__ == "__main__":
    when = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat() + "T07:00"
    is_long = (len(sys.argv) > 2 and sys.argv[2].lower() == "long")
    out = recommend(when, is_long)
    if "error" in out:
        print(out["error"])
    else:
        print(f"מיקום: {out['location']} · {out['when']} · {'ארוכה' if is_long else 'קצרה'}")
        print(f"{out['verdict']}")
        print(out["message"])
