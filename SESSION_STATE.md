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
**M2 milestone COMPLETE** (M2.1 athlete.py · M2.2 store.py · M2.3 constants→prompts via
ATHLETE_PROMPT_VARS incl. REVISE double-brace bugfix · M2.4 glossary via athlete.py).
M9.4 DONE (single Sunday week-anchor via athlete.week_start; fixed Monday-drift in
current_week_monday→current_week_start).
M5.1 + M9.1 DONE (prompts extracted byte-identical; data.json slim-rotation −53%, verified in prod).
**Next options (remaining meaningful items):**
- M5.2+M5.3 prompt content consolidation + gardening (CONTENT changes — one focused session,
  ideally with Hagay reviewing wording changes).
- M9.5 narrow broad excepts + logging; M9.6 make-ship DX; M9.2 garmin_client isolation;
  M9.3 JSON schema validation.
- M6 (unify Telegram pollers) / M7 (workflow consolidation) — medium refactors.
- [PRODUCT-HOLD] M3.2/M3.3/M4.1/M9.7 — awaiting Hagay's explicit OK.
M9.5 DONE (silent-failure triage incl. latent history-wipe data-loss bug; CI now runs full suite).
Recommended next: M6 (unify Telegram pollers — real reliability value) or M9.6 make-ship DX.
Note: prompts/revise.md stores athlete values as literals (documented in coach.py).
[PRODUCT-HOLD items M3.2/M3.3/M4.1/M9.7 still await Hagay's explicit OK.]
Pending side-note: fetch_garmin zone thresholds use %maxHR semantics — verify before wiring
athlete zone constants there.
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
