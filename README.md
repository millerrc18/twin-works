# TwinWorks

TwinWorks is a manufacturing ship-date forecasting and decision-support application for GDMS
composite programs at Marion. It combines a finite-capacity simulation, a measured residual model,
IFS-backed position refreshes, and operational what-if levers.

RTG remains a domain term for Return-to-Green targets. The `RTG_` environment-variable prefix,
RTG plan files, and legacy Excel tracker scripts remain intentionally compatible with existing
operational workflows.

## What It Does

- Forecasts in-process units using shared work-center capacity, cure/dwell gates, and program
  priority rules.
- Shows matrix and summary views, RTG-target deltas, slip, bottlenecks, and what-if levers.
- Adds a Marion virtual-factory view that overlays reviewed Plant 2 and Plant 3 floor plans with
  read-only WIP, capacity, and forecast-risk signals.
- Provides a Resource Registry, assumption provenance, readiness badges, and unit-level Why panels
  in legacy-shadow mode; resource records do not change allocation until separately activated.
- Supports fail-closed physical labor-pool shadows with immutable calendars, explicit external
  reserves, cross-program contention, exact replay, and causal baseline-versus-candidate diffs.
- Preserves published legacy forecasts while replayable `OBSERVE` candidates validate DB-backed
  resource profiles and surface assumption-review debt without publishing shadow dates.
- Provides a portfolio operating console and shared program workspaces with lifecycle-safe Overview,
  Schedule, Flow, Units, Resources, Assumptions, and History views.
- Rejects external-load inputs that do not cover the forecast horizon unless a governed
  extrapolation policy is present.
- Quarantines inconsistent source records in an append-only audit stream before they can affect
  WIP, capacity, or shared-resource conclusions.
- Supports offline snapshot mode and OAuth-backed live IFS refreshes.
- Keeps model status honest: empirical residual bias until sufficient forward-scored ships justify
  trained P50/P80 models.

## Run Locally

Windows PowerShell:

```powershell
.\run.ps1 snapshot 8215
```

Then open `http://localhost:8215`. Snapshot mode is safe for development and demos. For live IFS
mode, run `.\run.ps1 live 8215` and use **Connect IFS** in the browser; OAuth callback and app port
must match.

## Test

```powershell
$env:RTG_DATA_SOURCE = 'snapshot'
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

The golden master covers the 40 static bootstrap units for the ELEV, RAD, and AEGIS seed programs.
Do not recapture it after a live sync. Recapture only when an intentional static forecast change is
reviewed and documented.

## Repository Guide

- `AGENTS.md`: active engineering handoff, guardrails, and live work status.
- `TASKS.md`: prioritized implementation backlog.
- `docs/plans/82-marion-virtual-factory-capacity-map.md`: #82 scope, mapping contract, and
  Phase 1 delivery record.
- `docs/plans/three-program-tooling-roadmap.md`: current product boundary and Aeronose-first
  tooling execution plan.
- `docs/plans/tooling-availability-control.md`: critic-reviewed design for authenticated, append-only
  tooling outage and early-return controls.
- `docs/superpowers/specs/2026-08-27-resource-assumption-registry-design.md`: shared resources,
  external demand, tooling, and assumption-governance architecture.
- `docs/superpowers/plans/2026-08-27-resource-assumption-registry-plan.md`: phased TDD execution plan.
- `MASTER.md`: architecture and operating reference.
- `RTG_TRACKER_HANDOFF.md`: historical Excel-workbook workflow; it is not the active app handoff.
- `app/`: FastAPI application, services, data sources, templates, and static assets.
- `routers.py`, `capacity_engine.py`, `schedule_engine.py`: forecasting seed data and core engine.
- `tests/`: regression, pooling, onboarding, and golden-master coverage.

## Current Priorities

See `TASKS.md`. Active product scope is Elevator, Aeronose, and Aegis. SCOPE-01 is complete: BCA is
inactive and archived outside active ingress/navigation while its audit history remains. The
generic physical-resource shadow foundation is retained under RES-01. TOOL-01
adds deterministic occupancy leases and Aeronose tooling as the first governed tooling pilot. The
five tool counts are registered as unbound drafts, with Ryan Miller recorded as current
owner/approver and all pools Aeronose-dedicated. Controlled WIs and live IFS timing show that shell
molds, subring jigs, core-kit molds, and trim require distinct route or sub-operation boundaries.
The allocator core retains the existing cure-station rules with exact parity, but op 775 has now been
validated as dolly-based with no fixed station; that correction belongs in a successor candidate.
AVAIL-01 now provides the append-only, count-based outage lifecycle and database guards; the
critic-reviewed plan continues with authenticated authoring, compiler integration, and UI. One shell
mold is confirmed in the tool shop as a fabrication aid and is immediately usable once Ryan confirms
its return, but the live event table remains empty until identity controls pass. No tooling candidate can change
published dates until its shadow and approval gates pass.
Accuracy v1.1 is live in the portfolio and each program workspace with fixed horizons, confidence,
P80 calibration, completed terminal-operation truth, and immutable cohort provenance; immature
programs remain visibly calibrating.
The searchable in-app `/handbook` and nine-page core operating set are live. Contextual help links
and formal documentation governance remain DOC-01c/DOC-01d.
The Marion virtual factory is live for reviewed P2/P3 locations and remains visual-only. It must
not change simulation inputs without a separate approved design. Follow-ons #82-1a, #82-4, and
#82-5 cover the governed full-WC catalog refresh, reviewed physical expansion, and live acceptance.
