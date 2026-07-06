# SESSION STATE

> Read this first when resuming. Tells the next session exactly where to continue.

## Current milestone
**M1 — Stop the bleeding (reliability quick wins).**

## Repo consistency
Clean. All code compiles. Tests: `test_safety.py`, `test_approval_gates.py`, `test_coach.py`, `test_weekly_analysis.py`.

## Exact next implementation step
**M1 is COMPLETE and E2E-verified** (M1.1 smoke+CI incl. YAML validation · M1.2 dead morning
code · M1.3 health+heartbeat — first report delivered, message_id=44 · M1.4 pinned deps ·
M1.6 caching verified-existing). M1.5 (UTF-8) folded into M9 hygiene (low).
**M2.1 + M2.2 DONE** (athlete.py source-of-truth; store.py atomic state layer, 4 consumers
migrated; coach.py internals deferred to M8).
**Next: M2.3 — config-drives-prompts.** Inject athlete.py constants into the prompt strings
(WEEKLY_SYSTEM / POSTWORKOUT_SYSTEM currently hardcode 121–141, 4:50, 5:20, 180, 6:45–7:00 —
format them from athlete.py so code and prompts cannot diverge). M2.4 glossary largely covered
by athlete.py — verify and close. Then M2 is complete; next milestone M5 (prompt architecture)
or M9 quick-hygiene items.
Pending side-note from M2.1: fetch_garmin zone thresholds use %maxHR semantics — verify before
wiring athlete zone constants there.
Verify after any coach.py change: `python -m py_compile coach.py` + `python test_telegram_messages.py`.

## Important context
- Personal project. Deterministic-core law. Sunday week-anchor. See ENGINEERING_DECISIONS.md.
- Garmin sync + daily-analysis reduction + plan-generator are PRODUCT-HOLD (need Hagay's OK) — do NOT change autonomously.
- Deploy = scheduled :15/:45. Postworkout marks-analyzed only after verified send. Telegram content is HTML-escaped.

## Known risks
- `data.json` grows unbounded. GitHub disables scheduled workflows after 60 days idle.
- Garmin `garminconnect` is unofficial; 429 rate-limits handled by retry in fetch_garmin.

## How to resume
1. Read the 5 state files. 2. `git pull`. 3. Check `python -m py_compile coach.py` + run tests. 4. Continue the "next step" above.
