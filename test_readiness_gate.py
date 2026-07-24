# -*- coding: utf-8 -*-
"""בדיקות שער-המוכנות (T5) — מתי מדגמן ומתי שקט."""
import readiness_gate as rg

QUALITY = {"subtype": "quality", "name": "🏃 סף 4:50"}
LONG = {"subtype": "long", "name": "🏃 לונג 10"}
EASY = {"subtype": "easy", "name": "🏃 קל 4"}


def main():
    # יום-איכות + שינה גרועה → דגל
    f, r = rg.evaluate(QUALITY, {"sleep_score": 35, "body_battery_morning": 80})
    assert f and "ציון-שינה 35" in r, (f, r)
    # יום-איכות + סוללה נמוכה → דגל
    f, r = rg.evaluate(QUALITY, {"sleep_score": 80, "body_battery_morning": 20})
    assert f and "סוללת-גוף 20" in r, (f, r)
    # לונג + שניהם נמוכים → דגל עם שתי סיבות
    f, r = rg.evaluate(LONG, {"sleep_score": 40, "body_battery_morning": 25})
    assert f and "·" in r, r
    # יום-איכות + מוכנות טובה → שקט
    assert rg.evaluate(QUALITY, {"sleep_score": 85, "body_battery_morning": 90})[0] is False
    # יום-קל + שינה גרועה → שקט (רק איכות/לונג מגויטים)
    assert rg.evaluate(EASY, {"sleep_score": 30, "body_battery_morning": 20})[0] is False
    # חסר-נתונים → שקט (שמרני)
    assert rg.evaluate(QUALITY, {})[0] is False
    assert rg.evaluate(QUALITY, None)[0] is False
    assert rg.evaluate(None, {"sleep_score": 20})[0] is False
    # ציון 0 = "לא סונכרן" → לא דגל
    assert rg.evaluate(QUALITY, {"sleep_score": 0, "body_battery_morning": 0})[0] is False
    print("OK — readiness gate: flags quality/long on low readiness, silent otherwise.")


if __name__ == "__main__":
    main()
