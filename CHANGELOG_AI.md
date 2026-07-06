# CHANGELOG (AI engineering program)

Reverse-chronological. One entry per meaningful change during the engineering program.

## 2026-07-05
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
