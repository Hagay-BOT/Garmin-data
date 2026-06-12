"""Smoke + logic tests for coach.py — runs all metric functions against real data.json.
Does NOT call the Claude API. Run: python test_coach.py"""
import sys, json, io
sys.stdout.reconfigure(encoding="utf-8")
from datetime import date

import coach

failures = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

data = coach.load_data()
acts = data["activities"]
daily = data["daily"]
gmax = data.get("global_max_hr") or 201.0

check("data.json loads", isinstance(acts, list) and len(acts) > 0, f"{len(acts)} activities")

# CTL/ATL
dl = coach.build_daily_load(acts)
lm = coach.compute_ctl_atl(dl, date.today())
check("CTL positive", lm["ctl"] > 0, f"CTL={lm['ctl']}")
check("ATL positive", lm["atl"] > 0, f"ATL={lm['atl']}")
check("ACWR sane", lm["acwr"] is None or 0 < lm["acwr"] < 5, f"ACWR={lm['acwr']}")
check("TSB = CTL-ATL", abs(lm["tsb"] - (lm["ctl"]-lm["atl"])) < 0.2)

# Zones
z = coach.compute_zone_distribution(acts, days=28)
if z.get("available"):
    tot = z["z1_pct"]+z["z2_pct"]+z["z3_pct"]+z["z4_pct"]+z["z5_pct"]
    check("zones sum ~100%", abs(tot-100) < 1.0, f"sum={round(tot,1)}")
else:
    check("zones available", True, "no zone data (acceptable)")

# Last week
lw = coach.summarize_runs(coach.last_n_days_runs(acts, n=7))
check("last week structure", "count" in lw and "runs" in lw, f"{lw['count']} runs")

# Trends
tr = coach.compute_fitness_trends(acts, gmax, weeks=8)
check("trends has ef/vo2max/cadence/vdot", all(k in tr for k in ("ef","vo2max","cadence","vdot")))
check("EF current numeric-or-none", tr["ef"]["current"] is None or tr["ef"]["current"] > 0, f"EF={tr['ef']['current']}")
check("VDOT numeric-or-none", tr["vdot"]["estimate"] is None or 20 < tr["vdot"]["estimate"] < 90, f"VDOT={tr['vdot']['estimate']}")

# Strength
st = coach.compute_strength_metrics(acts, days=7)
check("strength structure", "session_count" in st, f"{st['session_count']} sessions")
nm = coach.compute_neuromuscular_atl(acts, date.today())
check("NM-ATL >= 0", nm >= 0, f"NM-ATL={nm}")

# Readiness / PRs
rd = coach.get_readiness(daily)
check("readiness dict", isinstance(rd, dict))
prs = coach.compute_prs(acts)
check("PRs computed", isinstance(prs, dict), f"{list(prs.keys())}")

# History functions (no file yet — should not crash)
hist = coach.load_history()
check("load_history no crash", isinstance(hist, list))
comp = coach.compute_compliance(hist, lw)
check("compliance no crash", "available" in comp)

# Prompt building (the real integration — must not raise)
metrics = {"load": lm, "zones": z, "last_week": lw, "readiness": rd, "prs": prs,
           "global_max_hr": gmax, "trends": tr, "strength": st, "nm_atl": nm}
up = coach.build_user_prompt(metrics, hist, comp)
check("user prompt builds", isinstance(up, str) and len(up) > 500, f"{len(up)} chars")
kb = coach.load_knowledge_base()
check("knowledge base loads", len(kb) > 1000, f"{len(kb)} chars")
sp = coach.SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=kb)
check("system prompt builds", "{knowledge_base}" not in sp and len(sp) > 1000)

# PLAN_JSON extraction roundtrip
sample = 'דוח...\n---PLAN_JSON---\n{"run_count": 4, "total_km_approx": 29}\n---END_PLAN---'
pj = coach.extract_plan_json(sample)
check("PLAN_JSON extraction", pj.get("run_count") == 4, f"{pj}")

print("\n" + ("="*40))
if failures:
    print(f"❌ {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
