# TOOL-01b Occupancy Allocator Core

## Status

Allocator, scheduler integration, maintenance handling, and cure-station parity delivered
2026-09-02. No Aeronose tooling affects forecasts because its operation spans remain unapproved.

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
- Reviewed future maintenance intervals preserve earlier free windows and block overlapping holds.
- Tools already held by as-of WIP are reconstructed conservatively from acquire/release spans.
- Occupancy waiters retry deterministically within the same shift after a holder releases.
- Over-capacity as-of holdings and 1,200-shift no-progress exhaustions fail the whole run.

## Parity

The cure-station migration preserves the established reservation order and timestamps. Focused
cure tests and the static golden forecast are exact.

## Post-Allocator Work

1. TOOL-01c must approve Aeronose tool identity, operation spans, and release events.
2. TOOL-01d surfaces replayed lease events in Why and occupancy timeline views.
3. Floor validation must confirm reconstructed as-of holdings against actual assigned tools.

These remaining items do not require Aeronose operation spans, but Aeronose activation remains
blocked until TOOL-01c approves those spans.

## Verification

- Full regression suite: 96 passed.
- Focused Ruff: passed.
- Static golden forecast: exact.
- Live Aeronose draft tooling pools remain unbound and have no forecast effect.
