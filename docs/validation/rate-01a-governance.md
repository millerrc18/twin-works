# RATE-01a Governance

## Status

Delivered 2026-09-17. This foundation governs context and staffing evidence; it does not calculate
or display hiring recommendations.

## Baseline Context

`build_rate_baseline_context` accepts either the current published epochs or an exact explicit set
of runnable candidate epochs. It rejects inactive/unknown programs, partial candidate selection,
published/candidate mixing, and mixed resource modes. The selected epoch keys, definition hashes,
lifecycle state, resource mode, resource profile, readiness, as-of date, and horizon are persisted
in the existing immutable `SimulationSnapshot` envelope. Identical inputs reuse the same content
hash and snapshot.

## Staffing Evidence

`record_skill_evidence` attaches one effective-dated `rate_staffing_model` assumption to an actual
`LABOR/HOURS` pool. Its canonical value contains:

- current FTE;
- productive hours per FTE;
- eligible work centers and shifts;
- nondecreasing new-hire learning curve;
- retention/training-completion yield;
- effective and review dates.

Approved records require complete versioned evidence, owner, approver, and commitment-ready status.
Draft, internal-only, or past-review records load as `PROVISIONAL`. Nonlabor pools, invalid curves,
invalid yields, missing eligibility, and overlapping effective ranges fail closed. Existing approved
assumption immutability applies unchanged.

## Verification

- Published baseline persistence and idempotency.
- Exact candidate-epoch coverage rejection.
- Approved staffing evidence round trip.
- Nonlabor pool and decreasing learning-curve rejection.
- Draft/stale readiness downgrade.
- Effective-range overlap rejection.

No production staffing values were invented or seeded as part of RATE-01a.

Full verification: 139 tests passed, Ruff passed, and the static golden forecast remained exact.
