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
**M2.1 DONE & pushed** (athlete.py + 4 consumers wired, verified compile/smoke/name-asserts).
**Next: M2.2 — `store.py`.** Recon done: raw JSON access points — coach.py×28,
push_week×5, weekly_revise×3, confirm_week×2, health_report×2, journal×2 (journal already
has its own _load/_save — pattern to generalize). Suggested scope: build store.py accessors
for shared mutable state (week_plan, analyzed_runs, weekly_state, journal, created_workouts,
coach_history; data.json read-only) with defaults+validation; migrate the CROSS-FILE consumers
first (weekly_revise, confirm_week, health_report, push_week); migrate coach.py's 28 internal
reads incrementally after. Then M2.3 config-into-prompts, M2.4 glossary (mostly done via athlete.py).
Also pending from M2.1: fetch_garmin zone thresholds use %maxHR — verify semantics before wiring athlete zones there.
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
