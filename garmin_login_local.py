# -*- coding: utf-8 -*-
"""
garmin_login_local.py — התחברות חד-פעמית לגרמין מהמחשב של הגיא (14.11.2026).

למה: ההתחברות בסיסמה מתוך GitHub Actions נדחית ב-401 גם כשהסיסמה נכונה (גרמין חוסם
לעיתים התחברות SSO משרתים). הפתרון: מתחברים פעם אחת מהבית, שומרים את אסימוני-הגישה,
והתהליכים ב-GitHub משתמשים בהם (GARMINTOKENS) במקום בסיסמה.

הרצה (בטרמינל רגיל, לא דרך Claude):
    python garmin_login_local.py
הסיסמה מוקלדת בטרמינל ולא נשמרת בשום מקום. האסימונים נכתבים לקובץ מחוץ לריפו.
"""
import getpass
import sys
from pathlib import Path

OUT = Path.home() / ".garmin_tokens.json"


def main() -> int:
    from garminconnect import Garmin
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password (hidden): ")
    try:
        g = Garmin(email, password, prompt_mfa=lambda: input("MFA code (from email/app): ").strip())
        g.login()
    except Exception as e:  # noqa: BLE001
        print(f"\nFAILED: {type(e).__name__}: {str(e)[:300]}")
        print("If this says 401 / Invalid Username or Password here too, the email or password is wrong.")
        return 1
    OUT.write_text(g.client.dumps(), encoding="utf-8")
    try:
        name = g.get_full_name()
    except Exception:  # noqa: BLE001
        name = "?"
    print(f"\nOK: logged in as {name}. Tokens saved to {OUT} (not printed).")
    print("Next, run:")
    print(f'  gh secret set GARMINTOKENS --repo Hagay-BOT/Garmin-data < "{OUT}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
