# TOOL-01b Occupancy Allocator Core

## Status

Core allocator and cure-station parity slice delivered 2026-09-02. The allocator is not yet wired
to approved Aeronose operation-span bindings, and no Aeronose tooling affects forecasts.

## Delivered

- Deterministic fixed-duration reservations across fungible or named slots.
- Atomic multi-pool requests: every requested slot is acquired or none are.
- Explicit queue key: ready time, DPAS-behind priority, commit date, program, serial, pool.
- Active acquire/release leases with minimum hold and post-release lag.
- Fatal `ResourceAllocationDeadlock` for impossible/unknown requests.
- Fatal `InvalidOccupancyRelease` for unmatched releases.
- In-memory reservation/acquire/release event history for causal integration.
- Existing Plant 2 paint-booth and Plant 3 electrical-seal cure reservations migrated to the same
  allocator.
- Approved occupancy bindings, slot capacities, and named instances compile into immutable
  scheduler/replay profiles.
- The scheduler acquires tools before the bound operation and releases on approved `OP_START`,
  `OP_COMPLETE`, `CURE_COMPLETE`, or `ROUTE_COMPLETE` events.
- Occupancy acquire/wait/release events are included in traced results and exact replay envelopes.

## Parity

The cure-station migration preserves the established reservation order and timestamps. Focused
cure tests and the static golden forecast are exact.

## Remaining Before TOOL-01b Closes

1. Apply future maintenance/unavailable intervals without incorrectly blocking earlier free time.
2. Reconstruct tools already held by units whose forecast starts between acquire and release ops.
3. Revisit an occupancy-blocked higher-priority unit within the same shift when a lower-priority
   holder releases later in that shift.
4. Surface replayed lease events in Why explanations and prove fatal no-progress handling for a
   complete multi-unit scheduler run.

These remaining items do not require Aeronose operation spans, but Aeronose activation remains
blocked until TOOL-01c approves those spans.

## Verification

- Full regression suite: 91 passed.
- Focused Ruff: passed.
- Static golden forecast: exact.
- Live Aeronose draft tooling pools remain unbound and have no forecast effect.
