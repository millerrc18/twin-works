# Data Sources and Freshness

TwinWorks can run from a live authenticated IFS connection or the local operational snapshot.

## Live refresh

The position refresh reads active configured programs, resolves serials from shop-order notes,
updates the mutable position state, and stamps eligible published forecasts. Processing shipments
uses the physical pack operation when available, then the administrative close date.

## Snapshot fallback

If a live query fails, the application continues from the last persisted snapshot rather than
returning an empty or partially mixed result. The page identifies the source and freshness.

## Important boundaries

- Inactive programs are excluded at registry and sync ingress.
- Historical positions and audit events remain stored after deactivation.
- Fixed-horizon Accuracy v1.0, forward model-maturity counts, and retrospective backtesting are
  separate evidence tracks.
- Same-day/post-ship forecasts and administrative-close-only units are excluded from forward
  accuracy; missing horizon windows remain visible.
- Source age and incomplete coverage must be visible; they cannot be relabeled as current.
