# RATE-01b Demand and Capacity Foundation

## Status

Delivered 2026-09-17. RATE-01b provides deterministic demand integration and analytical bounds but
does not yet produce owner-facing hiring or procurement packages. Calibration remains RATE-01c.

## Demand Ledger

- Customer demand uses explicit production `release_month`; customer due dates are not silently
  treated as release dates.
- Exact order identity nets only the quantity already represented by tracked WIP.
- Duplicate demand keys and cross-program order collisions fail closed.
- Netted demand converts to namespaced `RATE:` units with no operational shop-order identity.
- Required shared-program WIP must be supplied, including empty program lists when coverage is
  known to be zero; omitted shared programs fail closed.
- Synthetic releases and inherited WIP are copied into the demand set without modifying sources.

## External Demand

- RATE-01b consumes the immutable external-load snapshot assessment and its horizon policy.
- Rows classified as tracked projects are excluded defensively even if upstream quality is `OK`.
- Explicitly excluded and nonlabor rows do not enter labor demand.
- `SUSPECT` rows retain their governed weight and downgrade readiness to `PROVISIONAL`.
- Missing horizon coverage under `BLOCK` produces `UNRESOLVED`.
- Weighted hours are exposed by pool/shift/month for audit and by stable pool code/month for capacity
  bounds.

## Analytical Bounds and Search

- Remaining route labor uses raw labor hours and requires an explicit physical pool mapping for
  every remaining operation.
- External hours add to the same physical-pool bound without becoming synthetic tracked units.
- Tool bounds calculate peak concurrent pooled slots from half-open `[start, end)` leases; a tool
  released exactly when another unit acquires it is reusable.
- Sustainable-rate search evaluates the full bounded discrete grid rather than assuming monotonic
  feasibility. Exhausted evaluation bounds return `SEARCH_INCOMPLETE`, never `INFEASIBLE`.

## Verification

- Exact quantity netting and exclusion provenance.
- Duplicate/cross-program identity rejection.
- Shared-program coverage enforcement.
- Scenario-only release conversion.
- External quality, weighting, tracked-row exclusion, stable pool mapping, and coverage readiness.
- Analytical labor fixture and input-order invariance.
- Tool overlap and touching-boundary reuse.
- Nonmonotonic feasible-rate selection and bounded-search diagnostics.

No operational WIP, forecast log, plan slot, model epoch, or IFS record is modified by RATE-01b.

Full verification: 153 tests passed with the existing warning set, Ruff passed, and the static
golden forecast remained exact.
