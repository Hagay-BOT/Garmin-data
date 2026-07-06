# ENGINEERING BACKLOG

Deduped findings from the 3 reviews. Status: TODO · DOING · DONE · REJECTED · PRODUCT-HOLD.
Grouped by milestone. Discovered-during-work items get appended here.

## M1 — Reliability quick wins
- [DONE] M1.1 Smoke-test harness `test_telegram_messages.py` (escape/empty/parse) + `ci-tests.yml` (compile + smoke on push).
- [DONE] M1.2 Deleted the entire dead morning loop (291 lines from coach.py: MORNING_SYSTEM, build_morning_prompt, run_morning, _parse_morning_json, _send_morning_telegram, _save_morning_state, _has_run_planned_today, _todays_planned_md, _todays_sessions, _readiness_emoji, MODEL_MORNING, main() morning dispatch) + deleted files `check_telegram_reply.py`, `adjust_today.py` (orphaned), `morning_state.json`. Kept `morning_readiness()` (feeds metrics["readiness"]). Verified: compiles, smoke tests pass, zero residual refs.
- [DONE] M1.3 `health_report.py` + `health-heartbeat.yml` (Fri 13:00 IL): deterministic weekly health summary to Telegram (data freshness · unanalyzed runs · pending retries · plan covers week+approved · journal · repo-idle/60-day risk) + heartbeat commit resets GitHub's cron-disable timer. Verified locally: builds, all-green on live state.
- [DONE] M1.4 Pin requirements.txt (upper bounds).
- [TODO] M1.5 Global UTF-8 stdout for local scripts (calendar_sync crashed on cp1252). Low/dev-experience.
- [DONE] M1.6 Prompt caching — verified already implemented (`cache_control: ephemeral` on the full system prompt in `_stream_report`, coach.py). Honest caveat: benefit is small (5-min TTL; weekly/postworkout calls are far apart; frequent watcher runs skip the API entirely). No further change justified.

## M2 — Single sources of truth
- [DONE] M2.1 `athlete.py` — single source of truth for athlete constants. Wired: push_week, push_strength (fixed live drift — old swapped A=Push names!), calendar_sync, coach.py (cadence ×2, max-hr fallback). VERIFIED: compiles, smoke tests pass, strength names asserted unified across all 3 consumers.
- [DONE] M2.2 `store.py` — single state-access layer with atomic writes (tmp+os.replace) and consistent defaults. Migrated cross-file consumers: journal.py (proxy), weekly_revise.py (state+plan), health_report.py, push_week.py (created_workouts ×4). Kept push_week.load_plan fail-fast ON PURPOSE (pushing an empty default plan to Garmin would be dangerous). Verified: compile, smoke, live round-trip + health green. Remaining: coach.py's ~28 internal reads migrate incrementally (tracked in M8 refactor).
- [DONE] M2.3 Athlete constants injected into all 3 prompts via ATHLETE_PROMPT_VARS (z2 range, easy pace, strides pace, cadence, goal race, long cap). Bonus fix: REVISE_SYSTEM was sent raw with literal {{}} doubled braces — now formatted at definition. Verified: all templates render, no leftover placeholders, smoke green.
- [DONE] M2.4 Glossary — covered by athlete.py (strength names/descs, zones, paces). Run categories remain in fetch_garmin (single definition site, no duplication found).

## M3 — Deterministic core
- [TODO] M3.1 Audit LLM output fields → move deterministic ones to code.
- [PRODUCT-HOLD] M3.2 Reduce daily per-run LLM analysis (user-facing).
- [PRODUCT-HOLD] M3.3 Deterministic weekly plan generator (user-facing).

## M4 — Garmin sync (⚠️ behaviour)
- [PRODUCT-HOLD] M4.1 Reconcile against Garmin scheduled workouts; atomic re-sync by plan-hash.
- [TODO] M4.2 One-command clean re-sync (cleanup+approve as a single action).

## M5 — Prompt architecture
- [TODO] M5.1 Extract prompts to `prompts/*.md` + version tags.
- [TODO] M5.2 Consolidate shared coaching rules into one referenced block.
- [TODO] M5.3 Prompt gardening pass (dedupe accumulated "חובה" rules).

## M6 — Telegram intake unification
- [TODO] M6.1 One state-machine intake service replacing the pollers.

## M7 — Workflow consolidation
- [TODO] M7.1 13 → ~5 workflows; remove near-duplicates; re-evaluate cron-job.org need.

## M8 — Structural refactor
- [TODO] M8.1 Split `coach.py` into packages.
- [TODO] M8.2 Split `index.html`.

## M9 — Long-term hygiene
- [TODO] M9.1 `data.json` rotation/archival.
- [TODO] M9.2 `garmin_client.py` isolation.
- [TODO] M9.3 JSON schema validation on load.
- [TODO] M9.4 Single date/week-anchor util (finish the Sunday-anchor consolidation).
- [TODO] M9.5 Narrow broad `except Exception` + add logging.
- [TODO] M9.6 `make ship` + local `preview-messages` (developer experience).
- [PRODUCT-HOLD] M9.7 Auto-approve weekly plan if no safety flags + no reply within X.

## Discovered during work
(append here)
