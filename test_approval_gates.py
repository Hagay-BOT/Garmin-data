# -*- coding: utf-8 -*-
"""בדיקות שער-אישור: שום פעולה חיצונית לא קורית בלי אישור מפורש.
ריצה: python -m pytest test_approval_gates.py -q   או   python test_approval_gates.py
"""
import sys, os, json, tempfile
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import push_week
import telegram_notify as tg


def _tmp_plan(approved):
    d = {"week_of": "2026-06-22", "phase": "Base", "macro_week": 1,
         "sessions": [{"date": "2026-06-22", "day": "", "type": "run", "subtype": "easy",
                       "name": "ריצה", "desc": "", "est_km": 6,
                       "steps": [{"kind": "interval", "seconds": 2000}]}]}
    if approved:
        d["approved"] = True
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(d, f, ensure_ascii=False)
    f.close()
    return Path(f.name)


def test_push_blocked_without_approval():
    """ללא approved=true → אסור להגיע ל-login/העלאה לגרמין."""
    plan_path = _tmp_plan(approved=False)
    created_path = Path(tempfile.NamedTemporaryFile(suffix=".json", delete=False).name)
    created_path.unlink()  # שלא קיים

    login_called = {"v": False}
    orig_login, orig_plan, orig_created, orig_argv = (
        push_week.login, push_week.PLAN_FILE, push_week.CREATED_FILE, sys.argv)

    def _spy_login():
        login_called["v"] = True
        raise AssertionError("login נקרא למרות שאין אישור!")

    try:
        push_week.login = _spy_login
        push_week.PLAN_FILE = plan_path
        push_week.CREATED_FILE = created_path
        sys.argv = ["push_week", "--push"]
        raised = False
        try:
            push_week.main()
        except SystemExit as e:
            raised = e.code != 0
        assert raised, "ציפינו ל-SystemExit עם קוד שגיאה"
        assert login_called["v"] is False, "login לא היה אמור להיקרא"
        assert not created_path.exists(), "created_workouts לא היה אמור להיכתב"
    finally:
        push_week.login, push_week.PLAN_FILE, push_week.CREATED_FILE, sys.argv = (
            orig_login, orig_plan, orig_created, orig_argv)
        plan_path.unlink(missing_ok=True)


def test_lock_plan_sets_approved_only_via_confirm():
    """lock_plan (נתיב האישור המפורש) הוא היחיד שמסמן approved=true."""
    import confirm_week
    plan_path = _tmp_plan(approved=False)
    orig = confirm_week.PLAN_FILE
    try:
        confirm_week.PLAN_FILE = plan_path
        before = json.loads(plan_path.read_text(encoding="utf-8"))
        assert "approved" not in before
        locked = confirm_week.lock_plan()
        assert locked["approved"] is True
        assert "approved_at" in locked
        on_disk = json.loads(plan_path.read_text(encoding="utf-8"))
        assert on_disk["approved"] is True
    finally:
        confirm_week.PLAN_FILE = orig
        plan_path.unlink(missing_ok=True)


def test_find_reply_keyword_mapping():
    os.environ["TELEGRAM_CHAT_ID"] = "999"
    cid = 999
    orig = tg.get_updates
    try:
        def make(text):
            return [{"message": {"chat": {"id": cid}, "date": 200, "text": text}}]
        for kw in ("כן", "yes", "1"):
            tg.get_updates = lambda offset=None, _t=kw: make(_t)
            assert tg.find_reply(1, 100) == "approve", kw
        for kw in ("לא", "no", "2"):
            tg.get_updates = lambda offset=None, _t=kw: make(_t)
            assert tg.find_reply(1, 100) == "reject", kw
        # הודעה לפני הזמן שנשלח → מתעלמים
        tg.get_updates = lambda offset=None: [{"message": {"chat": {"id": cid}, "date": 50, "text": "כן"}}]
        assert tg.find_reply(1, 100) is None
    finally:
        tg.get_updates = orig


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
