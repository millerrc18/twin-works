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

## Parity

The cure-station migration preserves the established reservation order and timestamps. Focused
cure tests and the static golden forecast are exact.

## Remaining Before TOOL-01b Closes

1. Compile approved `OCCUPANCY` bindings and slot capacities into immutable scheduler profiles.
2. Drive acquire/release events from the operation state machine, including atomic retry when a
   higher-priority request becomes available within a shift.
3. Apply future maintenance/unavailable intervals without incorrectly blocking earlier free time.
4. Persist or materialize lease events in replayable simulation results and Why explanations.
5. Prove fatal no-progress handling for a complete multi-unit scheduler run.

These remaining items do not require Aeronose operation spans, but Aeronose activation remains
blocked until TOOL-01c approves those spans.

## Verification

- Full regression suite: 87 passed.
- Focused Ruff: passed.
- Static golden forecast: exact.
- Live Aeronose draft tooling pools remain unbound and have no forecast effect.
