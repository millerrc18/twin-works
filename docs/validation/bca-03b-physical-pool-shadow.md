# BCA-03b Physical Labor-Pool Shadow

## Status

**Deferred and archived 2026-09-02:** BCA is no longer active TwinWorks product scope. `BCAFIN` is
inactive and its candidate epoch is archived. This record is retained as historical evidence. The
generic physical-pool scheduler/governance work is carried forward as RES-01 for Elevator,
Aeronose, and Aegis; no BCA pool will be created or refreshed.

The physical-pool scheduler, governance gate, immutable candidate definition, replay path, and
explainable comparison are implemented. No BCA capacity value has been inferred from IFS actuals,
and no physical BCA pool has been written to the live database. Published ELEV, RAD, and AEGIS
epochs remain on the legacy model.

BCA-03b remains open at the floor-owner input gate. The software portion is ready to accept those
inputs without using `DEFAULT_SHIFT` or publishing shadow dates.

## Delivered Behavior

- Physical effort is keyed by stable pool code and operation binding, not by `(program, WC)`.
  Programs with different WC labels contend when their operations bind to the same pool.
- A physical pool receives one shift budget. Capacity is never multiplied by the number of
  consuming programs.
- `GROSS_SITE` capacity requires an explicit external-reserve policy. A static reserve has its own
  approved assumption and is subtracted before scheduling; negative raw net remains visible as an
  oversubscription event while schedulable capacity is floored at zero.
- Physical calendars require all seven weekday factors, an explicit exception-date map, and a
  finite coverage end. The engine fails when it reaches an uncovered date.
- Physical mode raises on an unbound operation or missing pool budget. It never consults
  `DEFAULT_SHIFT`.
- Mixed migration is supported: unchanged `LEGACY:*` bindings retain their explicit seeded
  budgets and legacy calendar behavior while selected operations move to a physical pool.
- `DB_ACTIVE` compilation fails closed on incomplete or provisional coverage and requires at least
  one physical effort pool. `DB_SHADOW` may retain provisional assumptions for internal comparison.
- Physical shadow epochs freeze routing, bindings, capacity versions, calendars, reserve policies,
  and assumption IDs. Creating one appends an `OBSERVE` candidate and verifies that publication did
  not change.
- Shadow comparison runs deep-copied identical WIP through baseline and candidate profiles. For
  every changed unit it reports finish delta, causal pool codes, assumption IDs, and wait intervals
  with gross, reserve, schedulable, requested, and allocated hours.

## Owner Input Contract

`define_physical_labor_pool` is create-only and requires all of the following before a pool can be
created:

1. Pool identity, site, name, and covered program/operation numbers.
2. Gross-site or net-tracked scope.
3. Hours by shift.
4. Seven weekday factors, reviewed exception dates, and calendar coverage end.
5. External reserve by shift for gross-site capacity, including an explicit zero when appropriate.
6. Owner, approver, evidence source, calculation method, effective date, and review date.

The service validates every requested routing operation before writing anything, creates separate
capacity and reserve assumptions, supersedes the prior effort bindings, and leaves transaction
commit control with the caller. Later changes must use successor assumptions/capacity versions.

## BCA Inputs Still Required

| Pool candidate | IFS evidence | Required owner decision |
| --- | --- | --- |
| `P3TRI` | P80 active week 64.55 h; peak 87.72 h | Sustainable staffing by shift, calendar, and external reserve |
| `TRI A` | P80 active week 127.14 h; peak 146.92 h | Concurrent assemblers, sustainable shift hours, and external reserve |
| `PRNG` | P80 active week 26.84 h; peak 47.47 h | Whether labor or range occupancy is controlling; BCA-04 may own the final constraint |
| `P3NDI` | One active week; broad non-BCA demand | Shared equipment/operator pool, calendar, and external reserve |

These figures remain utilization evidence only. They are not capacity values.

## Review Findings

Gemini 3.1 Pro reviewed the implementation boundary. Its material findings were incorporated:

- hybrid physical/legacy migration is explicit and replay-tested;
- physical priority ordering is deterministic;
- external snapshots are already materialized in immutable simulation snapshots, while live CRP
  ingestion and de-duplication remain BCA-03c;
- calendars now carry exception dates and a finite coverage end;
- oversubscription and partial allocation are visible in causal traces; and
- baseline and candidate comparisons use isolated WIP copies.

The requested Claude and GPT critic aliases returned unavailable-model errors; Gemini completed the
independent review.

## Verification

- Full pytest suite: 76 passed.
- Static golden forecast: exact, no incumbent date drift.
- Focused Ruff check on every changed Python file: passed.
- Repository-wide Ruff still reports pre-existing style debt in legacy workbook scripts; no new
  violations are present in this change.

## Restart Gate

No BCA follow-on is authorized. A future restart requires explicit product approval, current IFS
rediscovery, fresh resource/tooling approval, a new candidate epoch, and a new shadow pilot. The
existing observations and utilization envelopes cannot be reused as current capacity approval.
