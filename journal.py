"""
יומן מאמן — הערות חופשיות של הגיא ("היום עשיתי 3 ק"מ ולא 3.5, ישנתי גרוע, כאב ברך").
נרשמות ל-journal.json ומוזנות לניתוח אחרי-אימון ולסיכום השבועי כדי שהמאמן
יבין את ההקשר הסובייקטיבי ויתחשב בו (לא רק נתוני גרמין).
"""
import json
import datetime
from pathlib import Path

JOURNAL = Path(__file__).parent / "journal.json"


def _load() -> dict:
    try:
        d = json.loads(JOURNAL.read_text(encoding="utf-8"))
        d.setdefault("notes", [])
        d.setdefault("last_ts", 0)
        return d
    except Exception:
        return {"notes": [], "last_ts": 0}


def _save(d: dict) -> None:
    d["notes"] = d.get("notes", [])[-300:]
    JOURNAL.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


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
