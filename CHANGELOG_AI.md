# CHANGELOG (AI engineering program)

Reverse-chronological. One entry per meaningful change during the engineering program.

## 2026-07-06
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
