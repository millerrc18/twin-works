"""Matrix view — ops down rows, units across columns, mirroring the Excel tracker.

Cell states per (op-row, unit):
  done   -> "C"   (op < maxop)
  wip    -> "WIP" (op == maxop)
  upcoming -> projected date (op > maxop, from sim op_dt)
  cure/gate rows -> projected window date (from sim cure_dt), or "C" if past
Milestone band rows separate the sections (LAM/ASSY/PAINT/SHIP, AJ/A1/A2/FS).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from app.data.source import DataSource
from app.data import rtg_targets
from app.engines.rtg_wrapper import run_pooled
from app.engines.router_registry import registry
from ml.model.registry import registry_model
from ml.model.features import FeatureBuilder

_fb = FeatureBuilder()


def _display_rows(program):
    """Ordered rows: ('ms', code, name) | ('op', opno, desc, wc, hr) | ('cure'|'gate', opno, label, dwell)."""
    spec = registry.spec(program)
    cure_by_after = {}
    for c in spec.cures:
        cure_by_after.setdefault(c[0], []).append(c)
    ms_names = dict(spec.milestones)
    rows = []
    last_ms = None
    for (opno, desc, wc, hr, ms) in spec.ops:
        if ms != last_ms:
            rows.append(("ms", ms, ms_names.get(ms, ms)))
            last_ms = ms
        rows.append(("op", opno, desc, wc, hr, ms))
        for (_after, clabel, dwell, _note) in cure_by_after.get(opno, []):
            kind = "gate" if clabel.upper().startswith("GATE") else "cure"
            rows.append((kind, opno, clabel, dwell, ms))
    return rows


@dataclass
class MatrixUnit:
    serial: str
    so: str
    maxop: int | None
    commit: date | None     # contract (IFS due) — reference
    rtg: date | None        # RTG ship target (primary; None for Aegis/no-plan)
    target: date | None     # the target Δ is measured against (rtg if present else commit)
    target_kind: str        # "RTG" | "contract"
    earliest: date | None
    forecast: date | None   # p50 (de-biased)
    p80: date | None
    delta: int | None       # forecast vs target
    stalled: bool
    idle_days: int | None
    slip: int | None = None  # week-over-week: forecast move since last build (+later/-earlier)


def build_matrix(ds: DataSource, program: str, slots=None, flt: str = "all") -> dict:
    """Slot-anchored matrix. `slots` = list of SlotAssignment rows (from slot_service).
    Columns are arranged by delivery slot (fixed target, hand group), each showing the
    currently-assigned serial's live data + Δ vs the slot's fixed target. WIP serials not
    filling any slot go in an 'unassigned' group at the right. Aegis (no slots) is
    serial-anchored, sorted by contract."""
    spec = registry.spec(program)
    elev = [u.as_sim_unit() for u in ds.get_wip_units("ELEV") if not u.stalled]
    aeg = [u.as_sim_unit() for u in ds.get_wip_units("AEGIS") if not u.stalled]
    rad = [u.as_sim_unit() for u in ds.get_wip_units("RAD") if not u.stalled]
    sim = run_pooled(elev, aeg, rad, ds.as_of())
    ops, cures = spec.ops, spec.cures

    # index live units by serial
    by_serial = {u.serial: u for u in ds.get_wip_units(program)}
    unit_cells = {}
    from app.services.slip_service import slip_by_serial
    slip_map = slip_by_serial()

    def make_unit(serial, slot_target=None):
        u = by_serial.get(serial)
        if u is None:
            return None
        rtg = rtg_targets.rtg_ship(serial)
        target = slot_target or rtg or u.commit
        target_kind = "RTG" if (slot_target or rtg) else "contract"
        feats = _fb.build(serial, u.so, program, u.maxop).model_features()
        pred = registry_model.predict(program, feats)
        if u.stalled:
            unit_cells[serial] = dict(stalled=True, maxop=u.maxop, op_dt={}, cure_dt={})
            return MatrixUnit(serial, u.so, u.maxop, u.commit, rtg, target, target_kind,
                              None, None, None, None, True, _idle(ds, u),
                              slip=slip_map.get(serial))
        r = sim.get(serial, {})
        fin = r.get("finish")
        sim_fin = fin.date() if fin else None
        p50 = p80 = delta = None
        if sim_fin:
            p50, p80 = registry_model.apply(sim_fin, pred)
            if target:
                delta = (p50 - target).days
        earliest = _earliest_single(ops, cures, u.maxop, ds.as_of())
        unit_cells[serial] = dict(stalled=False, maxop=u.maxop,
                                  op_dt=r.get("op_dt", {}), cure_dt=r.get("cure_dt", {}))
        return MatrixUnit(serial, u.so, u.maxop, u.commit, rtg, target, target_kind,
                          earliest, p50, p80, delta, False, None, slip=slip_map.get(serial))

    columns = []          # list of {kind:'slot'|'unit', hand, slot_id, target, unit(MatrixUnit|None)}
    groups = []           # list of {label, span} for the hand/section bands
    assigned = set()

    if slots:
        # slot-anchored: group by hand (LH, RH, '') then by target
        from itertools import groupby
        slots_sorted = sorted(slots, key=lambda s: (s.hand, s.target_date or date.max))
        # preserve hand order LH, RH, '' as they appear
        hand_order = []
        for s in slots_sorted:
            if s.hand not in hand_order:
                hand_order.append(s.hand)
        for hand in hand_order:
            hslots = [s for s in slots_sorted if s.hand == hand]
            start = len(columns)
            for s in hslots:
                mu = make_unit(s.serial, s.target_date) if s.serial else None
                if s.serial:
                    assigned.add(s.serial)
                columns.append(dict(kind="slot", hand=hand, slot_id=s.slot_id,
                                    target=s.target_date, unit=mu, serial=s.serial))
            label = (hand + " — RTG slots") if hand else "RTG slots"
            groups.append(dict(label=label, span=len(columns) - start))
        # unassigned WIP serials (not filling any slot)
        unassigned = [ser for ser in by_serial if ser not in assigned]
        unassigned.sort()
        if unassigned:
            start = len(columns)
            for ser in unassigned:
                mu = make_unit(ser)
                columns.append(dict(kind="unit", hand="", slot_id=None,
                                    target=(mu.target if mu else None), unit=mu, serial=ser))
            groups.append(dict(label="Unassigned / bumped", span=len(columns) - start))
    else:
        # serial-anchored (Aegis): sort by contract date
        sers = sorted(by_serial, key=lambda s: (by_serial[s].commit or date.max, s))
        for ser in sers:
            mu = make_unit(ser)
            columns.append(dict(kind="unit", hand="", slot_id=None,
                                target=(mu.target if mu else None), unit=mu, serial=ser))
        groups.append(dict(label="Units (by contract)", span=len(columns)))

    # optional filter: behind (Δ>0) or active (not stalled). Rebuilds groups to match.
    if flt in ("behind", "active"):
        def keep(c):
            u = c.get("unit")
            if u is None:
                return False
            if flt == "active":
                return not u.stalled
            return (not u.stalled) and (u.delta is not None and u.delta > 0)
        # recompute group spans over the kept columns, preserving order
        kept, new_groups, gi = [], [], 0
        idx = 0
        for g in groups:
            start = len(kept)
            for _ in range(g["span"]):
                if keep(columns[idx]):
                    kept.append(columns[idx])
                idx += 1
            span = len(kept) - start
            if span:
                new_groups.append(dict(label=g["label"], span=span))
        columns, groups = kept, new_groups

    # mark the first column of each group (for the LH/RH/unassigned visual separator)
    idx = 0
    for gi, g in enumerate(groups):
        for k in range(g["span"]):
            columns[idx]["first_in_group"] = (k == 0 and gi > 0)
            idx += 1

    # build grid rows against the ordered columns
    all_serials = [c["serial"] for c in columns]
    rows = _display_rows(program)
    grid = []
    for row in rows:
        kind = row[0]
        if kind == "ms":
            grid.append(dict(kind="ms", code=row[1], name=row[2],
                             op_count=0, done_count=0))
            continue
        if kind == "op":
            _, opno, desc, wc, hr, ms = row
        else:
            _, opno, desc, hr, ms = row
            wc = ""
        cells = []
        for ser in all_serials:
            uc = unit_cells.get(ser)
            cells.append(_cell(kind, opno, desc, uc, ds.as_of()) if uc else dict(text="", state="blank", near=False, tw=False))
        # a row is "all done" if every non-blank cell is done (used for band collapse)
        real = [c for c in cells if c["state"] != "blank"]
        all_done = bool(real) and all(c["state"] == "done" for c in real)
        grid.append(dict(kind=kind, opno=(opno if kind == "op" else None),
                         desc=desc, wc=wc, hr=hr, ms=ms, all_done=all_done, cells=cells))

    # per-milestone stats for the collapse summary: total op rows + how many all-done
    band_stats = {}
    for g in grid:
        if g["kind"] == "ms":
            continue
        s = band_stats.setdefault(g["ms"], {"op_count": 0, "done_count": 0})
        s["op_count"] += 1
        if g["all_done"]:
            s["done_count"] += 1
    # a band is fully complete if every row in it is all-done
    for g in grid:
        if g["kind"] == "ms":
            s = band_stats.get(g["code"], {"op_count": 0, "done_count": 0})
            g["op_count"] = s["op_count"]
            g["done_count"] = s["done_count"]
            g["complete"] = s["op_count"] > 0 and s["done_count"] == s["op_count"]

    return dict(program=program, columns=columns, groups=groups, grid=grid,
                slotted=bool(slots),
                today_iso=ds.as_of().date().isoformat(),
                model_status=registry_model.predict(program).mode,
                cure_floor_days=round(sum(c[2] for c in cures) / 24.0, 1))


def _near(dt, as_of, days=10):
    """True if a projected date is within `days` of as-of — near-term work to emphasize."""
    try:
        return (dt.date() - as_of.date()).days <= days
    except Exception:
        return False


def _this_week(dt, as_of):
    """True if the date falls in the same Mon–Sun week as as-of (the 'today' reference band)."""
    try:
        d, a = dt.date(), as_of.date()
        wk_start = a - timedelta(days=a.weekday())
        return wk_start <= d <= wk_start + timedelta(days=6)
    except Exception:
        return False


def _cell(kind, opno, desc, uc, as_of):
    """Return (text, state, near) for one grid cell.
    state in done|wip|upcoming|cure|gate|blank. `near` weights near-term upcoming dates.
    Cure/gate cells show DATE ONLY (per-unit time-of-day was the biggest visual-noise source)."""
    maxop = uc["maxop"]
    if uc["stalled"]:
        return dict(text="", state="stall", near=False, tw=False)
    if kind in ("cure", "gate"):
        if maxop is not None and opno < maxop:
            return dict(text="C", state="done", near=False, tw=False)
        cdt = uc["cure_dt"].get(desc)
        return dict(text=(cdt.strftime("%m/%d") if cdt else ""), state=kind,
                    near=_near(cdt, as_of) if cdt else False,
                    tw=_this_week(cdt, as_of) if cdt else False)
    # op row
    if maxop is None:
        pdt = uc["op_dt"].get(opno)
        return dict(text=(pdt.strftime("%m/%d") if pdt else ""), state="upcoming",
                    near=_near(pdt, as_of) if pdt else False,
                    tw=_this_week(pdt, as_of) if pdt else False)
    if opno < maxop:
        return dict(text="C", state="done", near=False, tw=False)
    if opno == maxop:
        return dict(text="WIP", state="wip", near=False, tw=False)
    pdt = uc["op_dt"].get(opno)
    return dict(text=(pdt.strftime("%m/%d") if pdt else ""), state="upcoming",
                near=_near(pdt, as_of) if pdt else False,
                tw=_this_week(pdt, as_of) if pdt else False)


def _earliest_single(ops, cures, maxop, as_of):
    """Single-unit best-case finish (no contention) via forward_schedule. No side effects."""
    try:
        from schedule_engine import forward_schedule
        sop = -1 if maxop is None else maxop
        rows = forward_schedule(ops, cures, sop, as_of)
        return rows[-1][4].date() if rows else None
    except Exception:
        return None


def _idle(ds, u):
    from app.data import wip_tables as W
    lc = W.LAST_CLOCK.get(u.so)
    return (ds.as_of().date() - lc).days if lc else None
