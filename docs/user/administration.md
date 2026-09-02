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
