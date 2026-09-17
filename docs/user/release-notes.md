# Release Notes

## 2026-09-17

- Added a replayable Aeronose op-775 `OBSERVE` candidate that retains the 40-hour cure while removing
  the false fixed-station reservation; published forecasts remain on `RAD:LEGACY`.
- Added a separate `DRAFT` candidate for the proposed DRDI-controlled 2-hour flashoff plus 8-hour
  cure. It cannot run until complete approval evidence is recorded.
- Added the RATE-01a/b planning foundation for deterministic monthly/annual/profile demand,
  working-calendar releases, future-release enforcement, readiness/staffing gates, and
  measurement-only backlog sustainability. No owner-facing sizing recommendation is enabled yet.

## 2026-09-09

- Corrected shipment detection to require the configured Pack & Ship operation to be closed before
  accepting its latest finish clock.
- Added explicit ship-date reconciliation for previously recorded shop orders and shop-order-based
  forecast backfill across zero-padded serial variants.
- Versioned corrected accuracy evidence as `TW-ACC-1.1`; prior immutable v1.0 summaries remain in
  history.

## 2026-09-04

- Added critic-reviewed Accuracy v1.0 scores at fixed 7-, 14-, and 21-day horizons using only IFS
  physical pack dates.
- Added confidence tiers, headline gating, separate P80 Wilson coverage, immutable daily score
  summaries, and frozen cohort provenance.
- Added portfolio Accuracy signals and a responsive program Accuracy workspace.
- Removed same-day/post-pack and administrative-close-only records from forward model-maturity
  counts; current eligible counts are Elevator 3, Aeronose 1, and Aegis 1.
## 2026-09-03

- Recorded the Aeronose tooling owner/approver, program dedication, and fungibility decisions while
  retaining draft, internal-only status and zero schedule bindings.
- Reconciled controlled LAM, COREKIT, ASSY, and PAINT work instructions to live top-assembly,
  subring, and core-kit IFS routes.
- Confirmed op 775 is a dolly-based 40-hour part cure with no fixed station; its legacy one-slot rule
  now awaits removal in a governed successor candidate.
- Added a repeatable read-only IFS timing audit and documented the remaining component-link,
  mid-operation release, jig-release, holding-fixture, and current-WIP gates.
- Added the critic-reviewed plan for authenticated, append-only tooling availability controls and
  the consolidated floor-question handoff. The initial shell-mold outage remains shadow-only.
- Added the AVAIL-01 event foundation: immutable outage lifecycle, pooled count folding, SQLite
  concurrency guards, startup verification, and permanent audit export. No event or forecast effect
  is active yet.

## 2026-09-02

- Active TwinWorks scope is Elevator, Aeronose, and Aegis.
- BCA was archived outside active navigation, refresh, simulation, and forecast output while its
  immutable evidence was retained.
- Aeronose tooling counts were registered as draft inventory facts with no schedule bindings.
- The generic occupancy allocator now supports atomic tooling leases, maintenance windows, as-of
  holdings, deterministic retry, and replayable events while preserving cure-station forecasts.
- The in-app Handbook was added at `/handbook`.

## 2026-09-01

- Added the portfolio operations console and seven-tab program workspaces.
- Added governed model epochs, planning-basis isolation, assumption recertification, and exact
  simulation replay.
- Added the Marion Factory Map as a read-only visual decision layer.

Detailed engineering history remains in the source-controlled project changelog.
