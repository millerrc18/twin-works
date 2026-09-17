# RATE-01a/b Foundation

## Status

Initial foundation delivered 2026-09-17. It is pure, scenario-only, and not exposed as an
owner-facing recommendation surface.

## Delivered Contracts

- Active-program enforcement excludes inactive BCA.
- Monthly and annual rates canonicalize to integer monthly demand through cumulative decimal
  allocation; annual totals are not lost to independent monthly rounding.
- Explicit monthly profiles and route-distinct product mixes allocate deterministically.
- Working-day release calendars honor shutdown dates.
- Synthetic IDs are namespaced `RATE:` and carry no operational shop-order identity.
- `release_at` prevents future synthetic demand from entering the scheduler early.
- Readiness is `READY`, `PROVISIONAL`, or `UNRESOLVED`; unresolved tooling returns no numeric tool
  addition rather than zero.
- Missing productive-hours evidence returns an hours gap without a headcount claim.
- Sustainability uses only the measurement window; cooldown backlog clearing cannot make an
  undersized system pass.

## Remaining RATE-01a/b Work

- Scenario/version/run persistence, joint package solver, calibration, and UI remain in RATE-01c
  through RATE-01g.

RATE-01a and RATE-01b are complete. No live staffing assumptions are seeded until their owners
provide evidence.

## Verification

- Focused RATE tests cover annual accumulation, profile demand, product mix, calendars, future
  release enforcement, readiness, staffing evidence, and cooldown isolation.
- Static legacy inputs omit `release_at`, preserving established scheduler behavior.
- Full regression after RATE-01b: 153 passed with the existing warning set.
- Focused Ruff: passed.
- Static golden forecast: exact.
