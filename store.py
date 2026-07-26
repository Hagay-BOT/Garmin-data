# -*- coding: utf-8 -*-
"""
store.py — שכבת הגישה היחידה לקבצי ה-state (M2.2).

כל קריאה/כתיבה של קובץ-מצב עוברת כאן: ברירות-מחדל עקביות, קידוד אחיד,
ולידציה בסיסית, ואטומיות בכתיבה (tmp+replace — כתיבה שנקטעת לא משאירה
קובץ חצי-כתוב). מחסל את ה-drift של 40+ נקודות `json.load(open(...))` פזורות.

שימוש:
    import store
    plan = store.load_week_plan()
    store.save_week_plan(plan)
"""
import json
import os
import tempfile
from pathlib import Path

BASE = Path(__file__).parent

# ── ליבה ─────────────────────────────────────────────────────────────────────

def _read(name: str, default):
    """קריאת JSON עם ברירת-מחדל בטוחה. קובץ חסר/פגום → default (לא קריסה)."""
    p = BASE / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"⚠️ store: {name} פגום ({e}) — משתמש בברירת-מחדל.")
        return default


def _write(name: str, data) -> None:
    """כתיבה אטומית: tmp באותה תיקייה + os.replace (rename אטומי)."""
    p = BASE / name
    fd, tmp = tempfile.mkstemp(dir=BASE, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── week_plan.json — התוכנית השבועית (מקור-אמת לגרמין+יומן) ──────────────────

def load_week_plan() -> dict:
    plan = _read("week_plan.json", {"sessions": []})
    # M9.3: ולידציית-מבנה רועשת — סשן חסר-שדות מתפשט בשקט לגרמין/יומן/פרומטים.
    bad = [i for i, s in enumerate(plan.get("sessions", []))
           if not (isinstance(s, dict) and s.get("date") and s.get("type") in ("run", "strength")
                   and (s.get("type") != "strength" or s.get("key") in ("A", "B", "C")))]
    if bad:
        print(f"🔴 store: week_plan.json — sessions פגומים באינדקסים {bad} (חסר date/type/key)!")
    return plan


def save_week_plan(plan: dict) -> None:
    assert isinstance(plan.get("sessions"), list), "week_plan חייב sessions כרשימה"
    _write("week_plan.json", plan)


# ── journal.json — הערות המתאמן ──────────────────────────────────────────────

def load_journal() -> dict:
    d = _read("journal.json", {})
    d.setdefault("notes", [])
    d.setdefault("last_ts", 0)
    return d


def save_journal(d: dict) -> None:
    d["notes"] = d.get("notes", [])[-300:]
    _write("journal.json", d)


# ── weekly_state.json — סטייט לולאת האישור/עריכה השבועית ─────────────────────

def load_weekly_state() -> dict:
    return _read("weekly_state.json", {})


def save_weekly_state(s: dict) -> None:
    _write("weekly_state.json", s)


# ── created_workouts.json — אימונים שנוצרו בגרמין (dedup סנכרון) ─────────────

def load_created() -> list:
    d = _read("created_workouts.json", [])
    return d if isinstance(d, list) else []


def save_created(items: list) -> None:
    _write("created_workouts.json", items)


# ── coach_history.json — היסטוריית סיכומים שבועיים ───────────────────────────

def load_history() -> list:
    d = _read("coach_history.json", [])
    return d if isinstance(d, list) else d.get("weeks", [])


# ── data.json — נתוני גרמין (קריאה-בלבד מחוץ ל-fetch_garmin) ─────────────────

def load_data() -> dict:
    return _read("data.json", {"activities": [], "daily": {}})


# ── athlete_state.json — דגלי-גוף מתמשכים (T6): ברך/קרסול/מחלה ───────────────

def load_athlete_state() -> dict:
    d = _read("athlete_state.json", {})
    d.setdefault("flags", {})   # {"knee": {"since": "YYYY-MM-DD", "note": "..."}}
    return d


def save_athlete_state(d: dict) -> None:
    _write("athlete_state.json", d)
