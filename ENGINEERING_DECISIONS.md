# ENGINEERING DECISIONS (ADRs)

Short, dated architectural decisions. Stops re-litigating the same choices.
Format: date · decision · rationale · consequences.

## 2026-07-05 · Adopt an engineering program with 5 permanent state files
Three reviews became the spec. Execute milestone-by-milestone, autonomously, with the 5
state files (MASTER_PLAN, BACKLOG, DECISIONS, SESSION_STATE, CHANGELOG_AI) as permanent memory.

## 2026-07-05 · Personal scale → serialize state, do NOT migrate to a DB/server
Review 1 suggested moving git-as-DB to a real DB. Review 2 reversed this for a single-user,
low-write, low-maintenance project: a server/DB adds cost + moving parts against the goals.
**Decision:** keep JSON-on-git, but enforce single-writer + idempotency + serialization.

## 2026-07-05 · Guiding law: deterministic core, LLM only at the edges
LLM only where language is the input (free-text revision) or output (weekly narrative,
Q&A). Facts and logic (plan, metrics, classification, "next") → code. Rationale: the
recurring failures this session were LLM doing deterministic work + high-volume low-signal
daily prose. Consequence: shrink LLM usage from ~50 calls/week toward ~2–3.

## 2026-07-05 · Sunday is the week anchor (Sun–Sat)
Training week, dashboard, macro all anchor on Sunday. macro uses `start_sunday` (2026-06-14).
Consequence: any new week/date logic must use the shared anchor; no Monday-based math.

## 2026-07-05 · Strength split naming is fixed: A=Pull/משיכה · B=Push/דחיפה · C=Legs
Was swapped in multiple files historically. Single source of truth to be centralized (M2.4).

## 2026-07-05 · Telegram messages must HTML-escape all LLM content
Unescaped `<`/`&` caused 400 Bad Request → lost messages. All senders escape dynamic content.

## 2026-07-05 · Deploy publishes on a fixed schedule (:15/:45), not on workflow_run
workflow_run fan-out caused near-simultaneous Pages deploys → collisions. Fixed cadence,
spaced, cannot collide. Data freshness ≤30 min is acceptable for this project.

## 2026-07-09 · Product decisions (Hagay)
- **M3.2 APPROVED** — reduce daily per-run LLM analysis (deterministic status; deep insight on demand).
- **M3.3 APPROVED** — deterministic weekly plan generator; LLM only for narrative + Telegram revision NLU.
- **M4.1 APPROVED** — reconcile Garmin sync against the watch's actual scheduled workouts.
- **M9.7 REJECTED** — no auto-approve, ever: the plan must wait for Hagay's explicit reply
  (schedule fit is personal). Weekly flow stays approval-gated.
- **NEW M10 APPROVED** — before building next week's plan, the bot ASKS Hagay "מה התוכניות
  שלך לשבוע הבא?" (availability/constraints); his free-text answer feeds the planner.
  Natural flow: Sat pre-plan question → answer captured → plan built around it.

## 2026-07-05 · Postworkout: mark-analyzed only after a verified Telegram send (message_id)
Prevents silent loss. Failures retry up to MAX_POSTWORKOUT_ATTEMPTS then give up (cost cap).
