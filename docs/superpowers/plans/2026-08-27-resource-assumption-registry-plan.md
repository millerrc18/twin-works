# Resource and Assumption Registry Implementation Plan

> **Scope update 2026-09-02:** BCA-specific execution in this historical plan is deferred. Generic
> resource and occupancy work continues for Elevator, Aeronose, and Aegis under
> `docs/plans/three-program-tooling-roadmap.md`. Do not execute the BCA pilot tasks below.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable physical-resource model for shared work centers, external workload,
machines, cure stations, and tooling while preserving current forecasts until each constraint is
explicitly approved and activated.

**Architecture:** Stable physical pools are separated from effective-dated capacity versions and
operation requirements. Every model input references immutable assumption provenance, and every
forecast captures a materialized simulation snapshot plus causal constraint events. Labor pools,
external load, and occupancy tooling activate in independent shadow-gated phases.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy async, Alembic, SQLite, Jinja2/HTMX/Alpine,
existing deterministic `capacity_engine.py`, IFS MCP/Oracle views, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-resource-assumption-registry-design.md`

## Global Constraints

- No active forecast may silently use `DEFAULT_SHIFT` in DB resource mode.
- Approved resource/assumption records are immutable; changes create effective-dated successors.
- Internal scenarios may use complete provisional inputs; commitment-ready forecasts require
  approved, commitment-ready, non-stale assumptions and horizon coverage.
- External IFS demand and tracked TwinWorks demand must never be double counted.
- Map coordinates and presentation metadata remain display-only.
- Preserve the current 40-unit seed golden forecast in legacy mode throughout migration.
- No BCA activation until BCA-03 and BCA-04 assumptions are approved.
- Every task uses a throwaway SQLite database and follows red-green-refactor.

---

## File Structure

**New domain/services**

- `app/services/resource_registry.py`: resource CRUD, immutable versioning, assumption validation.
- `app/services/resource_profile.py`: compile one deterministic profile and readiness result.
- `app/services/external_load_service.py`: immutable IFS CRP load snapshots and quality policy.
- `app/services/resource_explain.py`: readiness aggregation and unit/resource explanations.
- `app/services/assumption_drift.py`: weekly drift and recertification calculations.
- `app/routers/resources.py`: Resource Registry, assumption review, and Why endpoints.
- `app/templates/resources.html`, `resource_detail.html`, and partials: audit/review UI.

**Modified boundaries**

- `app/models.py` and one Alembic migration: normalized resource/assumption/snapshot tables.
- `app/engines/router_registry.py`: operation requirements in `ProgramSpec`.
- `app/engines/rtg_wrapper.py`: compile/select resource profile per run.
- `capacity_engine.py`: physical effort buckets, atomic occupancy leases, constraint events.
- `app/services/program_service.py`: activation state and resource-coverage gate.
- `app/services/forecast_service.py`, `forecast_log_service.py`: readiness/explanation snapshots.
- `app/templates/programs.html`, forecast/matrix/map templates: coverage and Why displays.

---

### Task 1: Persist Physical Resources and Assumption Provenance

**Files:**
- Modify: `app/models.py`
- Create: `alembic/versions/c7d9e2f4a6b8_resource_assumption_registry.py`
- Create: `app/services/resource_registry.py`
- Create: `tests/test_resource_registry.py`

**Interfaces:**
- Produces: `create_pool`, `add_capacity_version`, `add_binding`, `add_assumption`,
  `approve_assumption`, `supersede_assumption`, and `resource_coverage`.
- Consumers: all later tasks.

- [ ] **Step 1: Write failing model/service tests**

Test these observable behaviors with an isolated DB:

```python
async def test_approved_assumption_is_immutable_and_successor_closes_prior_version(db):
    first = await add_assumption(db, subject_type="POOL", subject_key="59:TRI_A",
        parameter="shift_capacity", value={"1": 20}, basis="OWNER_CONFIRMED",
        approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
        effective_from=date(2026, 9, 1))
    with pytest.raises(ApprovedRecordImmutable):
        await update_assumption(db, first.id, value={"1": 24})
    second = await supersede_assumption(db, first.id, value={"1": 24},
                                        effective_from=date(2026, 10, 1))
    assert second.supersedes_id == first.id
    assert first.effective_to == date(2026, 9, 30)
```

Also test overlapping capacity versions, retired pools, insufficient evidence for
`MEASURED_ACTUAL`, invalid commitment grade, and binding release-op validation.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_resource_registry.py`
Expected: import/model failures because the registry does not exist.

- [ ] **Step 3: Add schema and migration**

Add tables from the spec: `resource_pool`, `resource_instance`, `model_assumption`,
`resource_capacity_version`, `operation_resource_binding`, `external_load_snapshot`,
`external_load_row`, `simulation_snapshot`, `forecast_constraint_event`, and
`assumption_review`. Add nullable `simulation_snapshot_id` to `forecast_log`.

Use check constraints for all enums and unique constraints for pool identity and effective-version
ranges. Set migration `down_revision = "b4e2f7a1c8d9"`.

- [ ] **Step 4: Implement minimal immutable registry service**

Use dataclasses for the external interface:

```python
@dataclass(frozen=True)
class CoverageIssue:
    subject_key: str
    parameter: str
    severity: str       # MISSING | PROVISIONAL | STALE
    reason: str

async def resource_coverage(db, program: str, as_of: date) -> list[CoverageIssue]:
    raise NotImplementedError
```

Approval validates evidence count, effective ranges, resource type/unit compatibility, and routing
operation references. Approved rows cannot be updated or deleted through the service.

- [ ] **Step 5: Run migration and tests**

Run:

```powershell
$env:RTG_DATABASE_URL='sqlite+aiosqlite:///./data/_resource_registry_test.db'
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests\test_resource_registry.py
```

Expected: PASS. Remove the throwaway DB.

- [ ] **Step 6: Commit**

```powershell
git add app/models.py app/services/resource_registry.py alembic/versions/c7d9e2f4a6b8_resource_assumption_registry.py tests/test_resource_registry.py
git commit -m "feat: add resource and assumption registry"
```

---

### Task 2: Compile Immutable Simulation Snapshots and Seed Legacy Parity

**Files:**
- Create: `app/services/resource_profile.py`
- Modify: `app/engines/rtg_wrapper.py`
- Modify: `app/config.py`
- Create: `tests/test_resource_profile.py`
- Modify: `tests/test_regression.py`

**Interfaces:**
- Consumes: Task 1 registry records.
- Produces:

```python
@dataclass(frozen=True)
class CompiledResourceProfile:
    mode: str
    pools: dict
    wc_to_pool: dict[str, str]
    requirements: dict[tuple[str, int], tuple]
    external_load: dict
    assumptions: tuple[int, ...]
    readiness: str
    unresolved: tuple[CoverageIssue, ...]
    snapshot_hash: str

async def compile_profile(db, programs, as_of, horizon_end, mode) -> CompiledResourceProfile:
    raise NotImplementedError
```

- [ ] **Step 1: Write failing legacy-parity tests**

Seed one DB pool per legacy `(program, WC)` plus existing cure-station slots. Assert the compiled
profile reproduces `routers.WC_SHIFT`, crew, DPAS, cure rules, and the current golden forecast
exactly in `DB_SHADOW` mode.

- [ ] **Step 2: Verify RED**

Run: `pytest -q tests/test_resource_profile.py tests/test_regression.py`
Expected: missing compiler/seeder failures.

- [ ] **Step 3: Implement legacy seeding and canonical snapshot hashing**

`seed_legacy_resources(db)` must be idempotent. Serialize resolved inputs with sorted keys and no
current-table references, then hash SHA-256. Persist the exact JSON in `simulation_snapshot`.

Add `RTG_RESOURCE_SOURCE=legacy|db-shadow|db-active` as the process default, but pass the selected
mode into every compiled profile and snapshot so concurrent/replay runs do not depend on mutable
global state.

- [ ] **Step 4: Connect wrapper in shadow mode**

Legacy remains authoritative. `rtg_wrapper.run_pooled` compiles/records the DB profile only when a
DB session/profile is supplied and returns a parity comparison object outside the public forecast
result. No dates may change.

- [ ] **Step 5: Verify parity**

Run full pytest and `python -m tests.golden check`. Expected: no diff.

- [ ] **Step 6: Commit**

```powershell
git add app/config.py app/engines/rtg_wrapper.py app/services/resource_profile.py tests/test_resource_profile.py tests/test_regression.py
git commit -m "feat: compile resource snapshots with legacy parity"
```

---

### Task 3: Ship Assumption Readiness and Why UI Before Math Changes

**Files:**
- Create: `app/services/resource_explain.py`
- Create: `app/routers/resources.py`
- Create: `app/templates/resources.html`
- Create: `app/templates/resource_detail.html`
- Create: `app/templates/partials/forecast_why.html`
- Modify: `app/templates/base.html`, `forecast.html`, `matrix.html`, `factory_map.html`
- Modify: `app/main.py`, `app/services/forecast_service.py`, `app/services/forecast_log_service.py`
- Create: `tests/test_resource_explain.py`, `tests/test_resource_routes.py`

**Interfaces:**
- Produces: `forecast_readiness(program, serial, maxop, snapshot)` and
  `explain_forecast(program, serial, simulation_result, snapshot)`.

- [ ] **Step 1: Write failing readiness aggregation tests**

Assert worst-state ordering `INCOMPLETE > PROVISIONAL > COMPLETE`, stale assumptions produce
`PROVISIONAL`, commitment-ready approval produces `COMPLETE`, and oversubscription is an independent
flag. Only resources on the remaining route participate.

- [ ] **Step 2: Write failing route/template tests**

Assert `/admin/resources`, `/admin/resources/{code}`, and the forecast Why partial expose basis,
approval, commitment grade, evidence window/method, owner, effective/review dates, and current
legacy values. Assert no POST action silently approves a record.

- [ ] **Step 3: Implement Resource Registry and Why UI**

The first release explains legacy-equivalent values before DB capacity changes math. Add a
readiness badge to forecast/matrix/map. `stamp_build` links each forecast row to its immutable
snapshot.

- [ ] **Step 4: Add current labor wait tracing without changing scheduling**

Instrument the current budget-exhausted branch to emit `ForecastConstraintEvent` records while
leaving allocation order and dates unchanged. Use one event term everywhere.

- [ ] **Step 5: Verify**

Run route tests, golden test, full suite, and desktop/narrow visual captures. Expected: exact dates,
new explanations visible.

- [ ] **Step 6: Commit**

```powershell
git add app/main.py app/routers/resources.py app/services/resource_explain.py app/services/forecast_service.py app/services/forecast_log_service.py app/templates tests
git commit -m "feat: expose forecast assumptions and resource explanations"
```

---

### Task 4: Activate Physical Labor Pools and Remove DB-Mode Defaults

**Progress 2026-09-01:** the pool-ID scheduler, hybrid transition behavior, static reserve,
finite-calendar gate, DB-active fail-closed behavior, immutable OBSERVE successor, replay, and
causal comparison are implemented and tested. No BCA pool was created because owner-approved
capacity/calendar/reserve inputs are still outstanding. The separate onboarding activation UI and
first live BCA shadow report remain open. See
`docs/validation/bca-03b-physical-pool-shadow.md`.

**Files:**
- Modify: `capacity_engine.py`, `app/engines/rtg_wrapper.py`
- Modify: `app/services/resource_profile.py`, `program_service.py`
- Modify: `app/routers/admin.py`, `app/templates/programs.html`
- Create: `tests/test_physical_resource_pooling.py`, `tests/test_program_resource_gate.py`

**Interfaces:**
- Consumes: `CompiledResourceProfile`.
- Produces physical pool contention and separate Save Draft / Activate Program gates.

- [ ] **Step 1: Write failing physical-pool tests**

Two programs bound to one pool must consume one budget, even if their WC labels differ. One program
bound to two separate pools must not merge them. Missing profiles must raise
`ResourceProfileIncomplete` in DB-active commitment mode.

- [ ] **Step 2: Write failing onboarding gate tests**

Save Draft accepts complete provisional assumptions. Activate Program blocks `INCOMPLETE` and
allows `PROVISIONAL` only for internal simulation. Commitment-ready activation requires `COMPLETE`.
Acknowledging an unknown WC must not create capacity.

- [ ] **Step 3: Implement pool-driven effort allocation**

Replace `(program, WC)` bucket identity with compiled pool ID in DB-active mode. Legacy behavior is
unchanged in legacy mode. Compute raw net capacity, use `max(0, raw_net)` for allocation, and emit an
oversubscription event when raw net is negative.

- [ ] **Step 4: Add explainable migration diff**

B1 one-to-one seeded pools require exact golden parity. B2 shared-pool collapse creates a report of
unit date changes, resource waits, old/new pool identity, and assumption versions. Require owner
sign-off; do not blindly recapture the golden file.

- [ ] **Step 5: Verify and commit**

Run focused tests and full suite in both legacy and DB-shadow modes.

```powershell
git add capacity_engine.py app/engines/rtg_wrapper.py app/services/resource_profile.py app/services/program_service.py app/routers/admin.py app/templates/programs.html tests
git commit -m "feat: schedule against physical labor pools"
```

---

### Task 5: Ingest Dynamic External Demand and Detect Shared Consumers

**Files:**
- Create: `app/services/external_load_service.py`
- Create: `app/data/ifs_external_load.py`
- Modify: `app/services/resource_profile.py`
- Modify: `app/templates/resource_detail.html`, `factory_map.html`
- Create: `tests/test_external_load.py`, `tests/test_shared_resource_discovery.py`

**Interfaces:**
- Produces `capture_external_load(client, pools, tracked_programs, as_of, horizon_end)` and
  `resolve_external_reserve(snapshot, pool, date, shift)`.

- [ ] **Step 1: Write failing source-quality and double-count tests**

Released SO rows default weight 1; PMRP rows default suspect/weight 0. Rows tied to tracked shop
orders/projects are excluded from reserve. When C17 is untracked it is external; when registered it
moves to tracked demand without changing total physical load.

- [ ] **Step 2: Write failing horizon/shift tests**

Commitment-ready compilation must fail past `horizon_covered_until` without an approved policy.
Day-level load apportions by an approved shift-weight assumption. Test `BLOCK`,
`HOLD_LAST_COMPLETE_WEEK`, and `TRAILING_MEAN` deterministically.

- [ ] **Step 3: Implement immutable CRP ingestion**

Read `CRP_ORDER_LOAD2` and join released `ORDER_REF1` rows to shop orders/projects. Materialize all
rows; never reference the live view during replay. Record source schema version and quality reasons.
Do not use IFS `LOAD_PCT` or infinite-WC `WC_CAP` as physical truth.

- [ ] **Step 4: Add shadow collision monitor and BCA/C17 report**

Automatically derive shared pools from bindings. Generate before/after C17 actuals, current BCA/C17
load, and counterfactual external load for the verified intersection. Show other consumers rather
than assigning capacity ownership percentages.

- [ ] **Step 5: Activate external subtraction only after approval**

The active profile uses gross capacity minus approved external reserve. Preserve raw negative net
and expose the deficit event; schedulable hours floor at zero.

- [ ] **Step 6: Verify and commit**

```powershell
git add app/data/ifs_external_load.py app/services/external_load_service.py app/services/resource_profile.py app/templates tests
git commit -m "feat: model dynamic external resource demand"
```

---

### Task 6: Generalize the Discrete Occupancy Allocator

**Files:**
- Modify: `capacity_engine.py`, `app/services/resource_profile.py`
- Modify: `routers.py`, `tests/test_cure_station_contention.py`
- Create: `tests/test_resource_occupancy.py`

**Interfaces:**
- Consumes approved `OCCUPANCY` bindings.
- Produces deterministic slot leases and constraint events.

- [ ] **Step 1: Write failing allocator tests**

Cover: two fungible slots run concurrently; third waits; cross-operation hold; release on op/cure;
minimum hold; specific-instance request; atomic two-tool acquisition; deterministic output under
ready-unit input reordering; invalid release op rejected; no-progress assertion fails loudly.

- [ ] **Step 2: Implement all-or-nothing acquisition**

At each ready event, check all occupancy requirements first. Acquire none unless all can be granted.
Requeue at the earliest missing release using `(ready_time, priority, serial, pool_id)`. Store held
leases in unit state and release only at validated events.

- [ ] **Step 3: Migrate cure stations through the same interface**

Translate current P2 paint-booth and P3 electrical-seal rules into occupancy bindings in DB-shadow
mode. Prove exact cure-contention and golden parity before activating.

- [ ] **Step 4: Verify and commit**

```powershell
git add capacity_engine.py app/services/resource_profile.py routers.py tests/test_resource_occupancy.py tests/test_cure_station_contention.py
git commit -m "feat: add deterministic resource occupancy leases"
```

---

### Task 7: Add Aeronose Tooling as Draft Constraints

**Files:**
- Create: `app/services/tooling_seed.py`
- Modify: `app/templates/resource_detail.html`, `app/templates/programs.html`
- Create: `tests/test_aeronose_tooling.py`
- Update: `TASKS.md`, `MASTER.md`

**Interfaces:**
- Seeds draft pools without activating unverified occupancy spans.

- [ ] **Step 1: Write failing seed/idempotency tests**

Assert draft pools and owner-supplied count assumptions:

```python
{
  "AERONOSE_ASSEMBLY_JIG": 2,
  "AERONOSE_HOLDING_FIXTURE": 2,
  "AERONOSE_TRIM_FIXTURE": 1,
  "AERONOSE_SHELL_LAM_MOLD": 3,
  "AERONOSE_CORE_FORM_MOLD_SET": 1,
}
```

All use `SLOTS`, basis `OWNER_CONFIRMED`, and remain `INTERNAL_ONLY` until acquire/release bindings
are approved. Re-running the seed creates no duplicates.

- [ ] **Step 2: Add binding-review workflow**

The UI requires current routing revision, acquire op, release event/op/cure, quantity, fungibility,
minimum hold, evidence, owner, and review date. Approval validation refuses absent routing events.

- [ ] **Step 3: Shadow tooling forecasts**

Compare baseline and tooling-constrained Aeronose dates. Present tool occupancy timeline and wait
causes. Do not activate commitment forecasts until the floor owner approves every required span.

- [ ] **Step 4: Verify and commit**

```powershell
git add app/services/tooling_seed.py app/templates tests/test_aeronose_tooling.py TASKS.md MASTER.md
git commit -m "feat: register Aeronose tooling constraints"
```

---

### Task 8: Add Drift, Expiry, and Recertification Governance

**Status:** Completed 2026-08-31. The implementation also records migrated-evidence attestation
and missing drift-policy debt, uses immutable successor capacity versions, and provides a permanent
JSON audit export.

**Files:**
- Create: `app/services/assumption_drift.py`
- Modify: `app/routers/resources.py`, resource templates, sync workflow
- Create: `tests/test_assumption_drift.py`

**Interfaces:**
- Produces `build_drift_report(db, as_of)` and assumption review items.

- [x] **Step 1: Write failing drift tests**

A pool-specific window compares current actual P80 with its approved evidence value. Crossing the
approved threshold creates one idempotent review item and moves readiness to provisional. It never
changes the capacity value. Sparse evidence creates a review note, not a measured estimate.

- [x] **Step 2: Implement recertification workflow**

Owners can approve unchanged, supersede with a new version, or reject the recommendation. Review
date expiry and drift use the same queue. Every action is timestamped and linked to evidence.

- [x] **Step 3: Add UI and notifications**

Show assumption debt and due reviews on Admin and Resource Registry pages. Do not send email or
external notifications in this task.

- [x] **Step 4: Verify**

```powershell
git add app/services/assumption_drift.py app/routers/resources.py app/templates tests/test_assumption_drift.py
git commit -m "feat: add assumption recertification workflow"
```

---

### Task 9: BCA Pilot, Replay, and Stabilization Gate

**Status:** Historical replay and incumbent parity are complete. BCA/C17 validation, the live
pilot, and fallback-retirement decision remain open.

**Files:**
- Modify: `TASKS.md`, `AGENTS.md`, `MASTER.md`, `CHANGELOG.md`
- Create: `tests/test_simulation_snapshot_replay.py`
- Create: `docs/validation/bca-resource-pilot.md`

**Interfaces:**
- Produces the acceptance evidence required before legacy fallback retirement.

- [ ] **Step 1: Validate BCA/C17 pool profiles**

Use the evidence report plus named owner decisions for `TRI L`, `ATUP`, `P3TRI`, `TRI A`, `236`,
`PRNG`, `P3NDI`, `P3 QA`, `3FINL`, and `235`. Record gross/effective scope, external policy,
shift weights, horizon policy, and review dates. Do not use P80 actuals as automatic capacity.

- [x] **Step 2: Write historical replay test**

Persist a simulation snapshot, supersede capacity/assumptions, replay the old snapshot, and assert
identical output hash and dates.

- [ ] **Step 3: Run shadow and active acceptance**

For 2-4 weeks, require zero critical defects, no unexplained seed-program drift, no deadlocks,
external horizon coverage through every forecast, and owner approval of all commitment-grade pools.
Compare legacy versus DB-active results with constraint-event explanations.

- [ ] **Step 4: Authorize or reject fallback retirement**

Only after signed acceptance, change the default resource mode to DB-active and retain per-run legacy
rollback for one additional accepted pilot cycle. Record the decision and evidence in the validation
document and changelog.

- [ ] **Step 5: Final verification and commit**

Run Alembic upgrade on a fresh DB, full pytest, golden check, live IFS smoke test, and desktop/mobile
walkthrough of resources, assumptions, forecast Why, Factory Map, and onboarding.

```powershell
git add TASKS.md AGENTS.md MASTER.md CHANGELOG.md docs/validation/bca-resource-pilot.md tests/test_simulation_snapshot_replay.py
git commit -m "chore: complete resource registry pilot gate"
```
