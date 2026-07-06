"""
יומן מאמן — הערות חופשיות של הגיא ("היום עשיתי 3 ק"מ ולא 3.5, ישנתי גרוע, כאב ברך").
נרשמות ל-journal.json ומוזנות לניתוח אחרי-אימון ולסיכום השבועי כדי שהמאמן
יבין את ההקשר הסובייקטיבי ויתחשב בו (לא רק נתוני גרמין).
"""
import datetime
import store

# גישת ה-state דרך store.py (M2.2) — כתיבה אטומית + ברירות-מחדל במקום אחד.
_load = store.load_journal
_save = store.save_journal


def add_note(text: str, when: str | None = None) -> None:
    """מוסיף הערה (תאריך + טקסט)."""
    d = _load()
    d["notes"].append({"date": when or datetime.date.today().isoformat(),
                       "text": (text or "").strip()})
    _save(d)


def recent_notes_md(days: int = 10) -> str:
    """הערות מ-N הימים האחרונים כטקסט ל-prompt."""
    d = _load()
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    rec = [n for n in d.get("notes", []) if str(n.get("date", "")) >= cutoff]
    if not rec:
        return "אין הערות מהמתאמן בתקופה זו."
    return "\n".join(f"- {n['date']}: {n['text']}" for n in rec)


def todays_note_md() -> str:
    """הערות של היום (לניתוח אחרי-אימון)."""
    today = datetime.date.today().isoformat()
    d = _load()
    rec = [n["text"] for n in d.get("notes", []) if n.get("date") == today]
    return " · ".join(rec) if rec else ""
