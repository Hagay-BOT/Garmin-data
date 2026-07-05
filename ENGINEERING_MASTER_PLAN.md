# ENGINEERING MASTER PLAN — Garmin Coach

> Permanent engineering memory. Derived from 3 comprehensive reviews (2026-07-05).
> This is a **personal, long-term** project. Optimize for: reliability · simplicity ·
> maintainability · automation · correctness · **deterministic behaviour** · low maintenance.
> **Guiding law:** LLM only where language is the input or output. Facts & logic → code.
> Push signal, not information. Boring-and-reliable > impressive-and-fragile.

## North Star
> Fewer moving parts · one source of truth for everything · every failure screams (never silent).

---

## Milestones (priority order)

### M0 · Engineering foundation ✅ (this session)
The 5 state files exist and stay synced with the repo.

### M1 · Stop the bleeding — reliability quick wins  ← **ACTIVE**
Safe, non-user-facing, highest ROI. Prevents the recurring silent breaks.
- M1.1 Smoke-test harness: render every Telegram message from sample data; assert JSON parses, HTML-escaped, non-empty, required fields present. Runs in CI + locally.
- M1.2 Delete dead morning loop (workflow already removed): `run_morning`, `MORNING_SYSTEM`, `_has_run_planned_today`, `_todays_planned_md`, `morning_state.json`, `check_telegram_reply.py`.
- M1.3 Heartbeat + weekly health-summary to Telegram (dead-man's switch; GitHub disables scheduled workflows after 60 days of no commits).
- M1.4 Pin dependencies in requirements.txt.
- M1.5 Global UTF-8 (kill recurring cp1252 crashes).
- M1.6 Prompt caching for the static knowledge_base (Anthropic cache_control) — token win.

### M2 · Single sources of truth
- M2.1 `athlete.py` — all of Hagay's constants (zones, paces, targets, cadence, thresholds) in ONE place.
- M2.2 `store.py` — typed accessors that own every JSON read/write + validation (kills scattered `json.load(open())` + field drift).
- M2.3 Config-drives-prompts: inject athlete constants into prompt strings so code & prompts can't diverge.
- M2.4 Shared glossary/constants (strength A/B/C names, run categories, zone labels).

### M3 · Deterministic core  ⚠️ (contains user-facing changes → needs product OK)
- M3.1 Field-by-field audit of LLM outputs; move deterministic fields fully to code.
- M3.2 [PRODUCT] Reduce daily per-run LLM analysis → deterministic status + pull-on-demand insight.
- M3.3 [PRODUCT] Deterministic weekly plan generator (LLM only for narrative + revision NLU).

### M4 · Garmin sync robustness  ⚠️ (behaviour-sensitive)
Reconcile against Garmin's scheduled workouts (source of truth); atomic re-sync by plan-hash; one-command re-sync.

### M5 · Prompt architecture
Extract prompts to `prompts/*.md` with version tags; consolidate shared coaching rules into one referenced block; periodic prompt gardening.

### M6 · Telegram intake unification
One intake service (state-machine) replacing the 4–5 pollers.

### M7 · Workflow consolidation (13 → ~5).

### M8 · Structural refactor: split `coach.py` (2.7k lines) and `index.html` (1.5k) into modules.

### M9 · Long-term hygiene: `data.json` rotation/archival · `garmin_client.py` isolation · JSON schema validation on load · single date/week-anchor util.

---

## Guardrails on autonomy
Implement autonomously EXCEPT when a change: deletes important data · significantly changes user-facing behaviour · needs a subjective product decision. Those are marked `[PRODUCT]` / ⚠️ and go to the backlog for explicit approval.

## Status
Current milestone: **M1**. See SESSION_STATE.md for the exact next step.
