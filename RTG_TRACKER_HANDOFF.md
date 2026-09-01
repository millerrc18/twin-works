# RTG Operation Tracker - Legacy Workbook Build & Update Handoff

> **Historical workbook handoff:** this document preserves the original Excel tracker update
> workflow. It is not the operating handoff for the current web application. For TwinWorks app
> architecture and working rules, read `MASTER.md` and `AGENTS.md` first.

## Current TwinWorks handoff (2026-08-31)

**Completed:** Feature #81 is through its local safety gate. The database-backed program registry,
IFS routing discovery, unknown-WC gate, and `/admin/programs` onboarding UI are implemented. The
62-test suite includes isolated onboarding, governance, replay, parity, serial/slot, and portfolio/
workspace regressions
that prove
pooling, draft
forecasting, exclusion from authoritative forecast stamping until publication, and no seed-forecast
drift. The seed golden master is now
40 static bootstrap WIP units for ELEV/RAD/AEGIS; it ignores mutable `PositionState` and extra
configured programs.
**Current capacity-model correction:** the app now derives shared WCs from active program routes and passes DB crew, DPAS, and shift-budget metadata into the scheduler. This intentionally replaces the old seed-only ELEV/Aegis `32678` shared-capacity assumption with the actual shared QA WC `32687`; the static 40-unit golden baseline was recaptured.

**Cure-station correction:** two Plant 2 paint booths now constrain Elevator dry-to-handle and Cor Ban cures; one conservative Plant 3 electrical-seal station constrains the Radome 40-hour op775 cure. Ovens remain unconstrained, and the parallel topcoat tape-test does not hold a booth.

**Marion virtual factory:** `GET /factory-map` now provides the visual-only Plant 2/Plant 3 capacity layer. It is backed by reviewed VAMA02/VAMA03 annotations, modeled capacity/WIP telemetry, and forecast/lever drill-through. It does not alter scheduling. `P3 QA` is mobile, and `PRNG` remains unplaced pending a reviewed annotation. See `docs/plans/82-marion-virtual-factory-capacity-map.md`.

**BCA discovery:** BCA-01/02 are complete. `/admin/programs` selects routing revisions from active
shop-order usage and retains operation economics/classification in the review draft. Live project
`521938` evidence: A and C use revision 3 / alternative `*`, each has 32 rows and 25 included
production ops; A = 69.603 labor / 104.303 machine hours, C = 69.603 / 104.603. Ops
`1,2,6,7,8,9,9999` default excluded. Next gates are BCA-03 capacity and BCA-04 machine/dwell rules.

**BCA observation registration:** BCA-05a is complete. `BCAFIN` tracks 73 live finishing orders
from project `521938`, with all serials resolved from NOTE_TEXT. Its immutable revision-3 candidate
is in OBSERVE, contract intent is not in force, Schedule is locked, forecast-log rows are zero, and
all eight resource-binding gaps remain visibly incomplete. ELEV/RAD/AEGIS publication is unchanged.

**Portfolio and program UI:** UI-01b/UI-01c are complete. The home page is a registry-driven
portfolio console with separate RTG and contract denominators, maturity and source ledgers, and one
simulation/capacity pass. Every program shares Overview, Schedule, Flow, Units, Resources,
Assumptions, and History tabs. OBSERVE pages expose evidence but no forecast dates or delivery KPIs.
Responsive navigation, dark mode, keyboard use, and WCAG A/AA audits passed.

**Resource foundation:** BCA-03a originated at migration `d8ea03f5b7c9`; the local DB has since
advanced to `dbe1f2a3b4c5`. It contains
24 one-to-one legacy pools and immutable assumption/capacity/simulation-snapshot records. Resource
Registry, readiness badges, and unit Why panels are available while legacy scheduling remains
authoritative. Approved assumptions/capacity are protected from ORM and direct SQL edits except
through supersession. DB-shadow forecasts match the golden baseline exactly. BCA-03b physical-pool
activation remains blocked on owner-approved capacities.

**Lifecycle and epoch foundation:** PLAT-01a was completed through migration `a8c3d4e5f6a7`.
ELEV, RAD, and AEGIS each have an immutable published legacy epoch at
`COMMITMENT_READY`. Epoch definitions, lifecycle transitions, publication selections, simulation
snapshots, and snapshot links are append-only and protected by database triggers. Every new
simulation snapshot materializes the selected epoch definitions and links them by program. Candidate
epochs are explicit and cannot replace published output without authorized publication. Backup:
`data/rtg_app_migrated.pre_model_epochs.bak`, SHA-256
`1F63D0C88AD53DA0CAF0E0BE2852C68D0D7B656D4734EB52BCCA2FAF97D436FF`.

**Virtual-factory follow-ons:** #82-1a adds a governed full active-WC catalog refresh and change
report; #82-4 covers PRNG/VAMA01/Plant 4 only after reviewed annotations; #82-5 is the authenticated
live-map and response-time acceptance check. These are recorded in `TASKS.md`.

**Planning-basis and shadow-integrity gate:** UI-01a and PLAT-01b/01c are complete. Planning basis
is independent from lifecycle; OBSERVE/PROVISIONAL programs publish no forecast dates or delivery
KPIs. Approved resource inputs carry schema-versioned evidence and immutable recertification
history. Forecast stamps now point to schema-v3 envelopes that freeze inputs, epoch routes,
scheduler profiles, and expected results for exact replay. ELEV/RAD/AEGIS have isolated OBSERVE
candidates with exact 29-unit legacy parity; published legacy epochs remain unchanged. The current
review ledger contains 70 explicit inherited debts (24 review dates, 24 evidence attestations, 22
drift policies), so shadow readiness is provisional rather than falsely green.
External-load snapshots are now append-only and horizon-gated; BCA-03c still owns the live CRP
capture and tracked-demand de-duplication.

**Next implementation gate:** execute BCA-06 layup/autoclave cleanup while BCA finishing evidence
accrues. The full critic-reviewed order, phase
gates, and portfolio UI plan are in `TASKS.md` and
`docs/superpowers/specs/2026-08-28-portfolio-dashboard-planning-basis-design.md`. Keep the
`RTG_PROGRAM_SOURCE=routers` fallback until the integrated 2-4 week pilot and rollback gate pass.

**Current data rule that supersedes this legacy document where they differ:** head serials are read
from `SHOP_ORD_CFV.NOTE_TEXT` as `S/N nnn`; elevator hand is derived from PART_NO 501/502. Do not
reintroduce the older assumption that serials are unavailable in IFS.

---

**Audience:** Codex (or any coding agent) tasked with turning the RTG Operation Tracker
into a **repeatable skill** that regenerates the tracker workbook on demand from live IFS
data. This document is exhaustive: it covers *what the tool is, why every design decision
was made, the exact data model, the algorithms, the calibration protocol, and the update
workflow.* Read it top to bottom before writing code.

**Owner:** Ryan Miller (Program Manager, GD Mission Systems — Gulfstream aerospace).
**Programs:** Elevator = **531335** (LH `72P5520501` / RH `72P5520502`, dash `-029P01`).
Radome / Aeronose = **C48178** (top assembly `3700ED0001-101`).
**Source session:** `7cc9493c-9e1f-4f7c-80d6-c6e8c2fcfbc7`.
**Working dir:** `C:\Users\ryan.c.miller\Downloads\rtg-tracker-build\`
**Output workbook:** `C:\Users\ryan.c.miller\Downloads\RTG Operation Tracker 2026.xlsx`

---

## 0. TL;DR — what the skill must do

Given "update the RTG tracker," the skill must:

1. **Re-review the routers** against live IFS (catch new/changed/dropped ops, rev bumps).
2. **Refresh each WIP unit's position** from IFS operation *status codes* (not clocking).
3. **Recalibrate cadence** from the last 2–3 weeks of ship closes; tune the paint-WC budget.
4. **Run the finite-capacity simulator** to forecast each unit's finish.
5. **Regenerate the Excel workbook** (Elevator tab, Aeronose tab, Methodology/Assumptions tab)
   with per-op projected dates, cure/gate rows, and the 4-row Contract/Earliest/Forecast/Δ header.

The whole point of the tracker: **predict which units miss their contract ship date and why**
(own-cure-bound vs capacity-contention-bound), so the PM can act (paint OT, resequence).

---

## 1. Why this exists — the core problem

The IFS ERP router has **`QUEUE_TIME = 0` and `MOVE_TIME = 0` on every operation.** Cure /
dwell time (sealant cures, paint cures, oven cures) is **not modeled anywhere in the ERP.**
This is the root cause of surprise ship-date misses: a unit "finishes" its last labor op on
paper but still owes 24–72 hours of mandatory cure that the schedule never accounted for.

Worse, the **contract commit dates were themselves backward-planned in the ERP with zero cure
time** — so the commits are *physically impossible baselines* (elevator commits are ~8–10
calendar days optimistic; radome ~5–14 days). Any "on-time" reading against the raw ERP commit
is really "N days late" against what's physically achievable.

The RTG tracker fixes both by (a) injecting WI-mandated cures as explicit 24/7 dwell rows and
(b) showing three dates per unit so the two failure modes are visually separated.

---

## 2. Data sources (all live IFS via the enterprise-ifs MCP)

MCP server: `mcp__plugin_enterprise-ifs_ifs-production`. Schema auto-qualifies to `GENE1APP`.
Always prefer `*_CFV` views. Key tables/views and their role:

| View | Role in the tracker |
|------|---------------------|
| `SO_OPER_DISPATCH_LIST_CFV` | **Router + per-op status.** Op list, planned hrs (`LABOR_SETUP_TIME + LABOR_RUN_FACTOR`), work center, and `OPER_STATUS_CODE_DB` (the position signal). |
| `ROUTING_OPERATION_CFV` | Crew size (`CREW_SIZE`), `RUN_TIME_CODE`, `PARALLEL_OPERATION`, `MACH_RUN_FACTOR` (radome oven cure time). Filter `BOM_TYPE_DB='M'`, take highest `ROUTING_REVISION`. |
| `SHOP_ORD_CFV` | WIP unit list (`OBJSTATE='Started'`), `REVISED_DUE_DATE`, `ORG_START_DATE`, `CLOSE_DATE` (for cadence). |
| `GD_SHOP_FLOOR_CLOCKING` | Last-clock date per SO (stall detection); live crew observation; cadence cross-check. **NOT for position** (see §5). |

**Reference SOs** (use these to pull the canonical router each update):
- Elevator: **SO `1452748`** (LH 229) — 78 ops total.
- Radome: **SO `1453338`** (SN 513) — 44 ops total.

---

## 3. The unit inventory & the serial↔SO bridge (CRITICAL, non-obvious)

**Head serials (LH 229, RH 227, radome SN numbers) are NOT stored in IFS for in-process
units.** `SERIAL_BEGIN='*'` on `SHOP_ORD_CFV`; the serial is only assigned at ship.
`RESERVED_SERIAL_STRUCTURE_REP` and `SHOP_MATERIAL_RESERVED_SERIAL` return nothing for the
top-assembly serial. **Therefore the serial↔SO link cannot come from IFS.**

**Bridge rule:** the GAC-RTG commit table's col-H ship commit (a Friday) = IFS SO
`REVISED_DUE_DATE + 1 day` (IFS due is the Thursday before). This match is 1:1 and clean for
all WIP LH and most RH. Where two SOs share a due date, disambiguate by `ORG_START_DATE`
(earlier start = lower serial) — but **one RH case required the user to confirm** (SO 1459237
= RH 234, not 1460759). The skill should surface such ties for user confirmation, never guess.

**Verified WIP mapping as of 2026-08-19** (this is the seed; refresh each update):

ELEVATOR LH (`72P5520501-029P01`): commit / SO
```
LH 232=1455596 (8/21) | LH 233=1456550 (8/28) | LH 229=1452748 (9/04, REF SO)
LH 234=1457061 (9/11) | LH 235=1458317 (9/18) | LH 236=1459236 (9/25)
LH 237=1460167 (10/02)| LH 238=1460758 (10/09)| LH 239=1461523 (10/16)
LH 230/231 = SHIPPED (no active SO)
```
ELEVATOR RH (`72P5520502-029P01`):
```
RH 227=1452749 (8/21, the Friday-miss unit) | RH 231=1456551 (8/28) | RH 232=1457063 (9/04)
RH 233=1458318 (9/11) | RH 235=1460168 (9/18) | RH 234=1459237 (9/25, user-confirmed)
RH 236=1460759 (9/25) | RH 237=1461524 (10/08) | RH 230 = SHIPPED
```
RADOME (`3700ED0001-101`), bridge by `REVISED_DUE_DATE` ascending; serials from prior
tracker (373/508/511/513/514/515/517/518/519/520/521/522/523). WIP SOs:
`1460931, 1460932, 1460451, 1459009, 1456255, 1454080, 1458360, 1454082, 1401814, 1451436,
1453339, 1453338, 1449908, 1454081, 1451434`. Note SN361 (1360294) is stale since 2025-02
and SN430 (1401814) is in MRB — both flag as STALLED.

---

## 4. Milestone boundaries (how ops roll up to the printed milestones)

**Elevator** (4 milestones): `AJ` (Assy Jig) ≤ op 1300 · `A1` (Assembly 1) ≤ 2800 ·
`A2` (Assembly 2) ≤ 3600 · `FS` (Finish/Ship) ≤ 4200.

**Radome** (4 milestones): `LAM` (Lamination) ≤ 570 · `ASSY` (Assembly) ≤ 710 ·
`PAINT` ≤ 755 · `SHIP` ≤ 790.

Each op carries its milestone tag in the router tuple (see §7). The workbook prints milestone
section headers and rolls op completion up into milestone status.

---

## 5. Position detection — status codes, NOT clocking (learned the hard way)

**The bug:** the original detector used `MAX(OPERATION_NO)` with clocking in
`GD_SHOP_FLOOR_CLOCKING`. This is WRONG because **"(NOWB)" ops** (No Work Booked to a
sub-order — e.g. op 3800 Prep & Prime, 30.5 hr) **clock their labor to a *different* cost
bucket** and are therefore invisible to clocking-based detection. The detector lagged reality
by a full op, causing RH 227 to read as "at op 3700" when it was actually in-process at 3800.

**The fix:** drive position from `OPER_STATUS_CODE_DB` in `SO_OPER_DISPATCH_LIST_CFV`:
- `90` = **Closed** (op done)
- `85` = **In Process** (current op)
- `40` = **Released** (upcoming)

**Position = the highest op number with status 90 (`MAX_CLOSED`).** The unit is working the
first op *after* `MAX_CLOSED`. **Ignore stray *low* in-process ops** (e.g. an op 50 showing
In-Process while the unit is really at 3850 — that's out-of-sequence rework noise).

Query pattern (per WIP SO):
```sql
SELECT ORDER_NO,
  MAX(CASE WHEN OPER_STATUS_CODE_DB='90' THEN OPERATION_NO END) AS MAX_CLOSED,
  MAX(CASE WHEN OPER_STATUS_CODE_DB='85' THEN OPERATION_NO END) AS MAX_INPROC
FROM SO_OPER_DISPATCH_LIST_CFV
WHERE ORDER_NO IN (...WIP SOs...) AND OPERATION_NO < 9000
GROUP BY ORDER_NO
```
The skill stores this as `STATUS_MAXCLOSED = {so: maxclosed_op}` in the builder.

**Completion cell rule in the grid:** op is "C" if `op_no < MAX_CLOSED`; "WIP" if
`op_no == MAX_CLOSED` (or the first released op after it); blank/projected-date if upcoming.

**Known deferred flaw (documented, not yet fixed):** the "op complete if downstream charging
exists" heuristic can erase real labor when a mechanic clocks a downstream prep op while the
main unit waits on MRB. Status-code position largely supersedes this, but if you re-introduce
any clocking logic, beware.

---

## 6. Cures & dwell — the heart of the model

Cures are **pure calendar dwell, ZERO labor, elapse 24/7 wall-clock** (nights + weekends).
They are injected as dedicated rows *after* the op that triggers them. Sourced from the MVA
Work Instructions (SharePoint `MFG-MMDCC / "MVA Work Instructions"`, flat lib ~326 files;
Elevator = 4401 series, Radome = 3700ED0001-101 ASSY/LAM/PAINT).

### 6a. Elevator cures (`ELEVATOR_CURES`) — 9.8 cal-day full-build floor
`(after_op, label, dwell_hr, note)`:
```
800  Liquid Shim (spar & details)        8   GMS4003 ambient set before assembly
2300 Fillet Seal Details (PS870 B-2)     32  24hr flash + 8hr@125F (accelerated/oven path)
3000 Seal Elec Hardware / CHO-BOND       24  CHO-BOND 1038 24hr resistance-check gate
                                             (168hr full cure runs PARALLEL, non-blocking)
3030 Overcoat Fastener Tails (PS870)     32  24hr flash + 8hr@125F; 3-day RT fallback
3200 Fay Seal LE Skins (PS870 C-12)      72  24hr flash + 48hr@125F (dominant elev cure)
3220 Aero Seal tack-free                 2   GMS4114 2hr tack-free
3400 FIP Seal (PS870 B-2)                32  24hr flash + 8hr@125F
3700 Aero Seal Gaps tack-free            2   GMS4114 2hr (the original "Friday-miss" op)
3800 Prime/Topcoat dry-to-handle         4   primer flash + topcoat dry before op3900 install
3800 GATE Topcoat 24hr tape-test (QI)    24  PARALLEL cure — see §6c
4010 Cor Ban tack-free                   4   GAC115AD1 CIC dry-to-tack (est; also 2-3d install cycle)
```

### 6b. Radome cures (`RADOME_CURES`) — 4.9 cal-day floor
LAM oven cures come from `MACH_RUN_FACTOR` in `ROUTING_OPERATION_CFV` (~6.5 hr each on
op 170/290/410/530). Plus WI gates:
```
170 Outer Skin oven                      6.5   (MACH_RUN_FACTOR)
170 GATE Peel-ply to next bond           8     WI 8hr peel-ply-to-bond gate
290 Honeycomb oven                       6.5
410 Diverter Anchor oven                 6.5
410 GATE Peel-ply to inner-skin bond     8
530 Inner Skin oven                      6.5
590 Edge/Chamfer seal                    6     GAA100BD08 est
620 GATE Pre-drill shim set              8     WI min 8hr RT before drill; Shore D gate
625 Liquid Shim Details                  6     GAA100BD10 6hr RT (or 2hr@150F accel)
700 LDS Fillet Seal (RTV)                2
710 Environmental Seal set               6
730 Fill Surface Imperfections           2
740 Anti-Static Paint flash              2
750 Environmental Primer                 4
775 GATE Electrical Sealing 40hr         40    polysulfide 00200054000, Shore A>=35
                                               (DOMINANT radome dwell)
```

### 6c. Parallel cures (the topcoat subtlety)
The **24hr topcoat tape-test cure is mandatory (WI) but runs IN PARALLEL** with downstream
labor (ops 3850→4030), only *gating* final inspection (op 4100) if it hasn't elapsed by then.
It is **not** a serial tail-blocker. Evidence: last-4-shipped units show op4100→op4200 (pack)
back-to-back with the same timestamp. Modeled via `PARALLEL_CURE_GATES = {'Topcoat 24hr
tape-test': 4100}` — the cure starts after op3800 (topcoat application), runs 24/7, and sets a
"not-before" time on op4100. Usually the intervening labor covers the 24hr so it's invisible;
it only bites when the tail is rushed.

### 6d. Cure design decisions (user-confirmed)
- PS870 sealant cures use the **ACCELERATED (oven) path** (24hr flash + 8-48hr@125F), not the
  14-day RT fallback.
- CHO-BOND 168hr full cure = **PARALLEL/non-blocking**; only the 24hr resistance-check gates.
- **Time-of-day** is shown on cure/gate rows only; labor ops are date-only.
- Cor Ban (op 4010) empirically spans **2–3 calendar days** per unit (cure + install cycle);
  model it as a realistic 2–3d block, not just the 4hr tack-free.

### 6e. Physical cure-station counts and configured constraints
- **Elevator: 2 paint booths** (concurrent paint/prep/topcoat/CorBan cap = 2). 2 ovens ×
  2–3 units each = 4–6 slots → **ovens NOT a constraint.**
- **Radome: ovens plentiful/unattended** (not a constraint); **op775 electrical-seal = 1–2
  stations** (the 40hr dwell is the hard bottleneck).
- **Configured allocator:** Elevator dry-to-handle after op3800 and Cor Ban after op4010 reserve
  one of two Plant 2 paint booths. Radome op775 electrical sealing reserves one conservative Plant 3
  seal station for its 40-hour cure. The 24-hour parallel topcoat tape-test does not reserve a booth.
  Oven cures remain per-unit and unconstrained.
---

## 7. Router data model (`routers.py`)

Two ops lists + two cures lists + crew/parallel maps. Op tuple:
`(op_no, description, work_center, planned_hr, milestone_code)`.

```python
ELEVATOR_OPS = [ (100,"Mark Data Plate","248",0.8,"AJ"), ... (4200,"Pack & Ship","P2PCK",1.5,"FS") ]
RADOME_OPS   = [ (130,"Outer Skin Bagging","AEROL",1.46,"LAM"), ... (790,"Pack and Ship","235",3.3,"SHIP") ]
ELEVATOR_CURES = [ (after_op, label, dwell_hr, note), ... ]
RADOME_CURES   = [ ... ]
ELEV_MILESTONES = [("AJ","Assy Jig"),("A1","Assembly 1"),("A2","Assembly 2"),("FS","Finish / Ship")]
RAD_MILESTONES  = [("LAM","Lamination"),("ASSY","Assembly"),("PAINT","Paint"),("SHIP","Ship")]
```

### 7a. Ops correctly EXCLUDED from the router (don't re-add)
Per-unit **MRB-clocking placeholder ops** are variance buckets, not real steps: elevator
`2052, 2054, 2810, 2820, 2830`; radome `626, 627`. Drop these.

### 7b. Ops that MUST be included (were wrongly dropped once)
"(NOWB)" ops are **real value-add** (No Work Booked to sub-order = in-line work). The router
restore added back: op **300** (Record Serial#, 2.0hr), **1940** (Prep Test Panel, 2.7),
**1950** (Countersink LE, 3.7), **3800** (Prep & Prime, 30.5hr — the true ship-miss driver),
**3850** (Inspect Touch Up, 0.1). Total 39hr that was invisible. **The router re-review step
(§10) must diff against live IFS and flag any op present in IFS but missing from the list.**

### 7c. Crew factor (`CREW_BY_OP`) — floor beats ERP standard
The ERP router is `CREW_SIZE=1` / serial on every op, but the floor swarms the finish line
(2 painters on op3800 observed live). Wall-clock = `planned_hr / crew(wc, opno)`. **Crew boost
is scoped to tail/finishing ops only** (by op #), so far-out units don't over-accelerate:
```python
CREW_BY_OP = {
  3800:2.0, 3900:2.0, 4010:2.0, 4030:2.0,   # elevator finish line (paint/ship push)
  2300:2.0, 3030:2.0, 3300:2.0,             # big seal/touch-up ops that swarm
  775:1.5, 780:1.5, 730:1.5, 740:1.5, 750:1.5,  # radome finish line
}
def crew(wc, opno=None):
    return CREW_BY_OP.get(opno, 1.0)   # main assembly stays 1x
```
This was a deliberate resolution of an "open tension": applying crew 1.5x to *all* assembly
ops made far-out units read 3 weeks early (re-introducing the optimism the critics warned of).
Tail-only scoping keeps near-ship units accurate without over-accelerating the back of the line.

### 7d. Parallel cure gates
```python
PARALLEL_CURE_GATES = { "Topcoat 24hr tape-test": 4100 }  # label substring -> gate op
```

---

## 8. The two schedule engines

### 8a. `schedule_engine.py` — single-unit "Earliest possible" (no contention)
`forward_schedule(ops, cures, start_op, start_dt)` walks the router from the op *after*
`start_op`, applying crew factor, adding labor via `add_labor_hours` (respects a ~16hr/day
shift, Sat 0.5, Sun 0.25) and cures via `add_cure_hours` (24/7 wall-clock). Returns rows
`(op_no|None, kind, label, start_dt, finish_dt, wc, hrs, ms)` where kind ∈ {labor, cure}.
Used to compute each unit's **Earliest-possible finish if worked completely alone.**

### 8b. `capacity_engine.py` — finite-capacity multi-unit sim (the Forecast)
`simulate(units, ops_map, cures_map, as_of)` — **this is the authoritative forecast.**
- `units`: list of `{serial, so, maxop, commit, program}`.
- All WIP units advance simultaneously but **compete for a shared per-WC daily hour budget**,
  drawn in **commit-date priority order** (earliest commit first).
- Day-stepped loop; each working day distributes `WC_DAILY[wc] * day_factor(day)` hours.
- Cures run 24/7 and do **not** consume WC hours (they block only that unit).
- Parallel gates ('pgate' queue items) set a not-before time on their gate op, non-blocking.
- Intra-day per-unit clock preserves **time-of-day** on cure/gate rows.
- Returns `{serial: {finish, op_dt{opno:start_dt}, cure_dt{label:start_dt}}}`.

**Per-WC daily budgets** (measured sustained utilization Aug 4–19, 11 working days) — this is
the calibration surface:
```
32684 (elev main assembly) = 167    AEROL (radome layup)      = 40
221   (ELEV PAINT)         = 27  ←BOTTLENECK   236 (RAD PAINT) = 12  ←BOTTLENECK
INSP=27  32687=18  P3 QA=8  3FINL=8   AEROA (radome assy)     = 20
238=8  ATUP=8 (radome ovens)   248=8  235=8  P2PCK=8   DEFAULT=12
```
**Paint booths are the true throttle** (matches observed ~6/mo throughput), NOT main assembly.

`day_factor`: Mon–Fri = 1.0, Sat = 0.5, Sun = 0.25. `SHIFT_START = 6` (0600), shift span
16hr/day (2 shifts).

---

## 9. Workbook layout (`build_tracker.py`)

Three tabs: **Methodology & Assumptions** (first), **Elevator**, **Aeronose**.

### 9a. Per-unit column header (4 stacked rows, the key design)
For each unit column: **Contract commit** (ERP date, unchanged even when late) /
**Earliest possible** (single-unit `project_unit`, no contention) / **Forecast (w/ contention)**
(capacity sim) / **Δ vs Contract** (days). Plus the serial + SO number in the header cell.

Interpretation the PM reads off the board:
- **Earliest > Contract** ⇒ the contract baseline was set without cure = physically impossible.
- **Forecast > Earliest** ⇒ the gap is the *contention cost* (paint-booth-limited).
- Example: RH 227 contract 8/21 / earliest 8/26 / forecast 8/26 / +5d ⇒ its *own cures* blow
  8/21, not contention. LH 237 earliest 9/14 vs forecast 9/29 = 15d gap ⇒ paint-limited.

### 9b. Grid body
Ops down the rows (with milestone section headers), units across the columns. Cure/gate rows
are inserted after their trigger op and tinted (cure vs gate colors). Each cell:
- Completed op → "C" (green)
- Current op (`== MAX_CLOSED`) → "WIP" (amber)
- Upcoming op → its **projected date** from `op_dt` (this is what the PM asked for — every
  future op shows the date it needs to happen, not just blank)
- Cure/gate rows → date **+ time-of-day** from `cure_dt`
- STALLED units (idle >7 days) → header flagged, forecast suppressed ("idle Nd").

### 9c. Commit dates source
Contract commit dates come from the **GAC RTG table** (`GAC RTG 2026.xlsx`, "Elevator RTG" and
"Aeronose RTG" tabs), cols E/F/G/H = milestone finish dates (AJ/A1/A2/FS). Col H = firm ship
commit. These are the fixed contractual baseline — **never overwrite them with the forecast.**

### 9d. Styling (locked convention)
Aptos/Aptos-Serif font, navy/blue/ice palette, yellow = editable cells. Landscape, fit-to-width,
freeze panes at the first unit column. (See `build_tracker.py` for exact hex + helpers.)

---

## 10. THE UPDATE WORKFLOW (what the skill runs each time)

User directive: **"every time we update this, do a full router review to fine-tune the model.
2–3 weeks isn't a lot to build a product like this off of."** So an update is NOT just a
position refresh — it re-runs calibration. Five steps:

1. **Router re-review (per program).** Pull `SO_OPER_DISPATCH_LIST_CFV` for the ref SO
   (elev 1452748 / rad 1453338). Diff the op list + planned hrs against `ELEVATOR_OPS` /
   `RADOME_OPS`. Flag: new ops, changed hours, dropped ops, `ROUTING_REVISION` bumps, and any
   "(NOWB)" op present in IFS but missing from the list. Surface diffs to the user before
   editing `routers.py`.

2. **Position refresh.** Rebuild `STATUS_MAXCLOSED` from `OPER_STATUS_CODE_DB=90` per WIP SO
   (§5). Also refresh the WIP SO list from `SHOP_ORD_CFV WHERE OBJSTATE='Started'` and
   re-derive the serial↔SO bridge (§3); surface any due-date ties for user confirmation.

3. **Cadence recalibration.** Pull `SHOP_ORD_CFV.CLOSE_DATE` for the last 2–3 weeks per
   program → compute days/unit. Compare to the model's implied cadence (`backtest.py`). If the
   paint-WC budget has drifted, tune `WC_DAILY['221']` (elev) / `WC_DAILY['236']` (rad) using
   `calib.py`. **Widen the window toward 4–6 weeks as more full-steam data accrues** (the
   Aug-2026 baseline was thin: 2–3 weeks post-config-roll).

4. **Crew / cure spot-check.** Verify crew assumptions against live clocking on the current
   push unit (`GD_SHOP_FLOOR_CLOCKING`, open clockings). Confirm cure floors against any WI
   revisions.

5. **Stall refresh.** Compute last-clock per SO; flag idle > 7 days as STALLED (suppress
   forecast). SN361 and SN430 (radome) were stalled at baseline.

Then: run `capacity_engine.simulate`, run `schedule_engine` per unit for Earliest, and
regenerate the workbook via `build_tracker.py`.

**Helper scripts already in the folder:** `backtest.py` (cadence vs model), `recent_cadence.py`
(window comparison), `calib.py` (paint-budget tuning table), `curefloor_calc.py` (cure-floor
sums), `trace227.py`/`trace227b.py` (single-unit trace for validation).

---

## 11. Calibration lessons (so the skill doesn't repeat them)

- **Backtest against the RECENT window only (2–3 wk).** A full-8wk average made the model look
  "3x too fast" — but that was stale data: the elevator just finished a **config roll** that
  held work up, then released in a burst. Current pace (last 2wk) = **2.2 days/unit elevator**,
  which the model reproduces. Radome was ~4–7 days/unit and climbing toward full-steam.
  Do NOT lower the paint budget to match stale slow data.
- **The model is calibrated to CURRENT pace, not steady-state.** Far-out forecasts assume the
  current burst rate holds — treat units beyond the next 2–3 ships as *directional*.
- **Validate against reality.** RH 227 was the anchor: team said Saturday 8/23; the corrected
  model (status position + crew + parallel topcoat) produced Sat 8/22 (+1d). When the model
  disagrees with the floor, find the modeling bug — don't just trust the model.

---

## 12. Known open items / deferred enhancements (documented, not built)

1. **Bottleneck/paint-load view** (user: "that might be useful, just note it"): a view of units
   queued for the paint bottleneck (WC 221 / 236) by week — shows where the throttle bites and
   is the actionable lever for pulling units in (paint OT / resequence).
2. **Electrical-seal station calibration:** cure-station contention is implemented. Confirm whether
   Radome op775 has one or two usable Plant 3 seal stations, then update the conservative seed
   capacity if floor/process validation supports two.3. **Paint cross-program pooling:** WC 221 (elev) and WC 236 (rad) are modeled as private
   budgets but may be the *same* booths/painters. If shared, effective elevator paint drops to
   ~15–20 hr/day. Confirm with the shop; if shared, pool the budgets.
4. **Weekend factors on cure-bound tails** are false precision (a red flag on a cure-dominated
   unit within ~2 days of commit is likely a false positive). Consider suppressing weekend
   labor factoring when a unit's remaining tail is cure-dominated.
5. **No rework / first-pass-yield modeling** (this is composites — voids, delam, failed tape
   tests happen). Every forecast is best-case. An MRB-history-based risk adjustment is possible.
6. **GDMS 4-4-5 fiscal calendar** (see `reference_gdms_fiscal_calendar.md`) if the tracker ever
   needs weekly rollups or FY/quarter headers.

---

## 13. Skill packaging recommendations

- **Trigger phrases:** "update the RTG tracker", "refresh the RTG plan", "regenerate the
  operation tracker".
- **Inputs:** none required beyond IFS MCP access; optionally `as_of` date (default today) and
  a scope flag (elevator only / radome only / both).
- **Structure:** keep `routers.py` as the editable source-of-truth data module;
  `schedule_engine.py` + `capacity_engine.py` as pure logic; `build_tracker.py` as the
  Excel renderer. The skill orchestrates the §10 workflow around them.
- **Guardrails:** (a) never overwrite contract commit dates with forecasts; (b) surface router
  diffs and serial↔SO due-date ties for user confirmation before editing; (c) after building,
  validate a known unit's trace against the floor before declaring success; (d) label the
  workbook with the `as_of` date and the calibration window used.
- **Verification step:** re-run `backtest.py` after each build; if the model's implied cadence
  doesn't match the recent-window actual (±~1 day/unit), stop and report — the capacity budget
  needs re-tuning before the forecast is trustworthy.

---

## 14. File manifest (`Downloads/rtg-tracker-build/`)

| File | Purpose |
|------|---------|
| `routers.py` | Router ops, cures, crew factors, parallel gates, milestones (editable data). |
| `schedule_engine.py` | Single-unit forward projection (Earliest-possible). |
| `capacity_engine.py` | Finite-capacity multi-unit sim (Forecast). **Authoritative.** |
| `build_tracker.py` | Excel workbook renderer (3 tabs, 4-row header, per-op dates, cures). |
| `backtest.py` | Model cadence vs actual ship cadence. |
| `recent_cadence.py` | Recent-window cadence comparison (2wk/3wk/8wk). |
| `calib.py` | Paint-WC budget tuning table (budget → days/unit). |
| `curefloor_calc.py` | Cure-floor day sums per program. |
| `trace227.py`, `trace227b.py` | Single-unit trace for validation. |
| `completion.py`, `extract_rtg.py`, `actuals.py`, `build.py` | Earlier/legacy helpers. |
| `RTG Operation Tracker 2026.xlsx` (in `Downloads/`) | The output workbook. |
| `GAC RTG 2026.xlsx` (in `Downloads/`) | Source of contract commit dates. |

**Related memory files** (`.claude/.../memory/`): `reference_wi_cure_dwell_times.md` (full cure
history + all the fix logs), `reference_rtg_serial_so_bridge.md` (serial↔SO bridge),
`reference_gdms_fiscal_calendar.md` (fiscal calendar), `reference_wi_cure_dwell_times.md`.
