# Administration Runbook

## Before a refresh

1. Confirm the intended data source and active-program list.
2. Verify IFS authentication for live mode.
3. Ensure no sync run is already active.

## Refresh positions

The refresh reads each active program, updates position state, invalidates the local cache, and
stamps only published programs. Review unknown serials and newly stalled units before relying on the
result.

## Resource changes

Approved assumptions and capacity versions are immutable. Correct them through governed successor
records. Draft tooling counts do not affect scheduling until approved occupancy bindings exist.

## Recovery

Use a tested database backup and the published legacy epoch as rollback controls. Never delete audit
events, model epochs, simulation snapshots, or deactivated program history to make a view look clean.
## Accuracy summaries

Processing a physical shipment now refreshes the model-maturity cohort and appends immutable
Accuracy v1.0 summaries for all active programs. Same-day/post-pack forecasts, administrative
close-only records, and forecasts outside the fixed horizon windows do not enter the score. Review
each program's Accuracy tab after processing shipments; a missing headline means the evidence gate
has not been met, not that the calculation failed.
