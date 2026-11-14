# -*- coding: utf-8 -*-
"""בדיקות message_nlu — בלי רשת: לקוח מזויף. בודק פענוח, סינון פלט לא-תקין, ונפילה לכללים."""
import json
import os
import types

import message_nlu as nlu
import telegram_intake
import body_state


class _Fake:
    def __init__(self, payload=None, stop="end_turn", raise_exc=None):
        self.payload, self.stop, self.raise_exc, self.calls = payload, stop, raise_exc, []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.raise_exc:
            raise self.raise_exc
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)
        return types.SimpleNamespace(stop_reason=self.stop,
                                     content=[types.SimpleNamespace(type="thinking", thinking=""),
                                              types.SimpleNamespace(type="text", text=text)])


def test_parses_and_validates():
    nlu._cache.clear()
    f = _Fake({"intent": "note", "body": [{"action": "open", "part": "foot"},
                                          {"action": "open", "part": "foot"},
                                          {"action": "open", "part": "elbow"}]})
    r = nlu.understand("יש לי כאב בכף רגל בגיד החיצוני", client=f)
    assert r == {"intent": "note", "body": [("open", "foot")]}, r
    kw = f.calls[0]
    assert kw["model"] == "claude-haiku-5-5" and kw["max_tokens"] >= 8192
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert "thinking" not in kw and "temperature" not in kw
    # מטמון: אותה הודעה לא נשלחת פעמיים
    nlu.understand("יש לי כאב בכף רגל בגיד החיצוני", client=f)
    assert len(f.calls) == 1


def test_failures_return_none():
    nlu._cache.clear()
    assert nlu.understand("", client=_Fake({})) is None
    assert nlu.understand("א", client=_Fake({"intent": "approve", "body": []})) is None
    assert nlu.understand("ב", client=_Fake("לא JSON")) is None
    assert nlu.understand("ג", client=_Fake({"intent": "note", "body": []}, stop="refusal")) is None
    assert nlu.understand("ד", client=_Fake(raise_exc=RuntimeError("429"))) is None


def test_disabled_without_key_and_callers_fall_back():
    nlu._cache.clear()
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        assert nlu.enabled() is False
        assert nlu.understand("תעביר את הריצה ליום שלישי") is None
        # הקוראים נופלים לכללים הישנים
        assert telegram_intake.classify("תעביר את הריצה ליום שלישי") == "revision"
        assert body_state.detect_smart("כאב ברך חזק היום") == [("open", "knee")]
    finally:
        if saved is not None:
            os.environ["ANTHROPIC_API_KEY"] = saved


def test_callers_use_model_when_available():
    nlu._cache.clear()
    # ניסוח שהכללים הקשיחים מפספסים: בלי אוצר-מילים של תוכנית, בלי מילת-כאב מוכרת
    msg = "אפשר לדחות את מה שתכננו למחר? הברכיים שלי לא משהו"
    assert telegram_intake.classify(msg) == "note" or True  # התנהגות הכללים לא נבדקת כאן
    nlu._cache[msg] = {"intent": "revision", "body": [("open", "knee")]}
    assert telegram_intake.classify(msg) == "revision"
    assert body_state.detect_smart(msg) == [("open", "knee")]
    # אישור נשאר דטרמיניסטי גם אם המודל היה אומר אחרת
    nlu._cache["אשר"] = {"intent": "note", "body": []}
    assert telegram_intake.classify("אשר") == "approval"
    nlu._cache.clear()


def main():
    for t in [test_parses_and_validates, test_failures_return_none,
              test_disabled_without_key_and_callers_fall_back,
              test_callers_use_model_when_available]:
        t()
        print(f"  ✓ {t.__name__}")
    print("\nOK — message NLU: parse, validation, fallback, deterministic approval.")


if __name__ == "__main__":
    main()
