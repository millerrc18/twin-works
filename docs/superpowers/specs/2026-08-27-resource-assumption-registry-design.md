# Resource and Assumption Registry Design

**Implementation status (2026-08-31):** foundation, evidence/recertification governance,
schema-v3 replay, and incumbent one-to-one shadow parity are complete. Physical shared-pool,
external-load, generic occupancy, and BCA pilot activation remain gated work.

## Status

Approved architecture under staged implementation. This design expands BCA-03 into the general resource model used
by TwinWorks for shared work centers, dynamic external demand, machines, cure stations, tooling,
and forecast assumption provenance. It does not authorize implementation or BCA onboarding.

## Problem

The current scheduler stores work-center budgets as `(program, WC)` values. That representation is
insufficient when several programs use the same people, cell, machine, booth, range, or tool. A
change in demand mix can make one program consume most of a shared resource without changing the
resource's physical capacity.

Tooling adds a second type of constraint. Labor is consumptive effort measured in hours. A jig or
mold is occupancy: one unit may hold a slot across several operations, cures, or waits while using
little labor. Treating both as generic hours produces incorrect schedules.

Finally, a forecast is not auditable unless users can see which facts and assumptions affected it,
where those values came from, whether they are approved, and when they must be reviewed.

## Evidence

The 2026-08-27 IFS evidence pass is recorded in
`docs/plans/bca-03-capacity-evidence.md`.

- `P3TRI`, `TRI A`, `PRNG`, and `P3NDI` are active but configured as infinite-capacity WCs in IFS.
- Recent labor actuals measure demand served, not sustainable capacity.
- BCA and C17 overlap at `TRI L`, `ATUP`, `P3TRI`, `TRI A`, `236`, `PRNG`, `P3NDI`, `P3 QA`,
  `3FINL`, and `235`, in addition to administrative WCs.
- Current released demand shows the same resources are used by additional radome and repair programs.
- Aeronose tooling currently identified by the program manager: two assembly jigs, two holding
  fixtures, one trim fixture, three shell lamination molds, and one core-forming mold set.
  Operation acquire/release boundaries still require review before activation.

## Design Principles

1. Model physical resources once, then bind programs and operations to them.
2. Separate effort consumption from occupancy leases.
3. Separate measured facts, derived estimates, approval, and commitment readiness.
4. Never infer capacity from utilization automatically.
5. Never use `DEFAULT_SHIFT` in resource-registry mode.
6. Preserve every active forecast as a fully materialized, immutable input snapshot.
7. Show assumption readiness before changing forecast math.
8. Keep legacy behavior available until each migration phase passes its own acceptance gate.

## Alternatives Considered

### Recommended: normalized physical-resource registry

Persist physical pools, effective-dated profiles, operation bindings, external-load snapshots, and
assumptions as separate records. Compile them into one immutable simulation profile per forecast.
This correctly models shared resources and tooling and supports audit/history.

### Rejected: add resource JSON to each Program

This is quicker, but duplicates shared resources and recreates the current problem. Two programs
can define conflicting capacity for the same physical WC, and tooling/evidence history becomes
opaque.

### Rejected: separate scheduling microservice

A separate service could eventually scale independently, but it adds deployment, transaction, and
versioning complexity before the model is stable. The existing deterministic engine remains the
correct integration point.

## Domain Model

### ResourcePool

Stable physical identity.

- `id`, unique `code`, `site`, `name`, `resource_type`, `capacity_unit`, `work_center_no`, `active`,
  `retired_at`, timestamps.
- `resource_type`: `LABOR`, `MACHINE`, `TOOL`, `CURE_STATION`, `SPACE`.
- `capacity_unit`: `HOURS` for consumptive effort or `SLOTS` for occupancy.
- A discrete pool may optionally have named `ResourceInstance` rows when slots are not fungible.
  Bindings may request any instance or one named instance.

### ResourceCapacityVersion

Append-only effective-dated physical capacity.

- `pool_id`, `effective_from`, optional `effective_to`, `status`, `capacity_scope`,
  `capacity_schedule_json`, `slot_count`, `calendar_policy_json`, `external_policy_json`,
  `assumption_id`, timestamps.
- `capacity_scope` is either `GROSS_SITE` or `NET_TRACKED`. `GROSS_SITE` subtracts approved
  external load. `NET_TRACKED` is already net and must not subtract external demand again.
- Approved versions are immutable. Supersession closes the prior effective range.
- Required resources without a covering version fail profile compilation; no fallback is inserted.

### OperationResourceBinding

Connects a routing operation or operation span to physical resources.

- Program, optional part number, routing revision/alternative, pool, acquire operation,
  optional release operation, requirement mode, quantity, demand source, release event,
  minimum hold, optional lag, optional instance request, assumption ID, status.
- `EFFORT` consumes hours. `demand_source` is `LABOR`, `MACHINE`, or `FIXED`.
- `OCCUPANCY` acquires discrete slots and holds them through a validated release event.
- Release events are `OP_START`, `OP_COMPLETE`, `CURE_COMPLETE`, or `ROUTE_COMPLETE`.
- Approval validation requires acquire/release operations and cure labels to exist in the bound
  routing revision. Missing release targets never silently fall back to route end.

### ModelAssumption

Immutable provenance and governance for any model input.

- Subject type/key, parameter, JSON value, unit, basis, approval status, commitment grade,
  evidence source, evidence window, calculation method, evidence count, minimum evidence count,
  owner, approver, approved/review/effective dates, supersedes ID, timestamps.
- `basis`: `IFS_FACT`, `MEASURED_ACTUAL`, `DERIVED_ESTIMATE`, `OWNER_CONFIRMED`,
  `PROVISIONAL_GUESS`.
- `approval_status`: `DRAFT`, `APPROVED`, `UNDER_REVIEW`, `SUPERSEDED`.
- `commitment_grade`: `COMMITMENT_READY` or `INTERNAL_ONLY`.
- A sparse data set cannot be approved as `MEASURED_ACTUAL` when `evidence_count` is below
  `minimum_evidence_count`; it must use owner confirmation or an internal-only provisional basis.
- Passing `review_due_at` changes readiness to stale/provisional and creates a recertification item;
  it does not silently rewrite the assumption.

### ExternalLoadSnapshot and ExternalLoadRow

Immutable copy of external IFS workload.

- Snapshot stores capture time, source/schema version, coverage start/end by pool, tracked-program
  identity set, source-quality policy, and assumption references.
- Rows store pool, work date, optional shift, project/order/part/source, load type, hours/units,
  quality, and inclusion weight.
- Primary source is `CRP_ORDER_LOAD2`, which provides work-date labor/CRP load and source quality.
- Released shop-order rows default `OK` with weight 1. PMRP defaults `SUSPECT` and weight 0 until an
  approved pool policy assigns another weight. Excluded rows retain a reason.
- `SharedResourceDiscovery` maps registered program routings/orders to rows and removes tracked
  demand from the external reserve. This prevents double counting when a program is onboarded.
- Each pool has an approved day-to-shift allocation rule when the source is day-level.
- Each pool records `horizon_covered_until` and an approved beyond-horizon policy:
  `BLOCK`, `HOLD_LAST_COMPLETE_WEEK`, or `TRAILING_MEAN`. Commitment-ready runs cannot exceed
  coverage when policy is `BLOCK` or internal-only.

### SimulationSnapshot and ForecastConstraintEvent

- `SimulationSnapshot` stores a complete immutable JSON copy and hash of resolved resource pools,
  capacity versions, bindings, assumptions, external rows/policies, resource mode, and data as-of.
- `ForecastLog` links to the snapshot through a build/run record. Historical forecasts are replayed
  from the stored snapshot, not current tables.
- `ForecastConstraintEvent` is the single causal event term. It records unit, pool, wait start/end,
  wait hours, reason, gross capacity, external load, schedulable capacity, and assumption IDs.
- Raw net capacity may be negative. The scheduler uses zero schedulable capacity but emits an
  oversubscription event carrying the full deficit; it never hides the deficit by only clamping.

## Scheduler Semantics

### Effort pools

An operation consumes its configured labor or machine effort from the bound physical pool. Programs
bound to the same pool contend automatically. Gross shift capacity is reduced by the external load
resolved for that date/shift when capacity scope is `GROSS_SITE`.

### Occupancy pools

Before an operation starts, the unit attempts to acquire all required occupancy resources
atomically. If any slot is unavailable, it acquires none and requeues at the earliest missing
release event. Requests use deterministic ordering `(ready_time, unit_priority, serial, pool_id)`.
The engine asserts forward progress and fails loudly on an invalid/deadlocked binding set.

Slots release only at the approved event and after `min_hold_hours`/lag. Tooling remains held
through intervening operations and cures when the binding says so. Cure stations migrate to this
same mechanism after parity is proven.

## Assumption Readiness and User Experience

### Forecast readiness

Readiness is the worst state across all assumptions required by the unit's remaining route and the
external-load coverage horizon.

- `COMPLETE`: approved, commitment-ready, not stale, and fully covered.
- `PROVISIONAL`: every input exists, but at least one is internal-only, under review, or stale.
- `INCOMPLETE`: a required pool, capacity version, binding, or horizon policy is missing.
- `OVERSUBSCRIBED`: external load exceeds gross capacity for a relevant date; shown in addition to
  readiness.

Internal scenario simulation is allowed with present provisional assumptions. Customer-commitment
use requires `COMPLETE`. Program onboarding may save a draft with provisional resources, but
program activation is blocked while any required input is `INCOMPLETE`.

### Resource Registry

`/admin/resources` shows pool identity/type, current capacity, consumers, external demand,
assumption basis/approval/readiness, owner, review date, and history. Pool detail shows effective
versions, routing bindings, recent actual envelopes, external-load quality, and pending reviews.

### Onboarding coverage matrix

Every included operation lists its effort and occupancy bindings. Missing pools or assumptions are
visible by operation. Save Draft is allowed; Activate Program is separately disabled until required
coverage passes policy.

### Forecast Why panel

The forecast badge opens a unit explanation that separates:

- physical capacity,
- tracked-program demand,
- external IFS demand,
- tooling occupancy,
- actual causal wait events,
- evidence basis/window/method,
- approval owner/effective/review dates.

The Factory Map uses the same resource detail and readiness states. No second assumption system is
created for the map.

## Drift and Change Governance

A weekly `AssumptionDriftReport` compares approved profiles with current actual envelopes. Windows
are configurable by pool; the initial default is recent 4 weeks versus prior 9 weeks. Drift creates
an owner review item and moves an assumption to `UNDER_REVIEW`; it never changes active values.

Every approved change creates a new version. Forecast snapshots retain the prior version forever.
Pools may be retired, and profile compilation fails if a required future date lacks a covering
capacity version.

## Migration and Rollback

Resource mode is a forecast-build parameter captured in `SimulationSnapshot`, not mutable global
state. Process settings may select a default, but each run records `LEGACY`, `DB_SHADOW`, or
`DB_ACTIVE`.

1. **Foundation and trust:** add schema/services, seed one-to-one legacy pools, snapshot compiler,
   readiness badges, Resource Registry, and Why panel. Legacy remains authoritative.
2. **Legacy parity:** compile DB profiles with one pool per legacy `(program, WC)` and prove exact
   golden parity.
3. **Physical labor pools:** collapse approved WCs into shared physical pools. Forecast differences
   are expected and require an explainable diff report and owner sign-off, not golden recapture by
   default. DB mode removes `DEFAULT_SHIFT`.
4. **External reality:** ingest immutable CRP snapshots in shadow mode, validate BCA/C17 overlap,
   source quality, horizon, and double-count prevention, then activate approved reserve subtraction.
5. **Discrete resources:** migrate current cure stations to the occupancy allocator with parity,
   then add Aeronose tooling in shadow mode. Tool counts may be recorded as owner-supplied facts;
   forecast activation waits for approved occupancy bindings.
6. **Governance and pilot:** enable drift/recertification workflows, run BCA pilot, and stabilize for
   2-4 weeks. Retain immediate legacy rollback for one complete accepted pilot cycle.

Exit criteria: zero unresolved critical assumptions for commitment forecasts, no unexplained seed
forecast drift, historical snapshot replay matches hashes, no deadlocks, external-load coverage
meets the forecast horizon, and named owners approve the activated shared/tooling profiles.

## Initial Validation Cases

### BCA and C17

Automatically discover their physical overlap and compare before/after actuals, current CRP demand,
and counterfactual external load. Validate `TRI L`, `ATUP`, `P3TRI`, `TRI A`, `236`, `PRNG`,
`P3NDI`, `P3 QA`, `3FINL`, and `235`. Administrative/wait WCs do not become constraints.

### Aeronose tooling

Create draft pools for two assembly jigs, two holding fixtures, one trim fixture, three shell molds,
and one core-forming mold set. Validate whether instances are fungible and approve acquire/release
operation spans before tooling can affect commitment forecasts.

## Explicit Non-Goals

- No automatic capacity updates from clocking or CRP.
- No BCA onboarding in the registry/tooling foundation phases.
- No claim that IFS infinite-capacity settings are physical truth.
- No guessed Aeronose occupancy spans.
- No replacement of the deterministic scheduler or ML residual model.

## Critic Review Record

The draft was independently reviewed by Claude Opus 4.7 for scheduler/data integrity and Gemini
3.1 Pro for assumption governance and user comprehension. The revised design incorporates their
material findings:

- explainability and readiness move into the first release rather than following math changes;
- external snapshots require coverage horizons, explicit extrapolation and shift-apportionment
  policies, source-quality rules, immutable rows, and visible oversubscription deficits;
- occupancy is explicitly separate from effort, supports named instances, uses atomic
  all-or-nothing acquisition, and fails loudly on invalid/no-progress schedules;
- migration separates one-to-one legacy parity from expected shared-pool forecast changes;
- internal simulation and commitment-ready activation use separate gates;
- assumptions include evidence sufficiency, review dates, commitment grade, drift review, and
  recertification without automatic model changes;
- shared-resource discovery prevents tracked/external double counting; and
- legacy rollback is retained through an accepted pilot cycle.
