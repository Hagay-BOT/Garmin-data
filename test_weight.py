# -*- coding: utf-8 -*-
"""בדיקות מעקב המשקל — פענוח תשובות גרמין במבנים הידועים, מיזוג וסיכום."""
import weight


def test_parse_daily_summaries_grams():
    resp = {"dailyWeightSummaries": [
        {"summaryDate": "2026-11-10", "latestWeight": {"weight": 80500.0, "bodyFat": 22.4,
                                                       "calendarDate": "2026-11-10"}},
        {"summaryDate": "2026-11-12", "allWeightMetrics": [
            {"weight": 80300.0, "calendarDate": "2026-11-12"},
            {"weight": 80100.0, "calendarDate": "2026-11-12"}]},
    ]}
    w = weight.parse_weigh_ins(resp)
    assert w["2026-11-10"] == {"kg": 80.5, "body_fat": 22.4}, w
    assert w["2026-11-12"]["kg"] == 80.1, "שקילה אחרונה ביום גוברת"


def test_parse_date_weight_list_and_flat():
    ms = 1794441600000  # 2026-11-12 UTC
    w = weight.parse_weigh_ins({"dateWeightList": [{"date": ms, "weight": 79900.0}]})
    assert list(w.values())[0]["kg"] == 79.9 and list(w)[0].startswith("2026-11-1"), w
    w2 = weight.parse_weigh_ins([{"calendarDate": "2026-11-13", "weight": 80.2}])
    assert w2 == {"2026-11-13": {"kg": 80.2, "body_fat": None}}, w2


def test_parse_rejects_garbage():
    assert weight.parse_weigh_ins(None) == {}
    assert weight.parse_weigh_ins({}) == {}
    bad = {"dailyWeightSummaries": [{"summaryDate": "2026-11-10", "latestWeight": {"weight": None}},
                                    {"summaryDate": "2026-11-11", "latestWeight": {"weight": 5.0}},
                                    {"summaryDate": "", "latestWeight": {"weight": 80000}}]}
    assert weight.parse_weigh_ins(bad) == {}


def test_merge_and_summary():
    old = {"2026-11-01": {"kg": 81.0, "body_fat": None}, "2026-07-01": {"kg": 74.0, "body_fat": None}}
    new = {"2026-11-01": {"kg": 80.8, "body_fat": None}, "2026-11-14": {"kg": 80.0, "body_fat": None}}
    m = weight.merge(old, new)
    assert list(m) == ["2026-07-01", "2026-11-01", "2026-11-14"] and m["2026-11-01"]["kg"] == 80.8
    s = weight.summary(m, since="2026-11-01")
    assert s["first_kg"] == 80.8 and s["last_kg"] == 80.0 and s["change_kg"] == -0.8, s
    assert weight.summary({}, "2026-11-01") == {"available": False}


def main():
    for t in [test_parse_daily_summaries_grams, test_parse_date_weight_list_and_flat,
              test_parse_rejects_garbage, test_merge_and_summary]:
        t()
        print(f"  ✓ {t.__name__}")
    print("\nOK — weight parsing, merge and summary verified.")


if __name__ == "__main__":
    main()
