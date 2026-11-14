# -*- coding: utf-8 -*-
"""בדיקות דגלי-מצב-גוף (T6) — זיהוי, מחזור-חיים, factors, prompt. עובד על state זמני."""
import body_state as bs
import store


def test_detect():
    assert bs.detect("הברך כואבת לי") == [("open", "knee")]
    assert bs.detect("כאב קרסול אחרי הריצה") == [("open", "ankle")]
    assert bs.detect("הברך עברה לי, הכל בסדר") == [("close", "knee")]
    assert bs.detect("אני חולה עם שפעת") == [("open", "illness")]
    # אזכור בלי כאב/החלמה → כלום (שמרני)
    assert bs.detect("רצתי והברך הרגישה חזקה") == []
    assert bs.detect("היה שבוע מעולה") == []


def test_lifecycle_and_injection():
    # שחזור בייט-לבייט: שמירה מחדש דרך store שינתה סיומות שורה, השאירה את הקובץ
    # «שונה» ב-git וחסמה את ה-pull --rebase של ship.py (14.11.2026).
    _path = store.BASE / "athlete_state.json"
    orig_bytes = _path.read_bytes() if _path.exists() else None
    try:
        store.save_athlete_state({"flags": {}})
        # פתיחה
        chg = bs.apply("כאב ברך חזק היום", today="2026-07-20")
        assert any("נפתח" in c for c in chg), chg
        assert "knee" in bs.active_flags()
        assert "injury" in bs.safety_factors()
        assert "ברך" in bs.prompt_line()
        # פתיחה חוזרת = idempotent (לא כפילות)
        assert bs.apply("שוב כאב ברך", today="2026-07-21") == []
        # דיווח חוזר נשמר בשקט: «שבוע בלי כאב» מדיד גם כשהדגל כבר פתוח
        assert bs.active_flags()["knee"]["last_reported"] == "2026-07-21"
        assert bs.pain_since("2026-07-21") is True
        assert bs.pain_since("2026-07-22") is False
        # מחלה מוסיפה illness
        bs.apply("אני חולה", today="2026-07-21")
        assert "illness" in bs.safety_factors()
        # סגירה
        chg = bs.apply("הברך עברה לי", today="2026-07-25")
        assert any("נסגר" in c for c in chg), chg
        assert "knee" not in bs.active_flags()
    finally:
        if orig_bytes is None:
            _path.unlink(missing_ok=True)
        else:
            _path.write_bytes(orig_bytes)


def main():
    test_detect()
    test_lifecycle_and_injection()
    print("OK — body-state flags: detect, open/close lifecycle, safety factors, prompt line.")


if __name__ == "__main__":
    main()
