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
from datetime import datetime as DT, date, timedelta

from app.engines.occupancy import (
    OccupancyAllocator,
    OccupancyRequest,
    ResourceAllocationDeadlock,
)

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


class MissingPhysicalResource(RuntimeError):
    """A registry-driven run reached an operation without a governed pool."""


class InvalidPhysicalResourceProfile(RuntimeError):
    """A physical pool is present but its budget or calendar is unusable."""

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

def simulate(units, ops_map, cures_map, as_of, profile=None, trace_constraints=False):
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
    allocation_mode = profile.get("allocation_mode", "LEGACY_COMPAT")
    operation_pools = profile.get("operation_pools", {})
    pool_shift_budgets = profile.get("pool_shift_budgets", {})
    pool_external_reserves = profile.get("pool_external_reserves", {})
    pool_calendar_policies = profile.get("pool_calendar_policies", {})
    occupancy_requirements = profile.get("occupancy_requirements", {})
    occupancy_pool_capacities = profile.get("occupancy_pool_capacities", {})
    occupancy_pool_instances = profile.get("occupancy_pool_instances", {})
    occupancy_unavailable_intervals = profile.get("occupancy_unavailable_intervals", {})
    finite_cure_stations = {
        station: int(capacity)
        for station, capacity in cure_station_capacities.items()
        if int(capacity) > 0
    }
    all_occupancy_capacities = dict(finite_cure_stations)
    for pool_code, capacity in occupancy_pool_capacities.items():
        if (pool_code in all_occupancy_capacities
                and all_occupancy_capacities[pool_code] != int(capacity)):
            raise ResourceAllocationDeadlock(
                f"Conflicting capacities for occupancy pool {pool_code}")
        all_occupancy_capacities[pool_code] = int(capacity)
    occupancy_allocator = OccupancyAllocator(
        all_occupancy_capacities,
        instances=occupancy_pool_instances,
        as_of=as_of,
    )
    for pool_code, rows in sorted(occupancy_unavailable_intervals.items()):
        for row in sorted(rows, key=lambda item: (
                item["start"], item["end"], item.get("instance_code") or "")):
            occupancy_allocator.add_unavailability(
                pool_code,
                DT.fromisoformat(row["start"]),
                DT.fromisoformat(row["end"]),
                reason=row["reason"],
                instance_code=row.get("instance_code"),
            )
    def crew_for(program, wc, opno):
        return float(crew_by_program.get(program, {}).get(opno, legacy_crew(wc, opno)))

    def reserve_cure_station(unit_key, station, requested_start, dwell_hours):
        if not station or station not in finite_cure_stations:
            return requested_start, None
        reservation = occupancy_allocator.reserve_fixed(
            unit_key, [OccupancyRequest(station)], requested_start, dwell_hours)
        return reservation.start, reservation

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
                    q.append(['pgate', clabel, gop, float(dwell), clabel, None, opno])
                else:
                    q.append(['cure', clabel, '', float(dwell), clabel, station, opno])
        return q

    state={}
    for u in units:
        q=build_queue(u['program'], u['maxop'])
        release_at = u.get('release_at')
        if isinstance(release_at, date) and not isinstance(release_at, DT):
            release_at = DT.combine(release_at, datetime.time(SHIFT_START))
        release_at = release_at or as_of
        state[u['serial']]=dict(u=u, queue=q, idx=0,
                                cure_until=None,  # datetime a cure finishes
                                cure_trigger_op=None,
                                release_at=release_at,
                                clock=max(as_of, release_at),
                                gate_nb={},       # gate_op -> datetime the op cannot start before
                                op_dt={}, cure_dt={}, finish=None,
                                constraint_events=[],
                                occupancy_acquired_ops=set(),
                                occupancy_holds=[])

    def occupancy_rows(program, opno):
        return tuple(occupancy_requirements.get((program, opno), ()))

    def release_occupancy(serial, st, event, opno, at):
        matches = [
            row for row in st["occupancy_holds"]
            if row["release_event"] == event
            and (row.get("release_op") is None or row.get("release_op") == opno)
        ]
        for pool_code in sorted({row["pool_code"] for row in matches}):
            effective = occupancy_allocator.release(serial, pool_code, at)
            if trace_constraints:
                st["constraint_events"].append({
                    "event_type": "OCCUPANCY_RELEASE",
                    "pool_code": pool_code,
                    "operation_no": opno,
                    "work_center_no": None,
                    "wait_start": at,
                    "wait_end": effective,
                    "wait_hours": max(
                        0.0, (effective - at).total_seconds() / 3600.0),
                })
        if matches:
            released = {(row["pool_code"], row.get("release_event"), row.get("release_op"))
                        for row in matches}
            st["occupancy_holds"] = [
                row for row in st["occupancy_holds"]
                if (row["pool_code"], row.get("release_event"), row.get("release_op"))
                not in released
            ]

    def occupancy_requests(rows):
        return [
            OccupancyRequest(
                row["pool_code"], quantity=int(row.get("quantity", 1)),
                instance_code=row.get("instance_code"),
                min_hold_hours=float(row.get("min_hold_hours", 0.0)),
                lag_hours=float(row.get("lag_hours", 0.0)),
            )
            for row in rows
        ]
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
        if allocation_mode == "PHYSICAL":
            return (0 if dpas_behind else 1, commit, u.get('program', ''), u['serial'])
        return (0 if dpas_behind else 1, commit, u['serial'])
    order=sorted(units, key=prio)
    serial_order=[u['serial'] for u in order]

    def held_at_as_of(row, acquire_op, maxop):
        if maxop is None or maxop < acquire_op:
            return False
        event = row["release_event"]
        release_op = row.get("release_op")
        if event == "ROUTE_COMPLETE":
            return True
        if release_op is None:
            return False
        if event == "CURE_COMPLETE":
            return maxop <= release_op
        return maxop < release_op

    # Reconstruct conservative leases for units already between acquire/release operations.
    for serial in serial_order:
        st = state[serial]
        program = st["u"]["program"]
        maxop = st["u"].get("maxop")
        for (bound_program, acquire_op), rows in sorted(occupancy_requirements.items()):
            if bound_program != program:
                continue
            held_rows = [
                row for row in rows if held_at_as_of(row, acquire_op, maxop)
            ]
            if not held_rows:
                continue
            acquired = occupancy_allocator.acquire_atomic(
                serial, occupancy_requests(held_rows), as_of)
            if acquired is None:
                pools = sorted({row["pool_code"] for row in held_rows})
                raise ResourceAllocationDeadlock(
                    f"As-of WIP requires unavailable occupancy pools for {serial}: {pools}")
            st["occupancy_acquired_ops"].add(acquire_op)
            st["occupancy_holds"].extend(held_rows)

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
            # Per-shift budget buckets. Legacy-compatible profiles retain the established
            # (program, WC) behavior. Physical profiles key the budget by immutable pool code,
            # so differently named WCs can contend for one real resource.
            budget={}
            budget_meta={}

            def raw_budget(prog, wc):
                shifts = shift_budgets.get((prog, wc))
                if shifts is not None:
                    return shifts.get(shn, 0)
                return wc_shift_budget(prog, wc, shn)

            def physical_day_fac(pool_code, prog):
                policy = pool_calendar_policies.get(pool_code) or {}
                if not policy and pool_code.startswith("LEGACY:"):
                    return day_fac(prog, dd)
                if policy.get("mode") != "WEEKDAY_FACTORS":
                    raise InvalidPhysicalResourceProfile(
                        f"Physical pool {pool_code} has no WEEKDAY_FACTORS calendar")
                factors = policy.get("factors") or {}
                covered_until = policy.get("covered_until")
                if covered_until and dd > date.fromisoformat(covered_until):
                    raise InvalidPhysicalResourceProfile(
                        f"Physical pool {pool_code} calendar ends before {dd.isoformat()}")
                exceptions = policy.get("exceptions") or {}
                value = exceptions.get(dd.isoformat())
                if value is None:
                    value = factors.get(str(dd.weekday()), factors.get(dd.weekday()))
                if value is None:
                    raise InvalidPhysicalResourceProfile(
                        f"Physical pool {pool_code} has no factor for weekday {dd.weekday()}")
                return float(value)

            def getb(prog, wc, opno):
                if allocation_mode == "PHYSICAL":
                    pool_code = operation_pools.get((prog, opno))
                    if not pool_code:
                        raise MissingPhysicalResource(
                            f"{prog} operation {opno} ({wc}) has no physical pool binding")
                    shifts = pool_shift_budgets.get(pool_code)
                    if shifts is None:
                        raise InvalidPhysicalResourceProfile(
                            f"Physical pool {pool_code} has no shift budget")
                    pk=("_POOL_", pool_code)
                    if pk not in budget:
                        factor = physical_day_fac(pool_code, prog)
                        gross = float(shifts.get(shn, 0.0)) * factor
                        reserve_shifts = pool_external_reserves.get(pool_code, {})
                        reserve = float(reserve_shifts.get(shn, 0.0)) * factor
                        schedulable = max(0.0, gross - reserve)
                        budget[pk] = schedulable
                        budget_meta[pk] = (gross, reserve, schedulable, pool_code)
                    budget[(prog, wc, opno)] = pk
                    return budget[pk]
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
            def useb(prog, wc, opno, amt):
                key = ((prog, wc, opno) if allocation_mode == "PHYSICAL"
                       else (prog, wc))
                b=budget[key]
                pk=b if isinstance(b,tuple) else key
                budget[pk]=budget[pk]-amt

            def record_wait(st, prog, opno, wc, wait_start, wait_end,
                            requested_hours, allocated_hours):
                if not trace_constraints or allocation_mode != "PHYSICAL":
                    return
                pk = budget[(prog, wc, opno)]
                gross, reserve, schedulable, pool_code = budget_meta[pk]
                st["constraint_events"].append({
                    "event_type": ("OVERSUBSCRIBED" if reserve > gross
                                   else "CAPACITY_WAIT"),
                    "pool_code": pool_code,
                    "operation_no": opno,
                    "work_center_no": wc,
                    "wait_start": wait_start,
                    "wait_end": wait_end,
                    "wait_hours": max(
                        0.0, (wait_end - wait_start).total_seconds() / 3600.0),
                    "gross_capacity": gross,
                    "external_reserve": reserve,
                    "schedulable_capacity": schedulable,
                    "requested_hours": requested_hours,
                    "allocated_hours": allocated_hours,
                })

            # Extra deterministic passes let an earlier-priority waiter retry after a holder
            # releases later in the same shift. Legacy runs retain their single pass exactly.
            shift_order = (serial_order * (len(serial_order) + 1)
                           if occupancy_pool_capacities else serial_order)
            for s in shift_order:
                st=state[s]
                if st['finish'] is not None:
                    continue
                prog=unit_prog[s]
                if st['release_at'] >= sh_close:
                    continue
                fac=(1.0 if allocation_mode == "PHYSICAL" else day_fac(prog, dd))
                if fac<=0:  # program not working this day (e.g. elevator off-weekend)
                    continue
                # if unit is in a cure, check if done (cures 24/7 wall-clock)
                if st['cure_until'] is not None:
                    if st['cure_until'] <= sh_close:
                        st['clock']=max(st['cure_until'], sh_open)
                        st['cure_until']=None
                        release_occupancy(
                            s, st, "CURE_COMPLETE", st["cure_trigger_op"], st['clock'])
                        st["cure_trigger_op"] = None
                    else:
                        continue  # still curing through this shift
                else:
                    st['clock']=max(sh_open, as_of, st['release_at'], st['clock'])
                if st['clock']>=sh_close:
                    continue
                # advance through queue within this shift
                while st['idx'] < len(st['queue']):
                    item=st['queue'][st['idx']]
                    if item[0]=='op':
                        _,opno,wc,hrs,desc=item
                        release_occupancy(s, st, "OP_START", opno, st['clock'])
                        rows = occupancy_rows(prog, opno)
                        if rows and opno not in st["occupancy_acquired_ops"]:
                            requests = occupancy_requests(rows)
                            acquired = occupancy_allocator.acquire_atomic(
                                s, requests, st['clock'])
                            if acquired is None:
                                available_at = occupancy_allocator.next_available_at(
                                    requests, st['clock'])
                                wait_end = min(available_at, sh_close)
                                if trace_constraints:
                                    for pool_code in sorted({
                                            request.pool_code for request in requests
                                    }):
                                        st["constraint_events"].append({
                                            "event_type": "OCCUPANCY_WAIT",
                                            "pool_code": pool_code,
                                            "operation_no": opno,
                                            "work_center_no": wc,
                                            "wait_start": st['clock'],
                                            "wait_end": wait_end,
                                            "wait_hours": max(
                                                0.0, (wait_end - st['clock']).total_seconds()
                                                / 3600.0),
                                            "requested_slots": sum(
                                                request.quantity for request in requests
                                                if request.pool_code == pool_code),
                                            "allocated_slots": 0,
                                        })
                                if available_at < sh_close:
                                    st['clock'] = available_at
                                    continue
                                break
                            st["occupancy_acquired_ops"].add(opno)
                            st["occupancy_holds"].extend(rows)
                            if trace_constraints:
                                for lease in acquired:
                                    st["constraint_events"].append({
                                        "event_type": "OCCUPANCY_ACQUIRE",
                                        "pool_code": lease.pool_code,
                                        "operation_no": opno,
                                        "work_center_no": wc,
                                        "wait_start": lease.acquired_at,
                                        "wait_end": lease.min_release_at,
                                        "wait_hours": 0.0,
                                        "instance_code": lease.instance_code,
                                    })
                        nb=st['gate_nb'].get(opno)
                        if nb is not None and st['clock'] < nb:
                            if nb <= sh_close:
                                st['clock']=max(nb, st['clock'])
                            else:
                                st['cure_until']=nb
                                break
                        if opno not in st['op_dt']:
                            st['op_dt'][opno]=st['clock']
                        avail=getb(prog, wc, opno)
                        shift_left=(sh_close-st['clock']).total_seconds()/3600.0
                        if avail<=0.01 or shift_left<=0.01:
                            if avail <= 0.01 and shift_left > 0.01:
                                record_wait(
                                    st, prog, opno, wc, st['clock'], sh_close,
                                    requested_hours=item[3], allocated_hours=0.0,
                                )
                            break  # WC out of hours this shift, or shift over
                        requested = item[3]
                        take=min(item[3], avail, shift_left)
                        useb(prog, wc, opno, take)
                        item[3]-=take
                        st['clock']=st['clock']+timedelta(hours=take)
                        if item[3]<=0.01:
                            st['idx']+=1
                            release_occupancy(
                                s, st, "OP_COMPLETE", opno, st['clock'])
                        else:
                            if getb(prog, wc, opno) <= 0.01 and st['clock'] < sh_close:
                                record_wait(
                                    st, prog, opno, wc, st['clock'], sh_close,
                                    requested_hours=requested, allocated_hours=take,
                                )
                            break
                    elif item[0]=='pgate':
                        _,clabel,gop,dwell,_,_station,_trigger_op=item
                        cs=st['clock']
                        st['cure_dt'][clabel]=cs
                        st['gate_nb'][gop]=cs+timedelta(hours=dwell)
                        st['idx']+=1
                    else:  # serial cure
                        _,clabel,_,dwell,_,station,trigger_op=item
                        cs, occupancy = reserve_cure_station(
                            s, station, st['clock'], dwell)
                        if trace_constraints and occupancy and occupancy.wait_hours > 0:
                            st["constraint_events"].append({
                                "event_type": "OCCUPANCY_WAIT",
                                "pool_code": station,
                                "operation_no": None,
                                "work_center_no": None,
                                "wait_start": occupancy.requested_start,
                                "wait_end": occupancy.start,
                                "wait_hours": occupancy.wait_hours,
                                "requested_slots": 1,
                                "allocated_slots": 1,
                            })
                        st['cure_dt'][clabel] = cs
                        st['cure_until'] = cs + timedelta(hours=dwell)
                        st["cure_trigger_op"] = trigger_op
                        release_occupancy(
                            s, st, "CURE_COMPLETE", trigger_op, st['cure_until'])
                        st["cure_trigger_op"] = None
                        st['idx']+=1
                        break
                if st['idx']>=len(st['queue']) and st['cure_until'] is None:
                    release_occupancy(s, st, "ROUTE_COMPLETE", None, st['clock'])
                    if st["occupancy_holds"]:
                        held = sorted({row["pool_code"] for row in st["occupancy_holds"]})
                        raise ResourceAllocationDeadlock(
                            f"Unit {s} completed with unreleased occupancy pools: {held}")
                    st['finish']=st['clock']
        dd=dd+timedelta(days=1)
    unfinished = [serial for serial, item in state.items() if item['finish'] is None]
    if unfinished and occupancy_pool_capacities:
        raise ResourceAllocationDeadlock(
            "Occupancy-constrained schedule made no complete progress within 1,200 shifts: "
            + ", ".join(unfinished))
    if unfinished and allocation_mode == "PHYSICAL":
        raise InvalidPhysicalResourceProfile(
            "Physical resource profile made no complete schedule within 1,200 shifts: "
            + ", ".join(unfinished))
    # finalize
    out={}
    for s,st in state.items():
        fin=st['finish'] or (st['cure_until'] or cur)
        out[s]=dict(finish=fin, op_dt=st['op_dt'], cure_dt=st['cure_dt'])
        if trace_constraints:
            out[s]["constraint_events"] = st["constraint_events"]
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
