"""Finite-capacity multi-unit scheduler for the RTG tracker.

Replaces the naive per-unit projection (which assumed every WIP unit gets full
labor every day in parallel). Instead: all WIP units advance simultaneously but
COMPETE for a shared per-work-center daily hour budget, drawn in commit-date
priority order. Cures run 24/7 wall-clock and do NOT consume WC labor hours. Selected paint and
cure-station dwells reserve discrete physical slots before they can begin.

Measured WC daily budgets (Aug 4-19 actuals, 11 working days) — real sustained
throughput, which is the right bottleneck constraint given current staffing.
"""
import datetime
from heapq import heapify, heappop, heappush
from datetime import datetime as DT, date, timedelta

# Per-WC daily labor-hour budget (measured sustained utilization). Floors applied
# to low-volume gate WCs so inspections/pack never artificially block the line.
WC_DAILY = {
 '32684':167.0,   # elevator main assembly
 'AEROL':40.0,    # radome layup
 '221':27.0,      # PAINT (elevator) — bottleneck
 'INSP':27.0,'32687':18.0,'P3 QA':8.0,'3FINL':8.0,  # QA (floored)
 'AEROA':20.0,    # radome assembly
 '236':12.0,      # PAINT (radome) — bottleneck
 '238':8.0,'ATUP':8.0,  # radome ovens (labor portion)
 '248':8.0,'235':8.0,'P2PCK':8.0,  # mark/ship (floored)
}
DEFAULT_WC = 12.0  # any WC not listed

SHIFT_START = 6

def wc_budget(wc):
    return WC_DAILY.get(wc, DEFAULT_WC)

def is_workday(dd):
    return dd.weekday() < 6  # Mon-Sat worked (Sat reduced handled by 0.5 factor)

def day_factor(dd):
    wd=dd.weekday()
    if wd<5:
        return 1.0
    if wd==5:
        return 0.5
    return 0.25

def simulate(units, ops_map, cures_map, as_of, profile=None):
    """units: list of dicts {serial, so, maxop, commit, program}
       ops_map: program -> ops list; cures_map: program -> cures list
    Returns: per-serial {finish, op_dt{opno:start_dt}, cure_dt{label:start_dt}, stalled}
    Day-stepped finite-capacity sim: each working day, distribute each WC's hour
    budget to units in commit-date order; a unit advances through labor ops until
    it hits a cure (24/7 dwell) or runs out of that day's WC hours."""
    from routers import (
        crew as legacy_crew,
        PARALLEL_CURE_GATES,
        CURE_STATION_CAPACITIES,
        CURE_STATION_RULES,
    )
    profile = profile or {}
    crew_by_program = profile.get("crew_by_program", {})
    cure_station_rules = profile.get("cure_station_rules", CURE_STATION_RULES)
    cure_station_capacities = profile.get("cure_station_capacities", CURE_STATION_CAPACITIES)
    parallel_cure_gates = profile.get("parallel_cure_gates", PARALLEL_CURE_GATES)
    cure_station_slots = {}
    for station, capacity in cure_station_capacities.items():
        if int(capacity) > 0:
            slots = [as_of] * int(capacity)
            heapify(slots)
            cure_station_slots[station] = slots
    def crew_for(program, wc, opno):
        return float(crew_by_program.get(program, {}).get(opno, legacy_crew(wc, opno)))

    def reserve_cure_station(station, requested_start, dwell_hours):
        if not station or station not in cure_station_slots:
            return requested_start
        slots = cure_station_slots[station]
        available_at = heappop(slots)
        start_at = max(requested_start, available_at)
        heappush(slots, start_at + timedelta(hours=dwell_hours))
        return start_at

    def gate_op_for(label):
        for sub,gop in parallel_cure_gates.items():
            if sub in label:
                return gop
        return None
    # Build per-unit remaining op queue. Labor hrs divided by crew factor (floor runs
    # multi-operator on big paint/seal ops — ERP router is serial CREW_SIZE=1).
    # Parallel-gate cures ('pgate') don't block the unit; they set a not-before time
    # on their gate op (e.g. topcoat 24hr must elapse before final inspection).
    def build_queue(program, maxop):
        ops=ops_map[program]
        cures=cures_map[program]
        cby={}
        for c in cures:
            cby.setdefault(c[0],[]).append(c)
        q=[]
        for (opno,desc,wc,hrs,ms) in ops:
            if maxop is not None and opno<=maxop:
                continue
            eff_hrs=float(hrs)/max(1.0, crew_for(program, wc, opno))
            q.append(['op',opno,wc,eff_hrs,desc])
            for (_,clabel,dwell,cnote) in cby.get(opno,[]):
                gop = gate_op_for(clabel)
                station = cure_station_rules.get((program, opno, clabel))
                if gop is not None:
                    # Parallel gates are not cure-station reservations.
                    q.append(['pgate', clabel, gop, float(dwell), clabel, None])
                else:
                    q.append(['cure', clabel, '', float(dwell), clabel, station])
        return q

    state={}
    for u in units:
        q=build_queue(u['program'], u['maxop'])
        state[u['serial']]=dict(u=u, queue=q, idx=0,
                                cure_until=None,  # datetime a cure finishes
                                clock=as_of,      # per-unit intra-day work clock
                                gate_nb={},       # gate_op -> datetime the op cannot start before
                                op_dt={}, cure_dt={}, finish=None)
    # priority: DPAS-rated programs that are BEHIND contract jump the queue for shared
    # capacity (e.g. Aegis shares paint booth WC221 + ovens with elevator and is DPAS-rated).
    # Then earliest commit first (None commit last).
    from routers import DPAS_PROGRAMS
    dpas_programs = set(profile.get("dpas_programs", DPAS_PROGRAMS))
    as_of_d = as_of.date()
    def prio(u):
        commit = u['commit'] or date(2099,1,1)
        behind = 1 if (u['commit'] and u['commit'] < as_of_d) else 0
        dpas_behind = (u.get('program') in dpas_programs) and behind
        # sort key: DPAS-behind units first (0), then by commit date, then serial
        return (0 if dpas_behind else 1, commit, u['serial'])
    order=sorted(units, key=prio)
    serial_order=[u['serial'] for u in order]

    # ---- PER-SHIFT stepping ----
    # Each day = 3 shifts (1:0600-1400, 2:1400-2200, 3:2200-0600 next). Each shift has its
    # own per-(program,wc,shift) hour budget (WC_SHIFT). Elevator weekends follow the
    # 2-on/1-off OT rotation (elevator_weekend_factor); radome/Aegis weekends at reduced rate.
    from routers import wc_shift_budget, elevator_weekend_factor, SHARED_WC
    shared_wcs = set(profile.get("shared_wcs", SHARED_WC))
    shift_budgets = profile.get("shift_budgets", {})
    budget_programs = list(profile.get("budget_programs") or
                           sorted({u.get("program") for u in units if u.get("program")}))
    SHIFTS=[(1,6,8),(2,14,8),(3,22,8)]  # (shift#, start_hour, span_hours)
    unit_prog={s: state[s]['u'].get('program') for s in state}
    def day_fac(prog, dd):
        if prog=='ELEV':
            return elevator_weekend_factor(dd)  # weekday 1.0, OT wknd 0.85, off wknd 0.0
        wd=dd.weekday()
        return 1.0 if wd<5 else (0.5 if wd==5 else 0.25)

    cur=as_of.replace(hour=SHIFT_START, minute=0, second=0, microsecond=0)
    if cur < as_of:
        cur = as_of
    maxsteps=1200
    dd=cur.date()
    while maxsteps>0 and any(state[s]['finish'] is None for s in state):
        for (shn, sh_start_hr, sh_span) in SHIFTS:
            maxsteps-=1
            # shift window datetimes (shift 3 starts 2200 same day, spans into next)
            sh_open=DT.combine(dd, datetime.time(sh_start_hr))
            sh_close=sh_open+timedelta(hours=sh_span)
            if sh_close <= as_of:
                continue  # shift already past
            # Per-shift WC budget buckets. The profile keeps legacy router budgets as the
            # fallback, but shared resources are derived from the active registry rather than
            # the seed-only SHARED_WC list.
            budget={}

            def raw_budget(prog, wc):
                shifts = shift_budgets.get((prog, wc))
                if shifts is not None:
                    return shifts.get(shn, 0)
                return wc_shift_budget(prog, wc, shn)

            def getb(prog, wc):
                key=(prog, wc)
                if key not in budget:
                    if wc in shared_wcs:
                        pk=('_SHARED_', wc)
                        if pk not in budget:
                            contributors = [p for p in budget_programs
                                            if (p, wc) in shift_budgets]
                            if contributors:
                                tot=sum(raw_budget(p, wc)*day_fac(p,dd) for p in contributors)
                            else:
                                # No existing resource profile: one default WC pool, not one
                                # default pool per program, so newly shared WCs really contend.
                                tot=raw_budget(prog, wc)*day_fac(prog,dd)
                            budget[pk]=tot
                        budget[key]=pk
                        return budget[pk]
                    budget[key]=raw_budget(prog, wc)*day_fac(prog,dd)
                b=budget[key]
                return budget[b] if isinstance(b,tuple) else b
            def useb(prog, wc, amt):
                key=(prog,wc)
                b=budget[key]
                pk=b if isinstance(b,tuple) else key
                budget[pk]=budget[pk]-amt

            for s in serial_order:
                st=state[s]
                if st['finish'] is not None:
                    continue
                prog=unit_prog[s]
                fac=day_fac(prog, dd)
                if fac<=0:  # program not working this day (e.g. elevator off-weekend)
                    continue
                # if unit is in a cure, check if done (cures 24/7 wall-clock)
                if st['cure_until'] is not None:
                    if st['cure_until'] <= sh_close:
                        st['clock']=max(st['cure_until'], sh_open)
                        st['cure_until']=None
                    else:
                        continue  # still curing through this shift
                else:
                    st['clock']=max(sh_open, as_of, st['clock'])
                if st['clock']>=sh_close:
                    continue
                # advance through queue within this shift
                while st['idx'] < len(st['queue']):
                    item=st['queue'][st['idx']]
                    if item[0]=='op':
                        _,opno,wc,hrs,desc=item
                        nb=st['gate_nb'].get(opno)
                        if nb is not None and st['clock'] < nb:
                            if nb <= sh_close:
                                st['clock']=max(nb, st['clock'])
                            else:
                                st['cure_until']=nb
                                break
                        if opno not in st['op_dt']:
                            st['op_dt'][opno]=st['clock']
                        avail=getb(prog, wc)
                        shift_left=(sh_close-st['clock']).total_seconds()/3600.0
                        if avail<=0.01 or shift_left<=0.01:
                            break  # WC out of hours this shift, or shift over
                        take=min(item[3], avail, shift_left)
                        useb(prog, wc, take)
                        item[3]-=take
                        st['clock']=st['clock']+timedelta(hours=take)
                        if item[3]<=0.01:
                            st['idx']+=1
                        else:
                            break
                    elif item[0]=='pgate':
                        _,clabel,gop,dwell,_,_station=item
                        cs=st['clock']
                        st['cure_dt'][clabel]=cs
                        st['gate_nb'][gop]=cs+timedelta(hours=dwell)
                        st['idx']+=1
                    else:  # serial cure
                        _,clabel,_,dwell,_,station=item
                        cs = reserve_cure_station(station, st['clock'], dwell)
                        st['cure_dt'][clabel] = cs
                        st['cure_until'] = cs + timedelta(hours=dwell)
                        st['idx']+=1
                        break
                if st['idx']>=len(st['queue']) and st['cure_until'] is None:
                    st['finish']=st['clock']
        dd=dd+timedelta(days=1)
    # finalize
    out={}
    for s,st in state.items():
        fin=st['finish'] or (st['cure_until'] or cur)
        out[s]=dict(finish=fin, op_dt=st['op_dt'], cure_dt=st['cure_dt'])
    return out


if __name__=="__main__":
    from routers import ELEVATOR_OPS, ELEVATOR_CURES, RADOME_OPS, RADOME_CURES
    AS_OF=DT(2026,8,19,12,0)
    ops_map={'ELEV':ELEVATOR_OPS,'RAD':RADOME_OPS}
    cures_map={'ELEV':ELEVATOR_CURES,'RAD':RADOME_CURES}
    def d(m,dd): return date(2026,m,dd)
    # a few elevator units to sanity check contention
    units=[
     dict(serial='RH 227',so='1452749',maxop=3700,commit=d(8,21),program='ELEV'),
     dict(serial='LH 232',so='1455596',maxop=4000,commit=d(8,21),program='ELEV'),
     dict(serial='LH 233',so='1456550',maxop=3400,commit=d(8,28),program='ELEV'),
     dict(serial='RH 231',so='1456551',maxop=3400,commit=d(8,28),program='ELEV'),
     dict(serial='LH 229',so='1452748',maxop=3400,commit=d(9,4),program='ELEV'),
    ]
    res=simulate(units,ops_map,cures_map,AS_OF)
    for u in units:
        r=res[u['serial']]
        print(f"{u['serial']:8} commit {u['commit']}  finish {r['finish'].strftime('%a %m/%d %H:%M')}")
