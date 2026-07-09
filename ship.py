# -*- coding: utf-8 -*-
"""
ship.py — צינור המשלוח המקומי בפקודה אחת (M9.6).

    python ship.py "commit message" [file1 file2 ...]

עושה בדיוק את מה שעשינו ידנית עשרות פעמים, באותו סדר, בלי לשכוח שלב:
  1. py_compile לכל קבצי ה-Python במעקב git
  2. ולידציית YAML לכל ה-workflows
  3. חבילת הטסטים המלאה (אותה רשימה כמו ה-CI)
  4. git add (הקבצים שניתנו, או -u לכל השינויים במעקב)
  5. commit → pull --rebase → push

כל שלב שנכשל עוצר את המשלוח. בלי דגלים, בלי מצבים — פשוט rails.
"""
import subprocess
import sys
import glob

TESTS = ["test_telegram_messages.py", "test_telegram_intake.py", "test_coach.py",
         "test_safety.py", "test_approval_gates.py", "test_weekly_analysis.py"]


def run(cmd: list, name: str) -> None:
    print(f"▶ {name} ...", flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print(f"🔴 {name} נכשל — המשלוח נעצר.")
        sys.exit(r.returncode)


def main():
    if len(sys.argv) < 2:
        print('שימוש: python ship.py "commit message" [files...]')
        sys.exit(1)
    msg, files = sys.argv[1], sys.argv[2:]

    tracked_py = subprocess.run(["git", "ls-files", "*.py"], capture_output=True,
                                text=True).stdout.split()
    run([sys.executable, "-m", "py_compile", *tracked_py], "compile all python")

    run([sys.executable, "-c",
         "import yaml,glob\n"
         "[yaml.safe_load(open(f,encoding='utf-8')) for f in glob.glob('.github/workflows/*.yml')]\n"
         "print('workflows OK')"], "validate workflow YAMLs")

    for t in TESTS:
        run([sys.executable, t], f"tests: {t}")

    run(["git", "add", *(files or ["-u"])], "git add")
    run(["git", "commit", "-m", msg], "git commit")
    run(["git", "pull", "--rebase", "origin", "main"], "git pull --rebase")
    run(["git", "push", "origin", "main"], "git push")
    print("✅ shipped.")


if __name__ == "__main__":
    main()
