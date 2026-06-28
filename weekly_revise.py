"""
לולאת עריכת תוכנית שבועית דרך טלגרם.

קולטת תשובה חופשית של הגיא להצעת התוכנית השבועית ומיישמת:
  • "אשר"/"כן"/👍  → confirm_week (נעילה + יומן + גרמין).
  • טקסט חופשי     → coach.run_revise (LLM מעדכן את week_plan.json) → שולח מחדש לאישור.

מצב נשמר ב-weekly_state.json (sent_at = חותמת ההודעה האחרונה; status).
לבדיקה: הגדר env REVISE_TEXT="..." כדי לעקוף את טלגרם.

סודות (GARMIN/TELEGRAM/ANTHROPIC) — ממשתני סביבה (GitHub Secrets בלבד).
"""
import os
import json
import time
import datetime
import html as _html
from pathlib import Path

import telegram_notify as tg

BASE = Path(__file__).parent
STATE = BASE / "weekly_state.json"
PLAN = BASE / "week_plan.json"
DAYS = ["ב", "ג", "ד", "ה", "ו", "ש", "א"]  # Mon..Sun → weekday()

APPROVE = {"אשר", "אשרר", "כן", "מאשר", "אישור", "מעולה", "אוקיי",
           "ok", "okay", "yes", "👍", "✅"}


def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s: dict) -> None:
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_approval(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in APPROVE or any(t == w or t.startswith(w + " ") for w in APPROVE)


def _plan_lines(plan: dict) -> list:
    out = []
    for s in plan.get("sessions", []):
        try:
            wd = DAYS[datetime.date.fromisoformat(s["date"]).weekday()]
        except Exception:
            wd = "?"
        if s.get("type") == "run":
            out.append(f"{wd}׳ · 🏃 {_html.escape(s.get('name', '') or s.get('subtype', 'ריצה'))}")
        else:
            out.append(f"{wd}׳ · 💪 כוח {_html.escape(str(s.get('key', '')))}")
    return out


def main() -> None:
    st = _load_state()
    reply = os.environ.get("REVISE_TEXT") or tg.find_text_reply(st.get("sent_at", 0))
    if not reply:
        print("אין תשובה חדשה — מדלג.")
        return
    # מצב בדיקה: "DRY <טקסט>" → מריץ את מנוע ה-revise בלבד, בלי לשמור/לשלוח/לדחוף.
    dry = False
    if reply.strip().upper().startswith("DRY "):
        dry, reply = True, reply.strip()[4:].strip()
    print(f"📩 תשובה התקבלה: {reply!r}{' (DRY)' if dry else ''}")
    if dry:
        import coach
        coach.run_revise(reply, dry=True)
        print("🧪 DRY — לא נשמר, לא נשלח, לא נדחף.")
        return

    # ── נתיב אישור → push לגרמין ──────────────────────────────────────────
    if _is_approval(reply):
        print("✅ זוהה אישור — מריץ confirm_week (נעילה + יומן + גרמין).")
        import confirm_week
        confirm_week.main()
        st.update(status="approved", sent_at=time.time())
        _save_state(st)
        tg.send_message("✅ התוכנית אושרה ועלתה לגרמין + יומן. בהצלחה! 🏃")
        return

    # ── נתיב עדכון חופשי → LLM משנה את התוכנית ────────────────────────────
    import coach
    saved, messages = coach.run_revise(reply)
    if not saved:
        tg.send_message("⚠️ לא הצלחתי להחיל את השינוי. נסה לנסח אחרת — למשל: "
                        "\"שישי 5 ק\"מ, שבת 10, חמישי בלי ריצה\".")
        return

    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    lines = ["📝 <b>עדכנתי את התוכנית לפי בקשתך:</b>", ""] + _plan_lines(plan)
    if messages:
        lines += ["", "🛡️ " + " · ".join(_html.escape(str(m)) for m in messages)]
    lines += ["", "השב <b>'אשר'</b> להעלאה לגרמין, או שלח עוד שינוי. ✏️"]
    mid = tg.send_message("\n".join(lines))
    st.update(status="pending_review", sent_at=time.time())
    _save_state(st)
    print(f"📤 תוכנית מעודכנת נשלחה (message_id={mid}).")


if __name__ == "__main__":
    main()
