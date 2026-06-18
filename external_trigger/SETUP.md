# הפעלה אמינה של ניתוח הריצה — מדריך הקמה

## הבעיה שזה פותר
GitHub Actions cron הוא *best-effort* — בשעות עומס הוא **מדלג** על הרצות (ב-18/6 כל חלון הערב לא רץ).
הפתרון: טריגר חיצוני אמין שמפעיל את ה-workflow דרך `repository_dispatch`. שני מסלולים, שניהם
משתמשים באותו PAT.

```
                          ┌─ cron-job.org (כל 30 דק', אמין)  ──┐
finished a run ──────────►│                                    ├──► GitHub repository_dispatch
press Telegram button ───►└─ Cloudflare Worker (מיידי) ────────┘         (type: run-analysis)
                                                                                  │
                                                                                  ▼
                                                                  coach-postworkout.yml רץ
                                                                  → Sonnet רק אם יש ריצה חדשה
                                                                  → ניתוח לטלגרם
```

---

## שלב 0 · צור fine-grained PAT (פעם אחת, ~2 דק')
1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token.
2. **Repository access:** Only select repositories → `Hagay-BOT/Garmin-data`.
3. **Permissions:** Repository permissions → **Actions: Read and write**. (זה כל מה שצריך.)
4. Expiration: בחר ארוך (שנה) או custom.
5. העתק את הטוקן (`github_pat_...`) — מוצג פעם אחת. **לעולם אל תכניס אותו לקוד.**

---

## מסלול A · אמינות אוטומטית (cron-job.org) — חובה

זה מה שמבטיח "לא יקרה שוב". לוקח ~5 דק'.

1. הירשם חינם ב-https://cron-job.org → Create cronjob.
2. **URL:** `https://api.github.com/repos/Hagay-BOT/Garmin-data/dispatches`
3. **Schedule:** כל 30 דקות בחלונות ריצה (או פשוט "every 30 minutes" כל היום — זול, 0 טוקנים כשאין ריצה).
4. **Advanced → Request method:** `POST`
5. **Advanced → Headers** (הוסף שלוש שורות):
   ```
   Authorization: Bearer github_pat_...        ← ה-PAT משלב 0
   Accept: application/vnd.github+json
   User-Agent: garmin-coach-cron
   ```
6. **Advanced → Request body:**
   ```json
   {"event_type":"run-analysis"}
   ```
7. שמור. cron-job.org יראה תגובת `204 No Content` = הצלחה.

> ה-PAT נשמר מוצפן אצל cron-job.org, לא בריפו. תואם את כלל האבטחה (סודות לא בקוד).

---

## מסלול B · כפתור מיידי בטלגרם (Cloudflare Worker) — אופציונלי

נותן "סיימתי ריצה → לחיצה → ניתוח מיידי" בלי להמתין ל-cron.

### B1 · פרוס את ה-Worker (~3 דק')
1. הירשם חינם ב-https://workers.cloudflare.com → Create Worker.
2. הדבק את התוכן של [`worker.js`](worker.js) → Deploy.
3. Worker → Settings → **Variables and Secrets**, הוסף:
   | שם | סוג | ערך |
   |---|---|---|
   | `GH_PAT` | Secret | ה-PAT משלב 0 |
   | `TRIGGER_KEY` | Secret | מחרוזת אקראית ארוכה שתבחר (למשל `openssl rand -hex 16`) |
   | `GH_OWNER` | Text | `Hagay-BOT` |
   | `GH_REPO` | Text | `Garmin-data` |
4. ה-URL של ה-Worker יהיה משהו כמו `https://garmin-trigger.<שמך>.workers.dev`.

### B2 · חבר את הכפתור לטלגרם
הכתובת המלאה של הכפתור = `<worker-url>?key=<TRIGGER_KEY>`.

הוסף אותה כ-**GitHub Secret** בשם `TRIGGER_BUTTON_URL`
(Settings → Secrets and variables → Actions → New secret).
הקוד בהודעת הבוקר יוסיף אוטומטית כפתור "📊 נתח ריצה עכשיו" כשהסוד קיים — בלי הסוד, אין כפתור (אינרטי).

> בדיקת אבטחה: ה-`TRIGGER_KEY` ב-URL מונע הפעלה מאקראי. הקישור נמצא רק בצ'אט הפרטי שלך.

---

## בדיקה
- **מסלול A:** ב-cron-job.org → Run now → צפה ל-`204`. ב-GitHub Actions תראה הרצה חדשה (trigger: repository_dispatch).
- **מסלול B:** פתח את `<worker-url>?key=<key>` בדפדפן → "✅ הניתוח רץ" → הרצה חדשה ב-Actions.
