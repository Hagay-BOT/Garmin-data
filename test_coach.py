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

# ACWR status (Feature 3)
st_g = coach.acwr_status(1.0); st_y = coach.acwr_status(1.4)
st_r = coach.acwr_status(1.7); st_b = coach.acwr_status(0.6)
st_n = coach.acwr_status(None)
check("ACWR green", st_g["flag"] == "🟢")
check("ACWR yellow", st_y["flag"] == "🟡")
check("ACWR red", st_r["flag"] == "🔴", st_r["level"])
check("ACWR blue (under)", st_b["flag"] == "🔵")
check("ACWR none-safe", st_n["flag"] == "⚪")
live_acwr = coach.acwr_status(lm["acwr"])
check("ACWR live flag present", live_acwr["flag"] in ("🟢","🟡","🔴","🔵","⚪"), f"{lm['acwr']} → {live_acwr['flag']}")

# Training Monotony (Feature 4)
mono = coach.compute_training_monotony(dl, date.today())
check("monotony structure", "monotony" in mono and "flag" in mono, f"={mono.get('monotony')} {mono.get('flag')}")
check("monotony non-negative", mono.get("monotony") is None or mono["monotony"] >= 0)
# synthetic: identical loads → max monotony flag
flat = {(date.today()-__import__('datetime').timedelta(days=i)).isoformat(): 50.0 for i in range(7)}
mono_flat = coach.compute_training_monotony(flat, date.today())
check("monotony flat→max risk", mono_flat["flag"] == "🔴", mono_flat["level"])
# synthetic: varied loads → lower monotony
import datetime as _dt
varied = {(date.today()-_dt.timedelta(days=i)).isoformat(): v for i, v in enumerate([100,0,90,0,40,0,120])}
mono_var = coach.compute_training_monotony(varied, date.today())
check("monotony varied numeric", mono_var["monotony"] is not None and mono_var["monotony"] > 0, f"={mono_var['monotony']}")

# Zone helper
check("zone index z2", coach._zone_index_from_pct(0.65) == 1)
check("zone index z5", coach._zone_index_from_pct(0.95) == 4)

# Zones (with avg_hr fallback enabled)
z = coach.compute_zone_distribution(acts, days=28, global_max_hr=gmax)
if z.get("available"):
    check("zones fallback fields", "runs_measured" in z and "runs_estimated" in z,
          f"measured={z.get('runs_measured')} estimated={z.get('runs_estimated')}")
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
metrics = {"load": lm, "acwr_status": coach.acwr_status(lm["acwr"]),
           "monotony": coach.compute_training_monotony(dl, date.today()),
           "zones": z, "last_week": lw, "readiness": rd, "prs": prs,
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

# Reliability: load_data fallback on missing file
import push_week
_orig_data = coach.DATA_FILE
try:
    coach.DATA_FILE = "no_such_file_xyz.json"
    fb = coach.load_data()
    check("load_data fallback", fb == {"activities": [], "daily": {}}, f"{fb}")
finally:
    coach.DATA_FILE = _orig_data

# Garmin workout validation
good = {"date": "2026-06-22", "type": "run",
        "steps": [{"kind": "interval", "seconds": 2000}]}
try:
    push_week.validate_workout(good)
    check("validate_workout accepts valid", True)
except Exception as e:
    check("validate_workout accepts valid", False, str(e))

def _expect_reject(sess, label):
    try:
        push_week.validate_workout(sess)
        check(label, False, "לא נדחה")
    except ValueError:
        check(label, True)

_expect_reject({"date": "x", "type": "run", "steps": [{"kind": "interval", "seconds": 0}]},
               "validate_workout rejects zero-duration")
_expect_reject({"date": "x", "type": "run", "steps": [{"kind": "bogus", "seconds": 100}]},
               "validate_workout rejects unknown kind")

print("\n" + ("="*40))
if failures:
    print(f"❌ {len(failures)} FAILED: {failures}")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
