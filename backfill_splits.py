"""
Backfill חד-פעמי: מוסיף מקטעי 100מ' (splits_100m) לריצות איכות נבחרות ב-data.json.

  python backfill_splits.py --diag           → אבחון: שמות שדות + מקטעים לדוגמה, בלי כתיבה
  python backfill_splits.py                   → מחשב וכותב ל-data.json עבור IDs ברירת המחדל

סיסמה מ-GARMIN_EMAIL / GARMIN_PASSWORD (Secrets בלבד).
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

from splits import compute_segments, descriptor_types

# שתי ריצות האיכות האחרונות (08.06 tempo, 25.05 intervals)
DEFAULT_IDS = [23170600098, 23003018530]


def login():
    from garminconnect import Garmin
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        print("ERROR: GARMIN_EMAIL / GARMIN_PASSWORD not set", file=sys.stderr)
        sys.exit(1)
    c = Garmin(email, password)
    c.login()
    print("✅ התחברות הצליחה")
    return c


def main():
    diag = "--diag" in sys.argv
    ids = DEFAULT_IDS

    client = login()

    with open("data.json", encoding="utf-8") as f:
        data = json.load(f)
    by_id = {a.get("activity_id"): a for a in data["activities"]}

    updated = 0
    for aid in ids:
        print(f"\n=== פעילות {aid} ===")
        try:
            details = client.get_activity_details(aid)
        except Exception as e:
            print(f"  שגיאה בשליפה: {e}")
            continue

        if diag:
            print("  שדות זמינים:", descriptor_types(details))

        segs = compute_segments(details, seg_meters=100.0)
        print(f"  חושבו {len(segs)} מקטעי 100מ'")
        for s in segs[:6]:
            pace = s["pace_sec_per_km"]
            pace_str = f"{pace // 60}:{pace % 60:02d}/ק\"מ" if pace else "—"
            print(f"    מקטע {s['seg']:>3}: {pace_str}  דופק {s['avg_hr']}")

        rec = by_id.get(aid)
        if rec is not None and segs and not diag:
            rec["splits_100m"] = segs
            updated += 1

    if diag:
        print("\n(מצב אבחון — לא נכתב כלום)")
        return

    if updated:
        with open("data.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ נכתבו מקטעי 100מ' ל-{updated} פעילויות ב-data.json")
    else:
        print("\nלא עודכן כלום.")


if __name__ == "__main__":
    main()
