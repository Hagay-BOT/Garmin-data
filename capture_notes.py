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
    import store
    d = journal._load()
    since = d.get("last_ts", 0)
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    newmax, added = since, 0
    # M10: בחלון שאלת-הזמינות (שבת בוקר→ערב) תשובות חופשיות הן אילוצי-תכנון,
    # לא הערות-יומן — נצברות ב-weekly_state.availability_raw עבור המחולל.
    wstate = store.load_weekly_state()
    awaiting_avail = wstate.get("status") == "awaiting_availability"
    avail_added = False

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
        # M10: תשובת-זמינות (רק אחרי שאלת-הזמינות, לפי חותמת-הזמן שלה) → למחולל.
        if awaiting_avail and ts > wstate.get("sent_at", 0):
            wstate["availability_raw"] = (wstate.get("availability_raw", "")
                                          + ("\n" if wstate.get("availability_raw") else "")
                                          + text)
            avail_added = True
            print(f"🗓️ נקלט אילוץ-זמינות: {text[:60]}")
            continue
        # תאריך לפי שעון ישראל (UTC+3) — קירוב מספיק טוב לרישום יומי
        day = (datetime.datetime.utcfromtimestamp(ts) +
               datetime.timedelta(hours=3)).date().isoformat()
        d["notes"].append({"date": day, "text": text})
        added += 1
        print(f"📝 נרשמה הערה ({day}): {text[:60]}")
        # T6: דגלי-גוף מתמשכים — אורתוגונלי לרישום ההערה (הערה יכולה גם לפתוח דגל).
        import body_state
        for chg in body_state.apply(text, today=day):
            print(f"   {chg}")

    d["last_ts"] = newmax
    journal._save(d)
    if avail_added:
        store.save_weekly_state(wstate)
    print(f"capture_notes: {added} הערות חדשות (last_ts={newmax}).")


if __name__ == "__main__":
    main()
