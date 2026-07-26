# -*- coding: utf-8 -*-
"""
body_state.py — דגלי-מצב-גוף מתמשכים (T6).

הבעיה: "כאב ברך" ביומן נשכח אחרי שבוע; המחולל, הפרומטים והבטיחות לא זכרו אותו.
הפתרון: דגלים מתמשכים ב-athlete_state.json שנפתחים ונסגרים בהודעת-טלגרם טבעית,
דטרמיניסטית (בלי LLM), ומוזרקים לתכנון, לנרטיב ולשכבת-הבטיחות עד שהגיא סוגר אותם.

חלקי-גוף מזוהים → מפתח פנימי (תואם safety.DEEP_DELOAD_FACTORS: injury):
  ברך/קרסול/שוק/גב/ירך → part; מחלה/חולה/שפעת → 'illness'.
"""
import datetime
import re

import store

# חלק-גוף/מצב → מפתח דגל. **דפוסי-regex** (לא substring) כדי לתפוס נטיות ורבים:
# "ברכיים"/"הברך", "קרסוליים", "כף רגל", "גיד" — כולם פספסו ב-26.07 והשאירו
# את הגיא בלי מענה. הרחבה מבוססת-מציאות, לא ניחוש.
_PARTS = {
    r"ברכ(י?ים|יי|ה)?|ברך": "knee",
    r"קרסול(י?ים|יי)?": "ankle",
    r"שוק(י?ים|יי)?|שוקי": "shin",
    r"גב\b|גב ה|בגב": "back",
    r"ירכ(י?ים|יי|יים)?|ירך": "hip",
    r"אכילס|גיד השריר|גיד אכילס": "achilles",
    r"כף רגל|כפות רגל|פלנטר|פאשיה|גיד החיצוני|גיד(ים)? ברגל|כף הרגל": "foot",
    r"מחל(ה|ות)|חול[הים]|שפעת|הצטננ|וירוס": "illness",
}
_LABELS_HE = {"knee": "ברך", "ankle": "קרסול", "shin": "שוק", "back": "גב",
              "hip": "ירך", "achilles": "אכילס", "foot": "כף רגל", "illness": "מחלה"}
# ביטויי-כאב טבעיים. "גומרות אותי" / "הורגות אותי" פספסו ב-26.07 — נוספו.
_PAIN_WORDS = (r"(כואב|כאב|פצוע|פציעה|תפוס|נתקע|חולה|מחלה|שפעת|הצטננ|נפוח|"
               r"גומר(ות|ים|ת)? אותי|הורג(ות|ים|ת)? אותי|מציק|שורף|רגישות|"
               r"נוקשה|לא בסדר|בעיה ב|מרגיש את ה)")  # לא "רגיש" חשוף — נבלע ב"הרגישו"
_HEAL_WORDS = r"(עבר[הו]? לי|בסדר|נרפא|החלי[םמ]|כבר לא כואב|טוב יותר|נעלמ?|הבריא|החלמתי)"


def detect(text: str) -> list[tuple[str, str]]:
    """טקסט → [(action, part)], action ∈ {'open','close'}. שמרני: רק במשפט עם
    חלק-גוף מוכר + מילת-כאב (פתיחה) או מילת-החלמה (סגירה)."""
    out = []
    if not text:
        return out
    for sentence in re.split(r"[.,;\n]| ו(?=[א-ת])", text):
        parts = {p for pat, p in _PARTS.items() if re.search(pat, sentence)}
        if not parts:
            continue
        if re.search(_HEAL_WORDS, sentence):
            out += [("close", p) for p in parts]
        elif re.search(_PAIN_WORDS, sentence):
            out += [("open", p) for p in parts]
    return out


def apply(text: str, today: str | None = None) -> list[str]:
    """מעדכן את athlete_state לפי הטקסט. מחזיר רשימת-שינויים לתצוגה. דטרמיניסטי."""
    actions = detect(text)
    if not actions:
        return []
    today = today or datetime.date.today().isoformat()
    st = store.load_athlete_state()
    flags = st["flags"]
    changes = []
    for action, part in actions:
        if action == "open" and part not in flags:
            flags[part] = {"since": today, "note": text.strip()[:120]}
            changes.append(f"🚩 נפתח דגל: {part}")
        elif action == "close" and part in flags:
            del flags[part]
            changes.append(f"✅ נסגר דגל: {part}")
    if changes:
        store.save_athlete_state(st)
    return changes


def active_flags() -> dict:
    return store.load_athlete_state()["flags"]


def safety_factors() -> set:
    """מפתחות ל-safety.factors — פציעה/מחלה מפעילות deload עמוק אם צריך."""
    flags = active_flags()
    fac = set()
    if any(p == "illness" for p in flags):
        fac.add("illness")
    if any(p in ("knee", "ankle", "shin", "hip", "achilles", "back") for p in flags):
        fac.add("injury")
    return fac


def prompt_line() -> str:
    """שורה לפרומטים (שבועי+פוסט) — ריק אם אין דגלים פעילים."""
    flags = active_flags()
    if not flags:
        return ""
    items = ", ".join(f"{_LABELS_HE.get(p, p)} (מאז {d.get('since','?')})"
                      for p, d in flags.items())
    return (f"⚠️ דגלי-גוף פעילים: {items}. התחשב בהם — הימנע מעומס על האזור, "
            f"שקול הקלה; אל תמליץ איכות/עומס שמסכן אותם עד שהדגל נסגר.")
