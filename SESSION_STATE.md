# SESSION STATE

> Read this first when resuming. Tells the next session exactly where to continue.

## Current milestone
**M1 — Stop the bleeding (reliability quick wins).**

## Repo consistency
Clean. All code compiles. Tests: `test_safety.py`, `test_approval_gates.py`, `test_coach.py`, `test_weekly_analysis.py`.

## Exact next implementation step
Executing M1 in order: M1.2 (delete dead morning code) → M1.1 (smoke tests) → M1.4/M1.5 → M1.3 (heartbeat) → M1.6 (prompt caching).

## Important context
- Personal project. Deterministic-core law. Sunday week-anchor. See ENGINEERING_DECISIONS.md.
- Garmin sync + daily-analysis reduction + plan-generator are PRODUCT-HOLD (need Hagay's OK) — do NOT change autonomously.
- Deploy = scheduled :15/:45. Postworkout marks-analyzed only after verified send. Telegram content is HTML-escaped.

## Known risks
- `data.json` grows unbounded. GitHub disables scheduled workflows after 60 days idle.
- Garmin `garminconnect` is unofficial; 429 rate-limits handled by retry in fetch_garmin.

## How to resume
1. Read the 5 state files. 2. `git pull`. 3. Check `python -m py_compile coach.py` + run tests. 4. Continue the "next step" above.
