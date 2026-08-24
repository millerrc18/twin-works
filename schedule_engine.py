"""Cure-loaded schedule engine for the RTG Operation Tracker.
Forward-projects each unit's finish from its current IFS position, injecting
WI-mandated cure dwells (24/7 wall-clock) and labor ops (shift-limited).
Empirical rate: ~16 productive labor hrs/unit/active-day (from 2-wk clocking).
Cures run continuously incl nights/weekends. Labor runs Mon-Sat (weekend reduced).
"""
import datetime
from datetime import datetime as DT, timedelta
from routers import ELEVATOR_OPS, ELEVATOR_CURES, RADOME_OPS, RADOME_CURES

LABOR_HR_PER_DAY   = 16.0     # empirical per-unit productive hrs on an active weekday
SAT_FACTOR         = 0.5      # Saturdays worked at reduced rate (2-on/1-off OT)
SUN_FACTOR         = 0.25     # occasional Sunday
SHIFT_START_HOUR   = 6        # 0600 first shift start
SHIFT_SPAN_HOURS   = 16       # ~2 shifts of productive coverage per weekday

def labor_capacity(day):
    wd=day.weekday()  # 0=Mon..6=Sun
    if wd<5: return LABOR_HR_PER_DAY
    if wd==5: return LABOR_HR_PER_DAY*SAT_FACTOR
    return LABOR_HR_PER_DAY*SUN_FACTOR

def add_labor_hours(start_dt, hours):
    """Advance a datetime by `hours` of LABOR effort, respecting daily capacity
    and shift window. Returns finish datetime."""
    cur=start_dt
    remaining=hours
    # normalize into a shift-day
    while remaining>1e-6:
        day=cur.date()
        cap=labor_capacity(datetime.datetime.combine(day,datetime.time()))
        if cap<=0:
            cur=datetime.datetime.combine(day+timedelta(days=1), datetime.time(SHIFT_START_HOUR))
            continue
        # hours already used today (relative to shift start)
        shift_start=datetime.datetime.combine(day, datetime.time(SHIFT_START_HOUR))
        if cur<shift_start: cur=shift_start
        used_today=(cur-shift_start).total_seconds()/3600.0
        avail_today=max(0.0, cap-used_today)
        if avail_today<=0:
            cur=datetime.datetime.combine(day+timedelta(days=1), datetime.time(SHIFT_START_HOUR)); continue
        take=min(remaining, avail_today)
        cur=cur+timedelta(hours=take)
        remaining-=take
        if remaining>1e-6:
            cur=datetime.datetime.combine(day+timedelta(days=1), datetime.time(SHIFT_START_HOUR))
    return cur

def add_cure_hours(start_dt, hours):
    """Cures elapse 24/7 wall-clock, incl nights & weekends."""
    return start_dt + timedelta(hours=hours)

def forward_schedule(ops, cures, start_op, start_dt, as_of=None):
    """Walk router from the op AFTER start_op (current position) to end.
    Returns list of rows: (op_no|None, kind, label, start_dt, finish_dt).
    kind in {labor, cure}. Cures inserted after their after_op."""
    # support MULTIPLE cures per after_op (radome op 170/410 each have cure + gate)
    cure_by_after={}
    for c in cures:
        cure_by_after.setdefault(c[0],[]).append(c)
    rows=[]
    cur=start_dt
    from routers import crew
    for (opno,desc,wc,hrs,ms) in ops:
        if opno<=start_op:
            continue
        s=cur
        f=add_labor_hours(s, hrs/crew(wc,opno))
        rows.append((opno,"labor",desc,s,f,wc,hrs,ms))
        cur=f
        # cure(s) that follow THIS op, in listed order
        for (_,clabel,dwell,cnote) in cure_by_after.get(opno,[]):
            cs=cur
            cf=add_cure_hours(cs, dwell)
            rows.append((None,"cure",clabel,cs,cf,"",dwell,ms))
            cur=cf
    return rows

if __name__=="__main__":
    # VERIFY against RH 227 (SO 1452749), currently at op 3700 (aero seal), clocked 8/18.
    # Forward-project its finish incl. remaining cures. Firm ship = Friday.
    as_of=DT(2026,8,18,12,0)   # midday today
    start_op=3700              # last op with clocking
    rows=forward_schedule(ELEVATOR_OPS, ELEVATOR_CURES, start_op, as_of)
    print("RH 227 (SO 1452749) forward projection from op 3700 @ 8/18 12:00")
    print(f"{'OP':>6} {'KIND':5} {'START':16} {'FINISH':16}  DESC")
    for r in rows:
        opno,kind,desc,s,f,wc,hrs,ms=r
        print(f"{(opno or '  cure'):>6} {kind:5} {s.strftime('%a %m/%d %H:%M'):16} {f.strftime('%a %m/%d %H:%M'):16}  {desc[:40]}")
    fin=rows[-1][4]
    print(f"\nPROJECTED FINISH (pack&ship): {fin.strftime('%A %m/%d %H:%M')}")
    print("Firm ship target: Friday 8/21")

    # ---- RADOME verify: SO 1456255 at op 621 (mid-assembly), clocked 8/17 ----
    print("\n"+"="*60)
    print("RADOME SO 1456255 forward projection from op 621 @ 8/17 12:00")
    rrows=forward_schedule(RADOME_OPS, RADOME_CURES, 621, DT(2026,8,17,12,0))
    print(f"{'OP':>6} {'KIND':5} {'START':16} {'FINISH':16}  DESC")
    for r in rrows:
        opno,kind,desc,s,f,wc,hrs,ms=r
        print(f"{(opno or '  cure'):>6} {kind:5} {s.strftime('%a %m/%d %H:%M'):16} {f.strftime('%a %m/%d %H:%M'):16}  {desc[:40]}")
    print(f"\nPROJECTED FINISH (pack&ship): {rrows[-1][4].strftime('%A %m/%d %H:%M')}")
