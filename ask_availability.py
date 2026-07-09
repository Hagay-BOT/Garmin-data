# -*- coding: utf-8 -*-
"""
ask_availability.py — שאלת-הזמינות השבועית (M10).

רץ שבת בבוקר, לפני בניית התוכנית (שבת 20:30): שואל את הגיא מה התוכניות שלו
לשבוע הבא. התשובות נקלטות ע"י capture_notes (מצב awaiting_availability →
availability_raw ב-weekly_state) ומוזנות למחולל הדטרמיניסטי כאילוצים.
"""
import time

import telegram_notify as tg
import store


def main() -> None:
    st = store.load_weekly_state()
    msg = ("🗓️ <b>לקראת התוכנית של שבוע הבא</b>\n\n"
           "מה התוכניות שלך לשבוע הקרוב? (נסיעות, ימים עמוסים, העדפות)\n"
           "פשוט כתוב חופשי — למשל: \"שלישי אני בנסיעה, מעדיף לונג בשישי\".\n"
           "אין אילוצים? אפשר להתעלם — התוכנית תיבנה רגיל. 🏃")
    mid = tg.send_message(msg)
    if not mid:
        print("⚠️ שאלת הזמינות לא נשלחה (credentials?) — לא משנה מצב.")
        return
    st.update(status="awaiting_availability", sent_at=time.time(),
              availability_raw="")
    store.save_weekly_state(st)
    print(f"📤 שאלת זמינות נשלחה (message_id={mid}) — ממתין לתשובות עד בניית התוכנית.")


if __name__ == "__main__":
    main()
