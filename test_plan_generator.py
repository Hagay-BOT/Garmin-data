# -*- coding: utf-8 -*-
"""בדיקות המחולל הדטרמיניסטי (M3.3+M10) — כללי-המבנה של הגיא כ-assertions."""
import datetime
import plan_generator as pg

SUNDAY = datetime.date(2026, 7, 12)  # ראשון
MACRO = {"week_num": 5, "phase": "Base", "target_km": 31, "long_run_km": 12,
         "quality": "1× Threshold (4:50) + strides", "deload": False}


def _by(plan, typ):
    return [s for s in plan["sessions"] if s["type"] == typ]


def _wd(iso):
    return datetime.date.fromisoformat(iso).weekday()


def test_basic_structure():
    p = pg.generate(SUNDAY, MACRO, last_strength_seq=["A", "B", "C", "A", "B"])
    runs, strength = _by(p, "run"), _by(p, "strength")
    # שבת = לונג
    longs = [r for r in runs if r["subtype"] == "long"]
    assert len(longs) == 1 and _wd(longs[0]["date"]) == 5, "הלונג חייב בשבת"
    assert longs[0]["est_km"] <= 12, "תקרת לונג"
    # איכות ≥48ש' מהלונג
    q = [r for r in runs if r["subtype"] == "quality"][0]
    assert (5 - _wd(q["date"])) % 7 >= 2, "איכות ≥48ש' לפני הלונג"
    # כוח: A×2, B×2, C×1
    keys = sorted(s["key"] for s in strength)
    assert keys == ["A", "A", "B", "B", "C"], f"פיצול כוח שגוי: {keys}"
    # המשכיות: שבוע שעבר נגמר ב-B → השבוע מתחיל ב-A
    uppers = [s for s in strength if s["key"] in "AB"]
    first_upper = min(uppers, key=lambda s: s["date"])
    assert first_upper["key"] == "A", "רוטציה חייבת להמשיך מהאימון האחרון"
    # התאוששות אחרי רגליים
    legs = [s for s in strength if s["key"] == "C"][0]
    day_after = (datetime.date.fromisoformat(legs["date"])
                 + datetime.timedelta(days=1)).isoformat()
    rec = [r for r in runs if r["date"] == day_after]
    assert rec and "התאוששות" in rec[0]["name"], "אחרי רגליים חייבת התאוששות Z1"
    # C לא יום-לפני-הלונג
    assert (5 - _wd(legs["date"])) % 7 >= 2, "C רחוק מהלונג"
    # נפח לא נחתך: סך הריצות ~target
    total = sum(r["est_km"] for r in runs)
    assert abs(total - MACRO["target_km"]) <= 3, f"נפח {total} רחוק מיעד {MACRO['target_km']}"


def test_busy_saturday_moves_long():
    av = pg.parse_availability("בשבת אני בנסיעה")
    assert av["busy_days"] == [5], av
    p = pg.generate(SUNDAY, MACRO, ["A", "B"], av)
    longs = [r for r in _by(p, "run") if r["subtype"] == "long"]
    assert longs and _wd(longs[0]["date"]) == 4, "שבת עמוסה → לונג בשישי"
    assert all(_wd(s["date"]) != 5 for s in p["sessions"]), "אין אימונים ביום עמוס"


def test_availability_parsing():
    av = pg.parse_availability("שלישי אני עמוס בעבודה וחמישי לא אוכל להתאמן")
    assert set(av["busy_days"]) == {1, 3}, av
    # הערה בלי ימים/עומס → כלום
    assert pg.parse_availability("מרגיש מצוין השבוע")["busy_days"] == []
    # יום מוזכר בלי מילת-עומס → לא עמוס (שמרני)
    assert pg.parse_availability("בשלישי רצתי מעולה")["busy_days"] == []


def test_deload_and_rotation_continuity():
    m = dict(MACRO, deload=True, target_km=23, long_run_km=8)
    p = pg.generate(SUNDAY, m, last_strength_seq=["B", "A", "C", "B", "A"])
    uppers = [s for s in _by(p, "strength") if s["key"] in "AB"]
    assert min(uppers, key=lambda s: s["date"])["key"] == "B", "אחרי A מתחילים ב-B"
    total = sum(r["est_km"] for r in _by(p, "run"))
    assert total <= 26, f"deload חייב נפח נמוך ({total})"


def main():
    for t in [test_basic_structure, test_busy_saturday_moves_long,
              test_availability_parsing, test_deload_and_rotation_continuity]:
        t()
        print(f"  ✓ {t.__name__}")
    print("\nOK — plan generator rules verified.")


if __name__ == "__main__":
    main()
