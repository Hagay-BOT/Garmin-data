# -*- coding: utf-8 -*-
"""בדיקות לשכבת הבטיחות הדטרמיניסטית (safety.py).
ריצה: python -m pytest test_safety.py -q   או   python test_safety.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
import safety


def _run(d, subtype, est_km, secs=None):
    secs = secs if secs is not None else int(est_km * 360)
    return {"date": d, "day": "", "type": "run", "subtype": subtype,
            "name": f"ריצה {subtype}", "desc": "", "est_km": est_km,
            "steps": [{"kind": "interval", "seconds": secs}]}


def _plan(sessions):
    return {"week_of": "2026-06-22", "sessions": sessions}


def test_volume_clamp_to_15pct():
    # prev=20 → cap=max(23, 23)=23. תוכנית 26 ק"מ צריכה לרדת ל-~23.
    plan = _plan([_run("2026-06-22", "easy", 13), _run("2026-06-24", "easy", 13)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(plan, prev_week_km=20)
    total = sum(s["est_km"] for s in out["sessions"])
    assert total <= 23.1, total
    assert adj, "ציפינו להתאמת נפח"


def test_low_volume_floor():
    # prev=4 → cap=max(4.6, 7)=7. תוכנית 8 → 7.
    plan = _plan([_run("2026-06-22", "easy", 8)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(plan, prev_week_km=4)
    assert sum(s["est_km"] for s in out["sessions"]) <= 7.1
    assert adj


def test_deload_targets_minus_30():
    plan = _plan([_run("2026-06-22", "easy", 15), _run("2026-06-25", "easy", 15)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(
        plan, prev_week_km=30, macro={"deload": True})
    total = sum(s["est_km"] for s in out["sessions"])
    assert 20.5 <= total <= 21.5, total  # ~0.70*30 = 21
    assert any("deload" in a for a in adj)


def test_consecutive_hard_days_warn_not_modify():
    plan = _plan([_run("2026-06-22", "quality", 8), _run("2026-06-23", "long", 10)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(plan, prev_week_km=30)
    assert nr is True, "ימי איכות צמודים צריכים לדרוש אישור"
    assert any("צמוד" in w for w in warn)
    # המבנה לא שונה בשקט — הסוגים נשארו
    assert out["sessions"][0]["subtype"] == "quality"
    assert out["sessions"][1]["subtype"] == "long"


def test_acwr_escalation():
    plan = _plan([_run("2026-06-22", "easy", 6)])
    _, _, warn_mid, nr_mid = safety.clamp_and_validate_week_plan(plan, 6, acwr=1.6)
    assert any("1.6" in w for w in warn_mid) and nr_mid is False
    plan2 = _plan([_run("2026-06-22", "easy", 6)])
    _, _, warn_sev, nr_sev = safety.clamp_and_validate_week_plan(plan2, 6, acwr=1.75)
    assert nr_sev is True


def test_structural_reject_zero_second_step():
    bad = _plan([_run("2026-06-22", "easy", 6, secs=0)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(bad, prev_week_km=6)
    assert out is None
    assert any("INVALID" in w for w in warn)


def test_structural_reject_out_of_order_dates():
    bad = _plan([_run("2026-06-25", "easy", 6), _run("2026-06-22", "easy", 6)])
    out, _, warn, _ = safety.clamp_and_validate_week_plan(bad, prev_week_km=20)
    assert out is None
    assert any("ממוין" in w or "INVALID" in w for w in warn)


def test_zero_base_has_a_cap():
    # תוקן 14.11.2026: אחרי הפסקה (שבוע שעבר 0, כרוני 0) שבוע של 25 ק"מ עבר בלי תקרה
    plan = _plan([_run("2026-11-15", "easy", 8), _run("2026-11-17", "easy", 8),
                  _run("2026-11-19", "easy", 9)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(plan, prev_week_km=0)
    total = sum(s["est_km"] for s in out["sessions"])
    assert total <= safety.RESTART_WEEK_CAP_KM + 0.2, total
    assert any("בסיס אפס" in a for a in adj), adj
    # בסיס אפס + deload במאקרו: עדיין תקרת החזרה, לא «אין תקרה»
    plan = _plan([_run("2026-11-15", "easy", 10), _run("2026-11-17", "easy", 10)])
    out, adj, _, _ = safety.clamp_and_validate_week_plan(plan, prev_week_km=0,
                                                         macro={"deload": True})
    assert sum(s["est_km"] for s in out["sessions"]) <= safety.RESTART_WEEK_CAP_KM + 0.2


def test_rest_week_uses_chronic_anchor():
    # שבוע מנוחה אחד (0) עם בסיס כרוני 20: התקרה מהכרוני (23), לא «אין תקרה» ולא 12
    plan = _plan([_run("2026-11-15", "easy", 10), _run("2026-11-17", "easy", 10),
                  _run("2026-11-19", "easy", 10)])
    out, adj, _, _ = safety.clamp_and_validate_week_plan(plan, prev_week_km=0,
                                                         chronic_week_km=20)
    total = sum(s["est_km"] for s in out["sessions"])
    assert 22.5 <= total <= 23.2, total


def test_metadata_block():
    plan = _plan([_run("2026-06-22", "easy", 13), _run("2026-06-24", "easy", 13)])
    out, adj, warn, nr = safety.clamp_and_validate_week_plan(plan, prev_week_km=20)
    meta = safety.build_plan_metadata(adj, warn, nr)
    assert meta["approval_required"] is True
    assert meta["generated_by"] == "LLM"
    assert meta["safety_adjustments"] == adj


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except Exception:
            fails += 1
            print(f"[FAIL] {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
