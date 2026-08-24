from datetime import datetime as DT, date
from routers import ELEVATOR_OPS, ELEVATOR_CURES
from capacity_engine import simulate
AS_OF=DT(2026,8,19,12,0)
# RH227 alone, status pos 3750 (in 3800), to isolate tail behavior
u=[dict(serial='RH 227',so='1452749',maxop=3750,commit=date(2026,8,21),program='ELEV')]
res=simulate(u,{'ELEV':ELEVATOR_OPS},{'ELEV':ELEVATOR_CURES},AS_OF)
r=res['RH 227']
print("RH227 alone, from op3750 (in-process 3800):")
print(f"  op dates:")
for opno in sorted(r['op_dt']):
    print(f"    op{opno}: {r['op_dt'][opno].strftime('%a %m/%d %H:%M')}")
print(f"  cures: {[(k[:30], v.strftime('%m/%d %H:%M')) for k,v in r['cure_dt'].items()]}")
print(f"  FINISH: {r['finish'].strftime('%a %m/%d %H:%M')}")
print(f"\n  Actual fast-path comp (unit 1455597): op3800 8/11 -> final insp 8/15 = 4 days")
print(f"  RH227 started 3800 ~8/19 -> +4 = Sat 8/23 target")
