# Load Management — CTL / ATL / ACWR

## Core Metrics

### CTL (Chronic Training Load) — "Fitness"
- 42-day exponential weighted average of daily training load
- Formula: `CTL_today = CTL_yesterday + (load_today - CTL_yesterday) * (1/42)`
- Represents long-term training adaptation
- Typical recreational runner: CTL 30–60
- Well-trained runner: CTL 60–100+
- Higher CTL = higher fitness base

### ATL (Acute Training Load) — "Fatigue"
- 7-day exponential weighted average of daily training load
- Formula: `ATL_today = ATL_yesterday + (load_today - ATL_yesterday) * (1/7)`
- Responds quickly to recent training stress
- High ATL relative to CTL = accumulated fatigue

### TSB (Training Stress Balance) — "Form"
- Formula: `TSB = CTL - ATL`
- Positive TSB: fresh/rested, lower fitness expression
- Negative TSB: fatigued, higher fitness expression
- Peak performance window: TSB between -10 and +5

### ACWR (Acute:Chronic Workload Ratio)
- Formula: `ACWR = ATL / CTL`
- Sweet spot: 0.8 – 1.3 (safe progression zone)
- Caution zone: 1.3 – 1.5 (elevated injury risk)
- DANGER ZONE: > 1.5 (Gabbett spike zone — high injury probability)
- Under-training: < 0.8 (detraining risk)

## Load Source
- Data.json uses `exercise_load` field (Garmin's internal training load metric)
- When `training_stress_score` is null, use `exercise_load` as the load proxy
- Multiple activities on the same day: sum all `exercise_load` values for that day

## Weekly Ramp Rate
- Recommended weekly CTL increase: 3–8 points/week
- Caution: 8–10 points/week
- Danger: > 10 points/week (injury risk)
- Safe rule: never increase weekly volume > 10% per week

## References
- Banister (1991): fitness-fatigue model
- Gabbett (2016): "The training-injury prevention paradox" — ACWR model
- Hulin et al. (2014): validation of 7:42 day ratio
