# -*- coding: utf-8 -*-
"""בדיקות למסווג הודעות-הטלגרם (M6) — הקטגוריות שמונעות הפעלת-LLM שגויה."""
import telegram_intake as ti

CASES = [
    # (text, awaiting_choice, expected)
    ("אשר", False, "approval"),
    ("כן", False, "approval"),
    ("👍", False, "approval"),
    ("מעולה תודה", False, "approval"),          # starts with approve word
    ("A", True, "choice"),
    ("ב", True, "choice"),
    ("A", False, "note"),                        # לא ממתינים לבחירה → לא choice
    # revisions — plan vocabulary
    ("שישי 5 ק\"מ, שבת 10", False, "revision"),
    ("חמישי בלי ריצה", False, "revision"),
    ("תוסיף strides לטמפו", False, "revision"),
    ("תקצר את הלונג", False, "revision"),
    ("ביום שלישי רק כוח", False, "revision"),
    # notes — the live-bug class: journal notes must NOT trigger the revise LLM
    ("ישנתי ממש גרוע וכאבה הברך", False, "note"),
    ("הייתי עמוס בעבודה ולא הספקתי", False, "note"),
    ("האימון הרגיש מצוין היום", False, "note"),
    ("", False, "note"),
]


def main():
    failed = 0
    for text, awaiting, expected in CASES:
        got = ti.classify(text, awaiting_choice=awaiting)
        ok = got == expected
        failed += (not ok)
        print(f"  {'✓' if ok else '✗ FAIL'} {text[:32]!r} → {got}"
              + ("" if ok else f" (expected {expected})"))
    assert not failed, f"{failed} classification cases failed"
    print(f"\nOK — {len(CASES)} intake classification cases passed.")


if __name__ == "__main__":
    main()
