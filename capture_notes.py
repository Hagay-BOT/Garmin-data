"""
קולט הערות חופשיות מטלגרם ל-journal.json.

מבוסס-זמן (לא צורך offset) כדי לדור בכפיפה אחת עם weekly_revise.py שגם קורא
את אותו בוט. כל הודעת טקסט חדשה (אחרי last_ts) נרשמת כהערת יומן.
רץ בתדירות גבוהה (יחד עם ה-watcher של אחרי-אימון).

סודות (TELEGRAM_BOT_TOKEN/CHAT_ID) — ממשתני סביבה (GitHub Secrets בלבד).
"""
import os
import datetime

import telegram_notify as tg
import journal


def main() -> None:
    d = journal._load()
    since = d.get("last_ts", 0)
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    newmax, added = since, 0

    for u in tg.get_updates():
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id", "")) != str(chat):
            continue
        ts = msg.get("date", 0)
        if ts <= since:
            continue
        newmax = max(newmax, ts)
        text = (msg.get("text") or "").strip()
        if not text:
            continue
        # M6: אישורים ("אשר") ובחירות A/B הם פקודות-זרימה, לא הערות-יומן — לא מזהמים.
        import telegram_intake
        if telegram_intake.classify(text, awaiting_choice=True) in ("approval", "choice"):
            print(f"⏭️  פקודת-זרימה ({text[:20]!r}) — לא נרשמת ליומן.")
            continue
        # תאריך לפי שעון ישראל (UTC+3) — קירוב מספיק טוב לרישום יומי
        day = (datetime.datetime.utcfromtimestamp(ts) +
               datetime.timedelta(hours=3)).date().isoformat()
        d["notes"].append({"date": day, "text": text})
        added += 1
        print(f"📝 נרשמה הערה ({day}): {text[:60]}")

    d["last_ts"] = newmax
    journal._save(d)
    print(f"capture_notes: {added} הערות חדשות (last_ts={newmax}).")


if __name__ == "__main__":
    main()
