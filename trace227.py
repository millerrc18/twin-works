from datetime import datetime as DT
from routers import ELEVATOR_OPS, ELEVATOR_CURES
from schedule_engine import forward_schedule
AS_OF=DT(2026,8,19,12,0)
# RH227 MAX_CLOSED=3750 -> project from 3750
rows=forward_schedule(ELEVATOR_OPS,ELEVATOR_CURES,3750,AS_OF)
print("RH227 single-unit projection from op3750 (op3800 onward):")
tot_lab=0; tot_cure=0
for opno,kind,desc,s,f,wc,hrs,ms in rows:
    dur=(f-s).total_seconds()/3600
    if kind=='labor': tot_lab+=hrs
    else: tot_cure+=hrs
    print(f"  {str(opno or 'cure'):>5} {kind:5} {s.strftime('%a %m/%d %H:%M')}->{f.strftime('%a %m/%d %H:%M')} {hrs:>5}h {desc[:34]}")
print(f"\nTOTAL remaining labor={tot_lab}h  cure={tot_cure}h  finish={rows[-1][4].strftime('%a %m/%d %H:%M')}")
