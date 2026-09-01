# TwinWorks Portfolio Dashboard and Planning-Basis Design

**Status:** Approved 2026-08-28; UI-01a delivered 2026-08-31; UI-01b/UI-01c delivered 2026-09-01;
UI-01d/UI-01e remain

## Purpose

TwinWorks is moving from three known programs to a portfolio that includes programs at different
levels of model maturity and with different governing delivery targets. The application needs a
portfolio-level operating picture with clear drill-down while preserving the program-specific views
needed by program managers, industrial engineering, and floor leadership.

The UI must not imply that every program has an RTG plan or that every lifecycle state is allowed to
publish forecast dates.

## Core Decision: Separate Planning Basis from Lifecycle

These are independent concepts:

- **Planning basis** identifies the authoritative target against which a commitment-ready forecast is
  compared.
- **Lifecycle** identifies whether TwinWorks has enough governed evidence to publish forecasts and
  performance metrics for the program.

### Planning basis

Add an explicit program-level `configured_planning_basis`:

- `PLAN_SLOTS`: externally governed fixed delivery slots with assignable units. The program also
  carries a `plan_label`, such as `RTG`, and source/version metadata.
- `CONTRACT_DATES`: each unit is anchored to its IFS contractual or required delivery date. There is
  no slot reassignment workflow.
- `NONE`: no approved target source. The program can still collect WIP and resource-demand evidence.

Initial mapping:

| Program | Planning basis | User-facing comparison |
|---|---|---|
| G500 Elevator | `PLAN_SLOTS` | Forecast versus RTG slot; contract remains visible as reference |
| Aeronose Radome | `PLAN_SLOTS` | Forecast versus RTG slot; contract remains visible as reference |
| Aegis Reflector | `CONTRACT_DATES` | Forecast versus IFS contract date |
| BCA Triband | `CONTRACT_DATES` configured, not yet effective | Contract remains reference data; no comparison or forecast dates until commitment-ready |

Do not infer planning basis from program code or from whether a target file happens to contain a
serial. The existing `rtg_source` becomes source metadata for `PLAN_SLOTS`, not the discriminator.
`plan_label` is registry data, not an enum, so future customer or internal plan names require no UI
code changes.

Add a derived `basis_effective` flag. It is true only when the selected epoch is
`COMMITMENT_READY` and the configured planning basis is not `NONE`. BCA may therefore retain its
contract-date intent during OBSERVE without being presented as measured against contract.

### Lifecycle visibility

- `DRAFT`: configuration workspace only.
- `OBSERVE`: show WIP, flow, actuals, shared-resource demand, data quality, and missing assumptions.
  Run hidden forecasts, but publish no forecast dates, late counts, or delivery KPIs.
- `PROVISIONAL`: show constraints, utilization, bottlenecks, sensitivity, and what-if results. Under
  the proposed conservative policy, publish no forecast dates.
- `COMMITMENT_READY`: publish P50/P80 dates and deltas against the configured planning basis.
- `PAUSED`: retain history and explain why active publication stopped.
- `ARCHIVED`/`DEPRECATED`: historical access only.

The same program can retain an active commitment-ready legacy epoch while a replacement candidate
epoch progresses through shadow lifecycle states.

## Forecast Data Contract

Stop overloading `UnitForecast.commit` with whichever target won the fallback chain. Expose:

- `contract_date`
- `plan_target_date`
- `comparison_target_date`
- `planning_basis`
- `plan_label`
- `basis_effective`
- `forecast_visibility`
- `p50_date` and `p80_date`, nullable and suppressed outside commitment-ready presentation paths
- `delta_to_target`, nullable and labeled with its basis

Target resolution is explicit:

1. If `basis_effective` is false, `comparison_target_date` and `delta_to_target` are null even when
   contract reference data exists.
2. Effective `PLAN_SLOTS` uses the assigned fixed plan slot.
3. Effective `CONTRACT_DATES` uses the unit's IFS contract date.
4. `NONE` has no comparison target.

Missing plan-slot data is a visible coverage defect. It must not silently fall back to contract and
continue to display an RTG label.

## Information Architecture

### Portfolio dashboard

The application home becomes a compact operations console rather than a grid of independent program
cards.

1. **Portfolio command strip**
   - total active WIP;
   - RTG-plan units at risk and their denominator;
   - contract-anchored units at risk and their denominator;
   - shared resources over or near capacity;
   - stale assumptions or data feeds requiring review;
   - latest successful IFS refresh.

2. **Program operating table**
   - program and lifecycle;
   - configured planning basis (`RTG plan`, `Contract`, or `No approved target`) plus an explicit
     `not yet in force` state when `basis_effective` is false;
   - WIP and stalled counts;
   - governing-target risk only when commitment-ready, with its basis pill adjacent to the value;
   - binding resource and readiness;
   - data freshness and direct drill-down.

3. **Shared-capacity pressure board**
   - physical resource pool;
   - tracked demand, external demand, and schedulable capacity;
   - gross utilization and net/schedulable utilization shown separately;
   - consuming programs;
   - utilization/oversubscription and assumption readiness;
   - links to Resource Registry and Factory Map.

4. **Maturity and review ledger**
   - OBSERVE/PROVISIONAL programs;
   - missing evidence and open reviews;
   - current gate, owner, and next required decision;
   - never mixed into commitment-ready delivery KPIs.

RTG adherence and contract exposure remain separate labeled measures. The portfolio must not combine
them into an unlabeled on-time percentage. Every aggregate states its included-program denominator,
for example `2 of 4 programs commitment-ready`.

Staleness is evaluated against source-specific policy, not one global timer. Position/WIP, external
load, plan sources, and governed assumptions each carry a configured maximum age or `review_due_at`.
Every source class must have an approved SLA before it can support a commitment-ready epoch. Plan
coverage defects and stale inputs appear both in the command strip and on the affected program row.

### Program workspace

Each program drill-down uses the same shell with contextual tabs:

- `Overview`: lifecycle, planning basis, WIP, current risks, constraint summary, and freshness.
- `Schedule`: RTG slot matrix for effective `PLAN_SLOTS`; contract-anchored unit timeline for
  effective `CONTRACT_DATES`. Outside commitment-ready states it remains visible as a locked,
  keyboard-focusable destination that opens a readiness explanation rather than displaying targets
  or forecasts. The explanation names the lifecycle, configured basis, blocking evidence gaps,
  responsible owner/next gate, and a link to Assumptions.
- `Flow`: operation-position and queue view, available in OBSERVE.
- `Units`: searchable unit/SO list with state and evidence.
- `Resources`: route-specific resource demand, tooling occupancy, and shared consumers.
- `Assumptions`: readiness, owner, evidence, expiry, and history.
- `History`: immutable forecast/model epochs and comparison to the active epoch.

Only relevant tabs are emphasized. Suppressed forecast views explain the missing maturity gate without
showing placeholder dates.

Every published forecast carries its epoch ID. When an active legacy epoch and candidate epoch both
exist, the workspace clearly identifies which one is published and provides a controlled comparison
path without blending their metrics.

### Navigation

- Generate program navigation dynamically from the registry; remove hardcoded ELEV/RAD/AEGIS links.
- Group programs by lifecycle or provide a compact program switcher when the list grows.
- Keep portfolio, shared resources, factory map, scenarios, and administration as stable global
  destinations.
- Preserve URL-addressable filters and selected units for review reproducibility.

## Visual Direction

Keep the existing calm-canvas/loud-signal system, but make the portfolio denser and more operational:

- use one primary operating table instead of a wall of cards;
- use narrow status rails, basis badges, compact utilization bars, and small trend marks;
- reserve alert colors for actionable exceptions;
- use consistent icons and labels for plan slots, contract dates, lifecycle, resources, and data age;
- use the Factory Map as a linked spatial drill-down, not the dashboard background;
- preserve light/dark themes and test desktop and mobile layouts for text collisions.

## Delivery Phases

1. **UI-01a - Planning-basis contract**
   - Add explicit planning basis/source metadata and refactor forecast DTOs and target resolution.
   - Remove the AEGIS program-code special case and silent plan-to-contract fallback.

2. **UI-01b - Portfolio read model and dashboard**
   - Build one portfolio query/read model so the route performs one pooled simulation and one
     resource aggregation per request.
   - Replace static KPIs and program cards with the command strip, operating table, and maturity
     ledger. This phase intentionally excludes the shared-capacity pressure board until governed
     physical-pool and external-demand data exist.
   - Include keyboard/focus, color-independent status, denominator labeling, epoch badging, and
     lifecycle-suppression behavior in this phase's acceptance contract.

3. **UI-01c - Adaptive program workspace**
   - Add program overview and contextual tabs.
   - Preserve the existing RTG slot matrix for plan-slot programs.
   - Provide contract and OBSERVE-safe flow/unit presentations without misleading RTG labels.
   - Keep Schedule visible but locked outside commitment-ready states, with the structured readiness
     explanation defined above.

4. **UI-01d - Shared-capacity drill-down**
   - Add the pressure board after physical pools and external demand are available.
   - Connect resource rows to Registry, Factory Map, affected programs, and unit explanations.

5. **UI-01e - Acceptance and rollout**
   - Add route/template tests for every planning-basis and lifecycle combination.
   - Verify no dates or delivery KPIs leak from OBSERVE or PROVISIONAL programs.
   - Re-run desktop/mobile and light/dark visual checks, keyboard navigation, and performance checks
     as integrated regression rather than deferring accessibility until this phase.

## Acceptance Criteria

- Every program visibly identifies its planning basis and lifecycle.
- A configured basis that is not yet effective cannot produce a comparison target or delta.
- RTG programs retain slot assignment and RTG delta behavior.
- Contract programs are serial/order anchored and never labeled as RTG.
- OBSERVE and PROVISIONAL programs expose operational evidence without forecast dates or late KPIs.
- Portfolio metrics never combine RTG adherence and contract exposure without explicit separation.
- The dashboard supports adding another program without template or navigation code changes.
- Shared-resource pressure drills down to assumptions, capacity, consumers, and affected units.
- Every published forecast identifies its epoch, and every freshness indicator uses a defined
  source-specific SLA.
- Existing ELEV/RAD/AEGIS forecast calculations remain unchanged until their candidate epochs are
  promoted through the governed resource pilot.
