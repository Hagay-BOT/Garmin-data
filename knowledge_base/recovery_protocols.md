# Recovery Protocols — Readiness & Fatigue Management

## Readiness Assessment Framework

### Body Battery (Garmin HRV-based)
- 76–100: Fully recovered — green light for hard training
- 51–75: Moderate readiness — okay for easy/moderate training
- 26–50: Fatigued — easy only, consider rest
- 0–25: Depleted — rest day mandatory
- **Decision rule**: never schedule a quality (Z4-Z5) session if morning body battery < 50

### Sleep Score (Garmin)
- 80–100: Excellent sleep — go ahead with planned training
- 60–79: Good sleep — normal training okay
- 40–59: Poor sleep — drop intensity by one level (if planned Z4, do Z2)
- < 40: Very poor sleep — rest or active recovery only
- **Decision rule**: two consecutive nights with sleep score < 60 = mandatory load reduction

### Combined Readiness Gate
Before any quality session, check all three:
1. Body Battery > 50
2. Sleep score (last night) > 60
3. ACWR < 1.3
If any fails: downgrade to Z2/recovery run or rest

## Recovery Time by Session Type
- Z2 easy run: recover in 24h
- Z3 tempo: recover in 36–48h
- Z4 threshold intervals: recover in 48h
- Z5 VO2max intervals: recover in 48–72h
- Long run > 15km: recover in 48–72h
- Strength training (heavy): recover in 48h

## Active Recovery
- Best performed 1–2 days after a hard session
- HR should stay in Z1 (< 60% MaxHR)
- Duration: 20–40 minutes
- Effect: increases blood flow, reduces muscle soreness, maintains movement pattern

## Signs of Overreaching (Non-Functional)
- Resting HR elevated > 5 bpm above baseline for 3+ days
- Body battery consistently < 50 despite rest days
- Performance decline lasting > 2 weeks
- Mood disturbance, sleep disruption, loss of motivation
- **Action required**: reduce training volume 40–60%, 5–7 days

## Deload Week Protocol
- Every 3–4 weeks, reduce weekly volume by 30–40%
- Keep intensity same (maintain neuromuscular feel)
- Purpose: supercompensation — fitness improves during recovery, not during stress
- Signs that deload is needed: 2+ weeks of declining body battery trend

## Hydration Impact on Recovery
- Sweat loss tracked in data.json (`sweat_loss_ml`)
- > 1.5L sweat loss: replenish carefully, affects next-day body battery
- Heat training: higher sweat loss, longer recovery window needed

## References
- Halson, S.L. (2014): "Monitoring Training Load to Understand Fatigue in Athletes"
- Meeusen et al. (2013): "Prevention, Diagnosis, and Treatment of the Overtraining Syndrome" (ECSS/ACSM joint consensus)
- Plews et al. (2013): HRV for monitoring training adaptation
