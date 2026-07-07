# CHANGELOG (AI engineering program)

Reverse-chronological. One entry per meaningful change during the engineering program.

## 2026-07-06
- **M9.1 DONE** data.json slim-don't-drop rotation: heavy fields (gps/laps/splits) stripped
  from activities >180d; summaries kept forever so PRs & all-time views intact. Verified in
  production: 3189→1508 KB (−53%), unbounded growth capped. (Original "archive old activities"
  design rejected after evidence — it would have broken live features.)
- **M5.1 DONE** Prompts extracted from coach.py to `prompts/*.md` (4 files), loaded at import.
  Golden-check verified byte-identical rendering. Editing coach voice no longer touches code.
- **M4.2 DONE** One-command Garmin re-sync: `resync` checkbox on Approve Week → cleanup runs
  automatically before the push (RESYNC env through confirm_week). No more two-step dance.
- **M9.4 DONE** Single week-anchor util `athlete.week_start()` (Sunday). Found & fixed live
  drift: `current_week_monday()` still anchored Monday → history/weekly_state week_of
  mismatched the plan's Sunday week_of. All Python week math now goes through one function.
- **M2.3+M2.4 DONE — M2 milestone COMPLETE.** Athlete constants now injected into all 3 LLM
  prompts (ATHLETE_PROMPT_VARS): zones, real easy pace, strides pace, cadence, goal race,
  long cap. Bonus bug fix: REVISE_SYSTEM was sent raw with literal doubled {{}} braces —
  now formatted at definition. Glossary covered by athlete.py.
- **M2.2 DONE** `store.py` — single state-access layer, atomic writes (tmp+replace), consistent
  defaults. Migrated journal/weekly_revise/health_report/push_week; deliberately kept
  push_week.load_plan fail-fast (safety semantics). Verified live round-trip + health green.
- **CI-fix** pyyaml was missing on the CI runner (local global install masked it) — the
  YAML-validation step had been failing since added. Installed in-step. CI green again.
  Lesson recorded: a new CI step must be verified on CI, not just locally.
- **M2.1 DONE** Created `athlete.py` — single source of truth for all athlete
  constants (zones, real Z2 pace, cadence targets, race goal, strength A/B/C names).
  Wired into push_week, push_strength, calendar_sync, coach.py. **Found live drift while
  wiring: push_strength.py still carried the old swapped A=Push names — exactly the bug
  class this milestone eliminates.** Verification pending (classifier window).

## 2026-07-05
- **M1.3-fix** Colon inside a plain YAML scalar broke the new workflow at parse time (GitHub
  created a nameless failed run). Fixed + CI now validates ALL workflow YAMLs on push
  (new failure class → new permanent guard). Health report verified E2E (message_id=44).
- **M1.3** Added `health_report.py` + `health-heartbeat.yml` — weekly deterministic health
  summary to Telegram (freshness/unanalyzed/pending/plan-coverage/journal/repo-idle) +
  heartbeat commit that resets GitHub's 60-day scheduled-workflow disable timer.
- **M1.6** Verified prompt caching already implemented in `_stream_report` (cache_control on
  system prompt). Marked done with caveat: small benefit given call cadence vs 5-min TTL.
- **M1.2** Deleted the entire dead morning loop: −291 lines from coach.py (2731→2440) + removed
  `check_telegram_reply.py`, `adjust_today.py` (orphaned), `morning_state.json`. Kept
  `morning_readiness()` (still feeds metrics.readiness for weekly/postworkout). Verified clean.
- **M1.1** Added `test_telegram_messages.py` — smoke tests that render every Telegram message
  from poisoned sample data and assert HTML-escaped, non-empty, JSON parses (markers/fence/bare).
  Added `.github/workflows/ci-tests.yml` (compile all + smoke tests on every push). Guards the
  escape/empty/parse failure classes that broke production this session.
- **M1.4** Pinned requirements.txt with upper bounds (block surprise major bumps).
- **M0** Engineering program bootstrapped: added ENGINEERING_MASTER_PLAN, ENGINEERING_BACKLOG,
  ENGINEERING_DECISIONS, SESSION_STATE, CHANGELOG_AI. Merged 3 reviews into milestones M0–M9.
