# TOOL-01c1 Availability Event Foundation

## Status

AVAIL-01 delivered 2026-09-03. TwinWorks now has an additive, append-only availability-event
foundation for finite tooling outages. No availability event has been written to the live database,
no tooling binding was created, and no published or shadow forecast behavior changed.

## Delivered

- `ResourceAvailabilityEvent` persists one immutable event in an outage lifecycle.
- Supported events: `OUTAGE_OPEN`, `EXTEND`, `RETURN_TO_SERVICE`, `CANCEL`, and retrospective `VOID`.
- Events store unavailable quantity rather than absolute available capacity, so a future baseline
  increase does not erase or misstate an existing one-tool outage.
- Phase 1 accepts `TOOL` / `SLOTS` pools. Optional instance identity is reserved for a later serial
  and preventive-maintenance feature.
- Strict service input requires offset-zero, timezone-aware UTC timestamps. SQLite stores normalized
  UTC values; the application fold restores UTC-aware datetimes.
- A pure fold creates end-exclusive outage and pooled-availability intervals, merges deterministic
  segments, and rejects aggregate unavailable quantity above the effective baseline.
- Future cancellation and retrospective voiding are separate: `CANCEL` is allowed before an outage
  begins; `VOID` records that a previously entered outage never occurred without deleting history.
- The permanent resource audit export includes the full event stream.

## Database Controls

Migration `0a1b2c3d4e5f` creates `resource_availability_event` and five SQLite triggers:

1. lifecycle and identity validation;
2. aggregate overlapping-quantity validation under the SQLite writer lock;
3. append-only insert identity protection;
4. update rejection;
5. delete rejection.

Startup governance integrity now requires all five triggers. Direct `UPDATE`, `DELETE`,
`INSERT OR REPLACE`, invalid first transitions, and overlapping outages above the effective
baseline fail closed.

## Critic Correction

Gemini 3.1 Pro identified two material risks in the initial implementation:

- Python-only aggregate validation allowed a concurrent write-skew race.
- Future-only cancellation could not represent a retrospective correction.
- An early-only return event could not record an on-time or late actual return honestly.

The final implementation adds a database aggregate-capacity trigger, append-only `VOID`, and a
unified `RETURN_TO_SERVICE` event for early, on-time, or late actual return. The planned compiler will enforce pooled count reductions directly and will not map a
count-only outage to an invented physical serial.

## Deployment

The local live database is at Alembic head `0a1b2c3d4e5f`; the event table is empty.

Pre-migration backup:
`data/rtg_app_migrated.pre_resource_availability_events.bak`

SHA-256:
`A991978507424B3B25A109321F756217B9F1B15521EE8171D766AEF00A399C65`

A clean database upgrade from base through head also passed.

## Verification

- Full regression suite: 110 passed.
- Focused availability/model-governance suite: 14 passed.
- Focused Ruff: passed.
- Static golden forecast: exact.
- Live governance-trigger inventory: complete.

## Remaining Phases

- AVAIL-02: validated application identity, server-derived roles, secure session, and CSRF.
- AVAIL-03: pooled capacity-reduction compiler, WIP conflict detection, candidate succession,
  immutable snapshot/replay integration.
- AVAIL-04: Resource Registry availability timeline and previewed authoring workflow.
- AVAIL-05: create the provisional shell-mold outage event, reconstruct IFS holders, and run the
  0/2/4-hour shell/core turnaround sensitivities.

No availability write route may be added before AVAIL-02 passes.