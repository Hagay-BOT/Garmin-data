# -*- coding: utf-8 -*-
"""
telegram_intake.py — מסווג הודעות-טלגרם משותף (M6).

בעיה שנפתרת: מספר קולטנים קוראים את אותו צ'אט, וכל אחד פירש כל טקסט כשלו —
הערת-יומן ("כאב ברך") שנשלחה בראשון הופעלה כבקשת-עריכת-תוכנית (קריאת LLM
ושכתוב מיותרים), ו"אשר" זוהם את היומן כרעש.

הפתרון: פונקציית classify אחת שכל הקולטנים חולקים. דטרמיניסטית, בדיקה.

קטגוריות:
  approval — מילת אישור ("אשר", "כן", 👍)
  choice   — בחירת וריאנט A/B בשער-הכרעה
  revision — בקשת שינוי-תוכנית (מכילה אוצר-מילים של תוכנית: ימים/ק"מ/סוגי אימון)
  note     — כל השאר → הערת-יומן (ברירת המחדל הבטוחה)
"""
import re

APPROVE_WORDS = {"אשר", "אשרר", "כן", "מאשר", "אישור", "מעולה", "אוקיי",
                 "ok", "okay", "yes", "👍", "✅"}

CHOICE_WORDS = {"a", "b", "א", "ב", "1", "2"}

# אוצר-מילים שמעיד על בקשת שינוי-תוכנית. הערות-יומן טיפוסיות ("ישנתי גרוע",
# "כאב ברך", "הייתי עמוס") לא מכילות אף אחד מאלה — ולכן יפלו ל-note.
_PLAN_VOCAB = re.compile(
    r"ק\"?מ|קמ\b|לונג|טמפו|אינטרוול|strides|סטרייד|כוח [ABCאבג]|"
    r"הקל|תקל|להקל|תוריד עומס|שבוע קל|"
    r"בלי ריצה|בלי אימון|תוסיף|תוריד|תשנה|תחליף|תקצר|תאריך|תעביר|"
    r"ביום (ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת)|"
    r"(ראשון|שני|שלישי|רביעי|חמישי|שישי|שבת) (בלי|רק|נפח|קל|\d)",
    re.IGNORECASE)


def is_approval(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in APPROVE_WORDS or any(t == w or t.startswith(w + " ")
                                     for w in APPROVE_WORDS)


def classify(text: str, awaiting_choice: bool = False) -> str:
    """סיווג הודעה יחידה. awaiting_choice=True רק כששער-הכרעה A/B פתוח."""
    t = (text or "").strip()
    if not t:
        return "note"
    if awaiting_choice and t.lower() in CHOICE_WORDS:
        return "choice"
    if is_approval(t):
        return "approval"
    if _PLAN_VOCAB.search(t):
        return "revision"
    return "note"
