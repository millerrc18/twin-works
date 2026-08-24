"""Feature-vetting: lay candidate ML signals next to actual behavior for the 8
ground-truth radome/elevator closes. HONEST FRAMING: n=8 -> directional only,
NOT statistically significant. Purpose: (a) is each signal computable/clean from
IFS, (b) are magnitudes plausible (big enough to explain multi-day slips),
(c) surface the rework/re-clock noise so we know what needs cleaning.
"""
import json, re, statistics
from collections import defaultdict

SRC = r"C:\Users\ryan.c.miller\.claude\projects\C--Users-ryan-c-miller\7cc9493c-9e1f-4f7c-80d6-c6e8c2fcfbc7\tool-results\toolu_vrtx_016c28nkjUCd7fMstaC8fqPH.txt"
rows = json.loads(json.loads(open(SRC,encoding='utf-8').read())["result"])["data"]
STD  = json.load(open(r"C:\Users\ryan.c.miller\Downloads\rtg-tracker-build\_rad_std.json"))

# radome SOs among the 8 (elevator ones have a different router; note separately)
RAD_SOS = {'1451435','1453337'}
ELEV_SOS = {'1451269','1451270','1453480','1453479','1453860','1455597'}

by_so=defaultdict(list)
for r in rows: by_so[r['SO']].append(r)

print("="*78)
print("SIGNAL VETTING  (n=8 ground-truth closes)  —  DIRECTIONAL ONLY, not significant")
print("="*78)

# ---- Signal 1: op-dwell outliers (SPAN_DAYS >> implied by CLK_HRS) ----
# A big span with small clocked hours = the unit SAT (queue/stall/coverage gap).
# That gap is where slip is born. Flag ops where span_days*24 >> clk_hrs.
print("\n[SIGNAL 1] OP-DWELL OUTLIERS  (span >> work => unit sat waiting)")
print("  Top 'sat' ops per unit (span_days vs clocked hrs; ratio = idle multiple):")
for so in list(RAD_SOS)+list(ELEV_SOS):
    ops=by_so.get(so,[])
    outliers=[]
    for o in ops:
        span=o['SPAN_DAYS'] or 0; clk=o['CLK_HRS'] or 0.1
        idle_days = span - clk/24.0
        if span>=2 and idle_days>=2:   # sat >=2 days beyond the work
            outliers.append((idle_days, o['OPNO'], span, clk))
    outliers.sort(reverse=True)
    tag = 'RAD' if so in RAD_SOS else 'ELEV'
    top=outliers[:3]
    ss=" | ".join(f"op{op}:{idle:.0f}d idle(span{span:.0f}/clk{clk:.0f}h)" for idle,op,span,clk in top)
    print(f"  {tag} {so}: {ss if top else '(no big idle gaps)'}")

# ---- Signal 2: labor coverage (N_EMP per op; zero-clock gap days) ----
print("\n[SIGNAL 2] LABOR COVERAGE  (N_EMP per op = effective crew; router says 1)")
for so in list(RAD_SOS)+list(ELEV_SOS):
    ops=by_so.get(so,[])
    if not ops: continue
    emps=[o['N_EMP'] for o in ops if o['N_EMP']]
    multi=[(o['OPNO'],o['N_EMP']) for o in ops if (o['N_EMP'] or 0)>=3]
    tag='RAD' if so in RAD_SOS else 'ELEV'
    print(f"  {tag} {so}: median crew={statistics.median(emps):.0f} max={max(emps)}  swarm-ops(>=3): {multi[:4]}")

# ---- Signal 3: rework/re-clock noise (op clocked with span way out of sequence) ----
print("\n[SIGNAL 3] REWORK/RE-CLOCK NOISE  (op re-touched long after it should close)")
print("  Ops whose span >30d = almost certainly re-clock/rework, NOT true dwell:")
for so in list(RAD_SOS)+list(ELEV_SOS):
    ops=by_so.get(so,[])
    noisy=[(o['OPNO'],o['SPAN_DAYS'],o['FIRST_CLK'],o['LAST_CLK']) for o in ops if (o['SPAN_DAYS'] or 0)>30]
    tag='RAD' if so in RAD_SOS else 'ELEV'
    if noisy: print(f"  {tag} {so}: {[(f'op{op}',f'{sp:.0f}d',f'{fc}->{lc}') for op,sp,fc,lc in noisy]}")

# ---- Summary read ----
print("\n"+"="*78)
print("MAGNITUDE CHECK (are signals big enough to explain multi-day slips?)")
allspans=[o['SPAN_DAYS'] for so in by_so for o in by_so[so] if (o['SPAN_DAYS'] or 0)>0]
print(f"  op-span distribution: median={statistics.median(allspans):.1f}d  p90={sorted(allspans)[int(len(allspans)*0.9)]:.1f}d  max={max(allspans):.0f}d")
print(f"  total ops sampled: {len(rows)} across {len(by_so)} units")
