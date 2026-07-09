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
- [DONE] M4.2 One-command clean re-sync: approve-week.yml now has a `resync` checkbox input → confirm_week runs cleanup before push (RESYNC env). Replaces the manual cleanup→wait→approve dance (done ~6× by hand). Verified: compiles, YAML valid, flag path exercised, smoke green.

## M5 — Prompt architecture
- [DONE] M5.1 All 4 prompts extracted to `prompts/*.md` (weekly/postworkout/revise/chat), loaded via `_load_prompt()`. Extraction from LIVE module values (regex-from-source hit Python `\"` escapes — caught by golden check). revise.md stored pre-formatted (athlete values literal; note in code). **Verified byte-identical rendering before/after.** coach.py: 2731→2231 lines since program start.
- [TODO] M5.2 Consolidate shared coaching rules into one referenced block (now easy — prompts are files).
- [TODO] M5.3 Prompt gardening pass (dedupe accumulated "חובה" rules). Note: revise.md athlete literals → consider placeholders+format when gardening.

## M6 — Telegram intake unification
- [TODO] M6.1 One state-machine intake service replacing the pollers.

## M7 — Workflow consolidation
- [TODO] M7.1 13 → ~5 workflows; remove near-duplicates; re-evaluate cron-job.org need.

## M8 — Structural refactor
- [TODO] M8.1 Split `coach.py` into packages.
- [TODO] M8.2 Split `index.html`.

## M9 — Long-term hygiene
- [DONE] M9.1 data.json rotation — **design changed after evidence** ("challenge the plan"): dropping old activities would break live features (all-time PRs, dashboard "הכל" view). Instead: **slim-don't-drop** — activities >180d lose heavy fields only (gps=59% of weight, laps, splits_100m; consumed only for recent runs: GPS gallery=last 6, laps=this week). All summary fields kept forever. Verified E2E in production: 812 fields removed, 3189→1508 KB (−53%), growth structurally capped. All 525 activities + PRs intact.
- [TODO] M9.2 `garmin_client.py` isolation.
- [TODO] M9.3 JSON schema validation on load.
- [DONE] M9.4 Single week-anchor util: `athlete.week_start(_iso)` (Sunday). Fixed live drift: coach's `current_week_monday()` still returned MONDAY (vs Sunday decision) → history/weekly_state week_of mismatched the plan's. Renamed to `current_week_start()`, health_report inline calc unified. JS side (index.html weekBounds) documented as the single JS twin. Verified: anchor asserts on 4 dates, health green, smoke green.
- [DONE] M9.5 Silent-failure triage (targeted, not blanket): (1) coach _load_analyzed/_load_pw_pending/_write_analyzed_payload → store.py (corrupt file now logged + atomic writes; silent swallow would have re-analyzed ALL runs = API/Telegram spam); (2) load_macro_plan corrupt → loud 🔴 print (was silently "no macro"); (3) **save_history_entry corrupt-read was WIPING the entire history on next save — now raises loudly instead of silent data loss**; (4) load_history corrupt → logged. Benign parse-fallbacks left as-is (deliberate). BONUS: test_coach.py had drifted (pre-M2.3 format call) and CI didn't catch it because it only ran smoke → **CI now runs the FULL test suite** (new guard for the tests-drift class).
- [DOING] M9.6 DX tools written: `ship.py` (one-command compile→YAML-validate→full-tests→add/commit/rebase/push, stops on any failure) + `preview_messages.py` (render postworkout+weekly Telegram messages from live data locally, no send, no LLM — <LLM> placeholders mark model-filled fields). **PENDING VERIFY (classifier window): run preview_messages, then ship.py shipping itself.**
- [PRODUCT-HOLD] M9.7 Auto-approve weekly plan if no safety flags + no reply within X.

## Discovered during work
(append here)
