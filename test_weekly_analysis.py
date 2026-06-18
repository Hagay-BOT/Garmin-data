"""בדיקות יחידה לשלב 1 של הסיכום השבועי (weekly_analysis.py)."""
import weekly_analysis as wa


MACRO_BUILD = {
    "status": "active", "week_num": 7, "phase": "Build", "target_km": 50.0,
    "long_run_km": 12.0, "deload": False, "gate": False,
    "race": {"distance_km": 15.0, "goal_pace": "5:20/km"},
}


def _metrics(**over):
    m = {
        "load": {"acwr": 1.0, "ramp_rate_4w": 5, "tsb": 2, "ctl": 40, "atl": 40},
        "monotony": {"monotony": 1.4},
        "zones": {"available": True, "easy_pct": 82, "z3_pct": 8, "hard_pct": 18},
        "last_week": {"count": 4, "total_km": 40, "runs": [{"dominant_zone": 4}]},
        "fitness_4week": {"vdot": 40.0, "vdot_basis": "5K", "threshold_pace": "5:00/ק\"מ"},
        "strength": {"session_count": 5, "days_since_last": 1},
        "macro": MACRO_BUILD,
        "red_flags": [],
    }
    m.update(over)
    return m


def test_required_vdot_for_race():
    r = wa.required_vdot_for_race(MACRO_BUILD)
    assert r["available"] and r["required_vdot"] > 0


def test_parse_pace():
    assert wa.parse_pace_to_sec("5:20/km") == 320
    assert wa.parse_pace_to_sec("5:00") == 300
    assert wa.parse_pace_to_sec(None) is None


def test_zone_no_mans_land_flag():
    z = wa.zone_balance_verdict({"available": True, "easy_pct": 70, "z3_pct": 22, "hard_pct": 25})
    assert z["no_mans_land"] is True
    z2 = wa.zone_balance_verdict({"available": True, "easy_pct": 82, "z3_pct": 8, "hard_pct": 16})
    assert z2["no_mans_land"] is False


def test_threshold_gap_positive_when_below():
    t = wa.threshold_progress(_metrics(fitness_4week={"vdot": 35.0}), MACRO_BUILD)
    assert t["vdot_gap"] > 0 and t["on_track"] is False


def test_compliance_quality_done():
    c = wa.compliance_detailed({"available": True, "compliance_level": "מלא"},
                               _metrics(last_week={"count": 4, "total_km": 40,
                                                   "runs": [{"dominant_zone": 4}]}))
    assert c["quality_done"] is True


def test_conflict_detected_low_compliance():
    conf = wa.detect_macro_reality_conflict(
        _metrics(last_week={"count": 2, "total_km": 20, "runs": []}),
        MACRO_BUILD, {"compliance_level": "נמוך"})
    assert conf["conflict"] is True
    assert conf["conservative_target_km"] < conf["macro_target_km"]


def test_no_conflict_when_on_track():
    conf = wa.detect_macro_reality_conflict(
        _metrics(), MACRO_BUILD, {"compliance_level": "מלא"})
    assert conf["conflict"] is False


def test_red_flag_wins_priority():
    m = _metrics(red_flags=[{"severity": "🔴", "flag": "ACWR spike", "detail": "1.8"}])
    a = wa.build_weekly_analysis(m, {"compliance_level": "מלא"})
    assert a["priority"]["headline_domain"] == "red_flag"


def test_threshold_leads_in_build_when_behind():
    m = _metrics(fitness_4week={"vdot": 34.0})  # well below required
    a = wa.build_weekly_analysis(m, {"compliance_level": "מלא"})
    assert a["priority"]["headline_domain"] == "threshold"


def test_all_good_defaults_to_on_track():
    m = _metrics(fitness_4week={"vdot": 60.0})  # above required
    a = wa.build_weekly_analysis(m, {"compliance_level": "מלא"})
    assert a["priority"]["headline_domain"] == "on_track"
