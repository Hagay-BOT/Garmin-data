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
M9.5 + M9.6 DONE (ship.py verified by shipping itself; preview_messages renders live).
**From now on: use `python ship.py "msg" [files]` for every commit** (runs full verification).
M6 DONE (re-scoped: shared classifier + guards; fixed note→revise-LLM live bug).
**Remaining meaningful items:** M7 workflow consolidation (13→~5; includes true poller
unification if still worth it) · M9.2 garmin_client isolation · M9.3 schema validation ·
M5.2-3 prompt gardening (content — with Hagay) · M8 structural split (coach.py/index.html) ·
[PRODUCT-HOLD] M3.2/M3.3/M4.1/M9.7 (need Hagay's OK).
M9.2 + M9.3 DONE. **All safe-filler engineering is COMPLETE.**
**PRODUCT DECISIONS RECEIVED 2026-07-09** (see DECISIONS): M3.2 ✅ M3.3 ✅ M4.1 ✅ ·
M9.7 ❌ rejected (always wait for explicit approval) · **NEW M10** ✅ pre-plan availability
question ("מה התוכניות שלך לשבוע הבא?" → constraints feed the planner).
**Build order (each is a session-scale build; verify heavily, these are user-facing):**
1. **M10 + M3.3 together** — availability question → constraints → deterministic plan
   generator (rules from athlete.py + user_profile week-structure + macro km + strength
   rotation continuity from history). LLM keeps narrative + revision NLU + availability parsing.
2. **M3.2** — deterministic daily status; LLM insight only on red-flag/quality/journal/on-demand.
3. **M4.1** — reconcile sync against get_scheduled_workouts.
M5.2-3 (prompt gardening) explained to Hagay — awaiting his interest; low priority.
**Build #1 STAGE A DONE:** `plan_generator.py` (deterministic WEEK_PLAN: Sat=long,
quality ≥48h before, C mid-week + Z1 recovery after, A/B×2+C rotation continuity, busy-days
shift sessions & redistribute km) + `parse_availability` (conservative: day+busy-word) +
`test_plan_generator.py` (4 rule-tests, in ship+CI). E2E dry-verified through
materialize+safety on real macro.
**STAGE B DONE:** ask_availability.py (Sat 10:00 IL, ask-availability.yml) → weekly_state
{awaiting_availability, sent_at, availability_raw:""} · capture_notes routes ANY text in the
window (after sent_at) to availability_raw (plan-vocab allowed — answers naturally contain it)
· weekly_revise now acts ONLY on status==pending_review (state-machine guard) · run_weekly's
state-write preserves availability_raw. Flow simulated E2E with state restore.
**STAGE C after:** wire generator into run_weekly (replace LLM WEEK_PLAN_JSON emission;
prompt surgery: LLM gets the BUILT plan, writes narrative only; PLAN_JSON summary computed
deterministically from generator output). Verify with preview_messages + DRY weekly.
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
