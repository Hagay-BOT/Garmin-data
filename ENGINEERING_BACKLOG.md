# ENGINEERING BACKLOG

Deduped findings from the 3 reviews. Status: TODO · DOING · DONE · REJECTED · PRODUCT-HOLD.
Grouped by milestone. Discovered-during-work items get appended here.

## M1 — Reliability quick wins
- [DOING] M1.1 Smoke-test harness for all Telegram messages (parse/escape/non-empty/fields).
- [TODO] M1.2 Delete dead morning loop + `check_telegram_reply.py`.
- [TODO] M1.3 Heartbeat + weekly health-summary; document 60-day cron-disable risk.
- [TODO] M1.4 Pin requirements.txt versions.
- [TODO] M1.5 Global UTF-8 stdout for all scripts.
- [TODO] M1.6 Prompt caching for knowledge_base.

## M2 — Single sources of truth
- [TODO] M2.1 `athlete.py` constants.
- [TODO] M2.2 `store.py` state accessor layer.
- [TODO] M2.3 Inject athlete constants into prompts.
- [TODO] M2.4 Shared glossary (A/B/C names, categories, zones).

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
