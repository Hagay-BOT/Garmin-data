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


def test_easy_run_cap_and_shortfall():
    # T1: הרבה ימים עמוסים → נפח בפועל < יעד → דיווח ב-notes, לא אובדן שקט
    av = pg.parse_availability("שני עמוס, שלישי עמוס, רביעי עמוס, חמישי עמוס")
    m = dict(MACRO, target_km=35, long_run_km=12)
    p = pg.generate(SUNDAY, m, ["A", "B"], av)
    assert "נפח בפועל" in p["notes"], f"חייב דיווח אובדן-נפח: {p['notes']}"
    # T1: אף ריצה-קלה לא חורגת מ-8 ק"מ
    for r in _by(p, "run"):
        if r["subtype"] == "easy":
            assert r["est_km"] <= 8.0, f"ריצה קלה מעל התקרה: {r['est_km']}"


def test_preference_moves_long():
    # T2: "מעדיף לונג בשישי" → הלונג עובר לשישי (weekday 4)
    av = pg.parse_availability("מעדיף לונג בשישי")
    assert av["prefer"].get("long") == 4, av
    p = pg.generate(SUNDAY, MACRO, ["A", "B"], av)
    longs = [r for r in _by(p, "run") if r["subtype"] == "long"]
    assert longs and _wd(longs[0]["date"]) == 4, "לונג חייב לעבור לשישי"
    # העדפה ליום עמוס לא חלה (עומס גובר)
    av2 = pg.parse_availability("שישי אני עמוס, מעדיף לונג בשישי")
    assert "long" not in av2["prefer"], av2
    # טקסט בלי העדפה מפורשת — כלום
    assert pg.parse_availability("היה שבוע טוב")["prefer"] == {}


def test_gate_week_builds_5k_tt():
    # T10: שבוע-שער → האיכות היא מבחן 5K TT קונקרטי
    m = dict(MACRO, gate=True, week_num=8)
    p = pg.generate(SUNDAY, m, ["A", "B"])
    q = [s for s in _by(p, "run") if s["subtype"] == "quality"][0]
    assert "5K Time-Trial" in q["name"], q
    assert "5 ק\"מ במאמץ" in q["desc"], q["desc"]
    # שבוע רגיל → לא TT
    p2 = pg.generate(SUNDAY, dict(MACRO, gate=False), ["A", "B"])
    q2 = [s for s in _by(p2, "run") if s["subtype"] == "quality"][0]
    assert "Time-Trial" not in q2["name"], q2


def test_return_mode_week():
    # חזרה לריצה: 3 אימוני הליכה-ריצה, בלי איכות ובלי לונג, ימים לא צמודים, כוח BW
    p = pg.generate_return(SUNDAY, stage=1, days_per_week=3)
    runs, strength = _by(p, "run"), _by(p, "strength")
    assert len(runs) == 3, runs
    assert all(r["subtype"] == "easy" for r in runs), "אין איכות ואין לונג במצב חזרה"
    wds = sorted((_wd(r["date"]) + 1) % 7 for r in runs)   # ראשון=0
    assert all(b - a >= 2 for a, b in zip(wds, wds[1:])), f"ימים צמודים: {wds}"
    assert [s["key"] for s in strength] == ["BW", "BW"], strength
    st = runs[0]["steps"]
    assert st[0]["kind"] == "warmup" and st[-1]["kind"] == "cooldown"
    assert sum(1 for x in st if x["kind"] == "interval") == 8
    assert sum(x["seconds"] for x in st if x["kind"] == "interval") == 8 * 60
    assert sum(r["est_km"] for r in runs) <= 12, "שבוע ראשון בתוך תקרת בסיס-אפס"
    assert "שלב 1" in runs[0]["name"]
    # יום עמוס לא מקבל אימון
    av = pg.parse_availability("ראשון אני עמוס")
    p2 = pg.generate_return(SUNDAY, 1, 3, av)
    assert all(_wd(s["date"]) != 6 for s in p2["sessions"])
    assert len(_by(p2, "run")) == 3
    # השלב האחרון = ריצה רצופה, בלי הליכה באמצע
    last = pg.generate_return(SUNDAY, pg.RETURN_LAST_STAGE, 3)
    kinds = [x["kind"] for x in _by(last, "run")[0]["steps"]]
    assert kinds == ["warmup", "interval", "cooldown"], kinds


def test_return_stage_progression():
    # מתקדמים רק אחרי שבוע שבוצע ובלי כאב
    assert pg.next_return_stage(1, 3, 3, False)[0] == 2
    assert pg.next_return_stage(1, 2, 3, False)[0] == 2      # 2 מתוך 3 מספיק
    assert pg.next_return_stage(2, 1, 3, False)[0] == 2      # לא בוצע → חוזרים
    assert pg.next_return_stage(3, 3, 3, True)[0] == 2       # כאב → שלב אחורה
    assert pg.next_return_stage(1, 3, 3, True)[0] == 1       # לא מתחת ל-1
    assert pg.next_return_stage(1, 0, 0, False)[0] == 1      # שבוע ראשון
    assert pg.next_return_stage(pg.RETURN_LAST_STAGE, 3, 3, False)[0] == pg.RETURN_LAST_STAGE
    # זמן הריצה בשבוע לא קופץ ביותר מ-40% בין שלבים עוקבים
    tot = [r * n for r, w, n in pg.RETURN_STAGES]
    assert all(b <= a * 1.4 for a, b in zip(tot, tot[1:])), tot


def test_return_plan_passes_materialize_and_safety():
    # מקצה לקצה: המחולל → materialize → שכבת הבטיחות, מבסיס אפס, בלי קיצוץ
    import coach, safety
    full = coach.materialize_week_plan(pg.generate_return(SUNDAY, 1, 3))
    assert full["goal_race"].startswith("חזרה לכושר")
    assert any(st["kind"] == "recovery" for st in full["sessions"][0]["steps"])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(full, prev_week_km=0)
    assert out is not None, warn
    assert adj == [], f"שבוע חזרה לא אמור להיחתך: {adj}"


def main():
    for t in [test_return_mode_week, test_return_stage_progression,
              test_return_plan_passes_materialize_and_safety,
              test_basic_structure, test_busy_saturday_moves_long,
              test_availability_parsing, test_deload_and_rotation_continuity,
              test_easy_run_cap_and_shortfall, test_preference_moves_long,
              test_gate_week_builds_5k_tt]:
        t()
        print(f"  ✓ {t.__name__}")
    print("\nOK — plan generator rules verified.")


if __name__ == "__main__":
    main()
