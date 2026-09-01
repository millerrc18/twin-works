# TwinWorks Task Ledger

This is the local implementation backlog for work that is not yet represented in an external tracker.
Do not mark a task complete until its acceptance criteria are verified. The active operational handoff
remains in `AGENTS.md`.

## Immediate Priorities

- [x] **#83 - TwinWorks rebrand and repository cleanup**
  - Completed the product-name pass across the live application, OAuth identity, current docs, run
    scripts, and retained UI mockups. Added `README.md`, removed the two committed WI extraction
    scratch files, and ignored them against re-addition. RTG remains domain and compatibility terminology.

- [x] **#32a - Cure-station contention allocator**
  - Added discrete cure-station allocation to `capacity_engine` through the simulation profile.
    Two Plant 2 paint booths constrain Elevator dry-to-handle and Cor Ban cures; one conservative
    Plant 3 electrical-seal station constrains the Radome 40-hour op775 cure. Ovens remain unconstrained,
    and the parallel 24-hour topcoat tape-test does not reserve a booth.
  - Acceptance: focused cure-station tests and the full static golden suite pass after the intentional
    40-unit baseline recapture.

- [ ] **#32b - Calibrate Radome electrical-seal station count**
  - Confirm whether the Plant 3 op775 electrical-seal process has one or two usable stations, then
    update `P3_ELECTRICAL_SEAL` capacity if floor validation supersedes the current conservative value of one.
  - Acceptance: capacity count is traceable to floor ownership or process authority and no default
    station assumption remains undocumented.

## Platform-Wide Resource Adoption

**Status:** Approved 2026-08-28. The migration must preserve the current
published Elevator, Aeronose, and Aegis forecasts while the enhanced resource model is evaluated in
shadow. BCA starts without a commitment-ready epoch and therefore enters the platform in `OBSERVE`.

- [ ] **PLAT-01 - Apply resource governance and candidate epochs to existing programs**
  - Reuse the Resource and Assumption Registry for every program rather than treating BCA as a
    separate modeling path. Capacity values, tooling, evidence, and readiness remain program- or
    physical-pool-specific.

  - [x] **PLAT-01a - Define lifecycle, ownership, and epoch rules**
    - Add `DRAFT`, `OBSERVE`, `PROVISIONAL`, `COMMITMENT_READY`, `PAUSED`, and terminal
      `ARCHIVED`/`DEPRECATED` states with explicit allowed transitions.
    - Assign transition authority: TwinWorks/data administration for `DRAFT` to `OBSERVE`,
      industrial engineering/floor management for `OBSERVE` to `PROVISIONAL`, and the program
      director/master scheduler for `PROVISIONAL` to `COMMITMENT_READY`.
    - Preserve the current production model as the active commitment-ready legacy epoch for ELEV,
      RAD, and AEGIS. Every enhanced candidate epoch receives an immutable registry snapshot and
      progresses independently without silently replacing the active epoch.
    - `OBSERVE` runs hidden shadow forecasts for backtesting, tooling discovery, and shared-resource
      analysis. Its dates are excluded from leadership forecast KPIs and commitment views.
    - Proposed conservative policy for approval: `PROVISIONAL` exposes constraints, utilization,
      bottlenecks, and what-if analysis but no ship dates. Only `COMMITMENT_READY` publishes dates.
    - Acceptance: lifecycle transitions and role authority are enforced in both the service and the
      database; epoch definitions, transition/publication history, and simulation snapshots are
      append-only; candidate epochs cannot silently replace the published epoch.
    - Delivered 2026-08-28: migrations `e6a1b2c3d4e5`, `f7b2c3d4e5f6`, and clean-install
      reconciliation `a8c3d4e5f6a7`; append-only epoch,
      transition, activation, and snapshot-link records, database transition/publication guards,
      published legacy epochs for ELEV/RAD/AEGIS, runtime-registry drift detection, explicit shadow
      epoch selection, and materialized epoch definitions in schema-v2 simulation snapshots.
      Startup verifies SQLite integrity pragmas and the complete governance-trigger inventory;
      raw UPDATE/DELETE/INSERT-OR-REPLACE bypass attempts are regression-tested.
      Physical-resource calibration and pilot gates remain in PLAT-01d and BCA-03e.

  - [x] **PLAT-01b - Add shadow-integrity and recertification controls**
    - Implement assumption expiry, drift review, idempotent recertification items, immutable replay,
      and explicit source-horizon quality before any non-parity physical-pool or external-demand
      shadow result is trusted.
    - Acceptance: stale or materially drifting inputs downgrade readiness without mutating prior
      epochs; stored snapshots replay to their original hash and result; active commitment-ready
      outputs cannot read candidate-epoch state accidentally.
    - Before external actors can write governance records, bind actor/role to authenticated identity,
      validate evidence payloads with versioned schemas, and add audit export/retention policy.
    - Delivered 2026-08-31: versioned/canonical evidence payloads; migration-attestation,
      missing-review-date, missing-drift-policy, expiry, sparse-evidence, and threshold-drift review
      generation; race-safe idempotent review keys; immutable one-time resolution; approved
      successor assumptions and capacity versions; permanent audit export; and schema-v3 replay
      envelopes with frozen inputs, routes, profiles, expected results, and three SHA-256 checks.
      External-load snapshots are append-only and enforce explicit `BLOCK`,
      `HOLD_LAST_COMPLETE_WEEK`, or `TRAILING_MEAN` horizon policy before integration.
      Existing schema-v2 snapshots remain integrity-verifiable and are explicitly non-replayable.
      External actor writes remain disabled pending authenticated role binding; BCA-03c still owns
      the live `CRP_ORDER_LOAD2` capture, tracked-demand exclusion, and policy approval.

  - [x] **PLAT-01c - Backfill and verify existing-program shadow coverage**
    - Confirm ELEV, RAD, and AEGIS operation bindings, readiness, owners, evidence, review dates,
      and immutable snapshot linkage. Build on the 24 legacy-equivalent pools and 162 bindings
      delivered in BCA-03a rather than reseeding a second registry.
    - Run the candidate resource epoch in shadow and prove exact legacy parity before physical-pool,
      external-demand, or tooling constraints are activated.
    - Acceptance: current published forecasts remain unchanged, every shadow run is replayable from
      its snapshot, and missing/stale assumptions are visible rather than filled by `DEFAULT_SHIFT`.
    - Delivered 2026-08-31: immutable `OBSERVE` candidates for ELEV/RAD/AEGIS, frozen one-to-one
      mapping definitions, live-definition drift rejection, automatic archival of superseded parity
      candidates, exact 29-unit legacy/DB-shadow parity, and exact replay from snapshots. Both paths
      produced result hash `c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`.
      The review queue exposes 70 inherited governance debts: 24 missing review dates, 24 migrated-
      evidence attestations, and 22 measured-actual assumptions missing drift thresholds. These keep
      the shadow profile provisional; they do not alter the published legacy epochs.

  - [ ] **PLAT-01d - Certify existing-program physical resources in candidate epochs**
    - Apply approved shared labor pools, dynamic external demand, and occupancy resources to each
      affected existing route. Register the known Aeronose tooling first and validate its acquire/
      release spans; perform an Elevator tooling survey; record Aegis tooling as currently
      nonbinding at its present rate only with an owner, evidence, and review expiry.
    - Compare every candidate epoch with its active legacy epoch and explain all material date or
      constraint changes. Certification does not replace the active epoch and cannot alter published
      incumbent dates before the integrated pilot gate.
    - Acceptance: every required route input is commitment-ready or has an explicit, expiring reason
      to remain on legacy behavior; material shadow differences have causal constraint explanations.

  - [ ] **PLAT-01e - Promote accepted replacement epochs**
    - After the authenticated cross-program smoke test and 2-4 week integrated shadow pilot, promote
      only the candidate epochs approved by the authorized program and scheduling owners.
    - Acceptance: ELEV, RAD, and AEGIS either have governed replacement epochs or remain explicitly
      on legacy behavior; rollback remains available through one additional accepted pilot cycle.

- [ ] **UI-01 - Build the portfolio dashboard and planning-basis-aware program workspace**
  - Replace the three-program dashboard assumptions with a holistic portfolio operating view and
    consistent program drill-down. Design:
    `docs/superpowers/specs/2026-08-28-portfolio-dashboard-planning-basis-design.md`.

  - [x] **UI-01a - Add explicit planning-basis and target semantics**
    - Model `PLAN_SLOTS`, `CONTRACT_DATES`, and `NONE` independently from lifecycle. Add a derived
      `basis_effective` flag so configured intent cannot become an active comparison before the
      selected epoch is commitment-ready. Preserve RTG
      slots for Elevator/Aeronose, use contract anchoring for Aegis and initially BCA, and remove
      program-code special cases and silent RTG-to-contract fallback.
    - Acceptance: forecast DTOs expose contract, plan, comparison target, basis, and visibility as
      separate fields; ineffective bases produce no comparison target/delta, and missing plan data
      is a visible defect rather than a relabeled contract date.
    - Delivered 2026-08-31: program-level `PLAN_SLOTS`, `CONTRACT_DATES`, and `NONE`; independent
      lifecycle gating; separate forecast-log target fields; registry-derived labels; locked
      Schedule views outside commitment-ready states; and no AEGIS code special case or silent
      plan-to-contract fallback.
  - [x] **UI-01b - Replace the dashboard with a portfolio operations console**
    - Add a command strip, dense program operating table, and maturity/review ledger. Keep RTG-plan
      adherence and contract exposure separately labeled and exclude OBSERVE/PROVISIONAL programs
      from delivery KPIs. Label every aggregate denominator, show source-specific freshness, and
      defer the shared-capacity pressure board until UI-01d.
    - Acceptance: one registry-driven dashboard handles all programs without hardcoded cards or
      static KPIs and uses one pooled simulation/read-model pass per request. Keyboard/focus,
      color-independent status, epoch badges, and lifecycle suppression are part of this phase.
    - Delivered 2026-09-01: replaced the static KPI/card dashboard with a dense portfolio command
      strip, registry-driven operating table, target-specific RTG/contract denominators, published-
      baseline shared-pressure signal, maturity/review ledger, and source ledger. Each request uses
      one published-program simulation and one capacity aggregation; five live requests averaged
      3.29 seconds (2.84-4.63 seconds). BCA remains outside delivery-risk denominators.
  - [x] **UI-01c - Add adaptive program workspaces and dynamic navigation**
    - Provide Overview, Schedule, Flow, Units, Resources, Assumptions, and History drill-downs.
      PLAN_SLOTS programs retain the RTG matrix; CONTRACT_DATES programs use a contract timeline;
      OBSERVE/PROVISIONAL programs expose evidence and constraints without forecast dates.
    - Acceptance: navigation is registry-driven, URLs retain review state, and every lifecycle/
      planning-basis combination has an intentional state. Schedule remains visibly locked outside
      commitment-ready states and explains lifecycle, basis, evidence gaps, owner, and next gate.
    - Delivered 2026-09-01: added registry-driven sidebar navigation and URL-addressable Overview,
      Schedule, Flow, Units, Resources, Assumptions, and History workspaces. Published RTG/contract
      schedules retain their existing views; OBSERVE programs expose operational evidence and
      governed gaps while Schedule stays locked. Mobile navigation is off-canvas and inert while
      closed. Desktop/mobile, light/dark, keyboard interaction, and axe WCAG A/AA checks pass with
      zero violations.
  - [ ] **UI-01d - Add the cross-program shared-capacity pressure board**
    - Show physical capacity, tracked and external demand, consuming programs, oversubscription,
      readiness, and drill-through to Resources, Factory Map, and affected units.
    - Acceptance: every signal has source/provenance and cannot be confused with published program
      commitment metrics.
  - [ ] **UI-01e - Complete behavioral, visual, accessibility, and performance acceptance**
    - Test all planning-basis/lifecycle combinations, date/KPI suppression, dynamic program counts,
      light/dark themes, desktop/mobile layouts, keyboard use, and portfolio request performance.
    - Visual acceptance note (2026-08-31): the existing fixed 224px application sidebar leaves the
      Resource Registry too narrow at a 390px viewport. Replace it with the planned responsive
      navigation before closing UI-01e; desktop review-debt layouts are clean.

### Proposed Execution Order

Items 1-6 are complete. The next execution target is item 7, BCA-06 layup/autoclave cleanup.

1. PLAT-01a lifecycle, transition ownership, and immutable epoch behavior.
2. UI-01a explicit planning-basis, target, and forecast-visibility semantics.
3. PLAT-01b shadow-integrity, expiry, drift, recertification, and replay controls.
4. PLAT-01c existing-program shadow backfill and exact-parity verification.
5. BCA-05a observation-only finishing registration so data collection starts early.
6. UI-01b/UI-01c portfolio shell, dynamic navigation, and adaptive program workspaces; no shared-
   capacity pressure board until its governed data is ready.
7. BCA-06 layup/autoclave state cleanup and quarantine; it does not block finishing observation.
8. BCA-03b define approved physical labor pools across affected programs, shadow only.
9. BCA-03c ingest external demand, discover shared consumers, and prove no double counting.
10. UI-01d add the cross-program capacity pressure board using governed shared-resource data.
11. BCA-03d add generic occupancy allocation and Aeronose tooling as the first validated case.
12. BCA-04 classify BCA machine time and dwell.
13. PLAT-01d certify existing-program physical resources without promoting them.
14. BCA-05b run the integrated BCA `OBSERVE` shadow with shared-resource effects.
15. UI-01e complete integrated UX, lifecycle-suppression, accessibility, and performance acceptance.
16. BCA-07 run the authenticated live onboarding and cross-program smoke test.
17. BCA-03e complete the 2-4 week integrated shadow pilot and stabilization gate.
18. PLAT-01e promote only accepted replacement epochs; retain rollback.

**Phase gates:**
- Gate 1 - foundation: authorized lifecycle transitions, immutable epoch snapshots, expiry/drift
  behavior, and deterministic replay are verified before non-parity shadow modeling.
- Gate 2 - baseline: the static golden suite and live refresh comparisons show exact incumbent
  legacy parity, with no production assumption silently supplied by `DEFAULT_SHIFT`.
- Gate 3 - observation isolation: BCA data is collected without dates or leadership KPIs and has
  zero effect on active incumbent outputs.
- Gate 4 - shared-resource integrity: tracked-demand exclusion is mathematically tested, source
  coverage spans the forecast horizon, and BCA/C17 load reconciles before reserve subtraction.
- Gate 5 - integrated shadow: physical labor, occupancy, machine/dwell, and tooling constraints have
  no deadlocks, explain material changes, and pass point-error and interval-coverage thresholds.
- Gate 6 - promotion: the live smoke test and 2-4 week pilot are stable and the named IE/floor,
  program, and master-scheduling owners approve the candidate epoch.

Tasks #32b and #82-1a/#82-4/#82-5 may proceed in parallel because they do not change the lifecycle
or candidate-epoch critical path. The legacy resource fallback remains until the accepted pilot and
rollback-retention gates are complete.

## BCA Triband Radomes - Onboarding Readiness

**Decision:** Project `521938` may be registered early for observation-only data collection after
the platform isolation controls pass. Do not publish BCA dates or leadership KPIs until the later
promotion gates are complete. The first candidate is the BCA finishing family, not the layup family.

- [x] **BCA-01 - Make routing discovery revision-aware**
  - Update the IFS discovery path to choose an explicit routing revision, defaulting to the active
    revision used by the selected shop orders rather than returning every master-data revision.
  - Acceptance: `3301ED0031-101A` under project `521938` resolves to exactly 32 revision-3
    operations, not the 128 rows returned across revisions 1-4.
  - Delivered 2026-08-27: discovery reads active shop-order revision usage, defaults to the unique
    dominant revision, requires selection on ties, and exposes all master revisions. Live IFS
    resolved revision 3 / alternative `*` for 71 active A orders and 7 active C orders.

- [x] **BCA-02 - Preserve discovered operation economics**
  - Carry `LABOR_SETUP_TIME + LABOR_RUN_FACTOR`, `MACH_RUN_FACTOR`, crew size, operation status,
    and administrative/NOWB classification from IFS discovery into the onboarding draft.
  - Acceptance: the BCA finish draft reflects the live revision-3 economics before any approved
    modeling adjustments. `101A` = 69.603 labor / 104.303 machine hours; `101C` = 69.603 labor /
    104.603 machine hours. Administrative ops `1, 2, 6, 7, 8, 9`, terminal `9999`, and waiting
    queues are explicitly excluded or classified rather than treated as production labor.
  - Delivered 2026-08-27: the draft retains setup/run labor, setup/run machine time, crew, run-time
    code, parallel flag, reference-order status, NOWB flag, classification, and inclusion state.
    The A/C machine delta is at ops 3000, 3100, and 4000; labor, WC, crew, and exclusions match.

- [ ] **BCA-03 - Persist per-program work-center capacity configuration**
  - Expand this into the Resource and Assumption Registry: physical shared pools, effective-dated
    capacity, dynamic external demand, occupancy tooling, immutable forecast snapshots, and visible
    assumption provenance.
  - Design: `docs/superpowers/specs/2026-08-27-resource-assumption-registry-design.md`.
  - Plan: `docs/superpowers/plans/2026-08-27-resource-assumption-registry-plan.md`.
  - Acceptance: onboarding blocks non-administrative unknown WCs until a validated capacity profile
    is supplied. It must not accept `DEFAULT_SHIFT` as a production forecast assumption.
  - BCA finish capacities requiring validated floor input: `P3TRI`, `TRI A`, `PRNG`, and `P3NDI`.
    Existing profile coverage includes `236`, `P3 QA`, `3FINL`, `235`, and `INSP`.
  - Evidence pass completed 2026-08-27: all four are site-shared, IFS-configured as infinite
    capacity, and unsuitable for automatic budgets from clocking. Use a physical-pool model with
    explicit external reserve/effective capacity. See `docs/plans/bca-03-capacity-evidence.md`.

  - [x] **BCA-03a - Resource/assumption foundation and early explainability**
    - Add immutable assumptions, effective-dated physical resources, simulation snapshots,
      readiness badges, Resource Registry, and forecast Why views without changing forecast dates.
    - Delivered 2026-08-27: additive schema/migration, immutable registry service, 24 seeded
      legacy-equivalent pools, deterministic snapshot hashes, Resource Registry, readiness badges,
      and unit Why panels. Legacy allocation remains authoritative and golden-identical.
  - [ ] **BCA-03b - Legacy parity and physical labor-pool activation**
    - Seed one-to-one legacy pools, prove exact parity, then collapse approved shared pools through
      an explainable diff gate. Eliminate `DEFAULT_SHIFT` in DB-active mode.
    - Progress: one-to-one seeding and exact legacy parity are complete. Physical shared-pool
      activation remains gated on owner-approved capacity assumptions.
  - [ ] **BCA-03c - Dynamic external demand and collision monitoring**
    - Materialize `CRP_ORDER_LOAD2`, prevent tracked-demand double counting, preserve horizon/source
      quality, and validate BCA against C17 Triband as a known external shared-resource consumer
      before reserve subtraction activates.
  - [ ] **BCA-03d - General discrete occupancy and Aeronose tooling**
    - Unify cure stations and tooling under atomic slot leases. Register the confirmed Aeronose tool
      counts, then block activation until acquire/release operation spans are approved.
  - [ ] **BCA-03e - Integrated shadow pilot and stabilization gate**
    - After platform-level expiry, drift, recertification, and replay controls exist, complete the
      2-4 week integrated BCA/incumbent shadow pilot before any candidate epoch promotion or legacy
      fallback retirement.
    - Acceptance: source coverage remains current across each forecast horizon, replay hashes hold,
      calibration and interval-coverage thresholds pass, and named owners approve all activated
      shared-resource and tooling profiles.

- [ ] **BCA-04 - Model machine time and dwell deliberately**
  - Define whether BCA machine-heavy operations are labor, constrained machine time, or 24/7 dwell or cure gates; validate against work instructions and floor practice.
  - Acceptance: the modeling decision covers at least finish-route ops `4100` (34.2 machine hours),
    `5100` (21), and `5300` (10.5), with an auditable reason for each treatment. It also reconciles
    the A/C machine-time differences at ops `3000`, `3100`, and `4000` before selecting one shared
    program model or part-specific overrides.

- [ ] **BCA-05 - Onboard BCA finishing through the controlled `OBSERVE` lifecycle**
  - Candidate identity: project `521938`, site `59` / Plant 3, parts
    `3301ED0031-101A` and `3301ED0031-101C`, active routing revision `3`, pack op `7000`, terminal
    op `9999`.
  - Rationale: the A/C routes are equivalent in labor, work center, crew, and default exclusions.
    C has 0.300 additional machine hours across ops 3000/3100/4000, plus the non-material op-2
    description difference; BCA-04 must decide whether that machine delta affects scheduling.
  - [x] **BCA-05a - Register observation-only data collection**
    - After PLAT-01a through PLAT-01c pass, register the finishing identity and collect routing,
      WIP, actuals, shared-WC demand, and tooling discoveries. Unknown capacity or tooling remains
      visibly unresolved; it is never filled with `DEFAULT_SHIFT`.
    - Acceptance: live sync resolves serials from `NOTE_TEXT`, records physical pack at op `7000`,
      and supplies the maturity/shared-capacity ledger without publishing BCA dates, entering
      leadership KPIs, or changing active ELEV/RAD/AEGIS outputs.
    - Delivered 2026-08-31 through TwinWorks' authenticated IFS session: registered `BCAFIN` with
      73 live WIP orders and zero unresolved serials. Live revision-3 evidence was frozen in epoch
      `BCAFIN:CANDIDATE:ad7afe75ea9f`: 67 active A orders and 6 active C orders, 32 routing rows/
      25 included operations each, identical 69.603-hour labor routes, and 104.303/104.603 machine
      hours. The candidate is `OBSERVE`, contract intent is not effective, Schedule is locked,
      forecast-log rows remain zero, and ELEV/RAD/AEGIS remain on their published legacy epochs.
      Eight work-center binding gaps are explicitly `INCOMPLETE` (`P3TRI`, `TRI A`, `P3 QA`,
      `236`, `PRNG`, `P3NDI`, `3FINL`, `235`); no fallback capacity was activated.
  - [ ] **BCA-05b - Enable the integrated OBSERVE shadow forecast**
    - After BCA-03b through BCA-04 pass, run hidden BCA forecasts against approved physical pools,
      deduplicated external demand, and validated machine/dwell and occupancy semantics. Include BCA
      demand in incumbent candidate-epoch shadow forecasts only.
    - Acceptance: current WIP forecasts without fallback capacity, every result carries an immutable
      epoch snapshot and readiness explanation, and no result reaches a commitment or KPI view.

- [ ] **BCA-06 - Keep the BCA layup stream separate and clean its state**
  - Treat `3301ED0032-101` as a separate 26-op layup/autoclave program, not a second part under
    the finishing program.
  - Acceptance: reconcile the 10 orders still in `Started` after terminal op `9999`, then define
    independent `TRI L` and `ATUP` capacity and machine/dwell semantics before onboarding. Quarantine
    inconsistent layup orders from shared-autoclave conclusions until their state is reconciled.

- [ ] **BCA-07 - Run the live onboarding smoke test**
  - With an authenticated Connect IFS session, discover the selected pilot part, review the revision,
    capacity profile, and unknown-WC gate, save it, then verify the dashboard, matrix, sync, and
    forecast-log flows. Verify active incumbent outputs and candidate-epoch shadows separately.
  - Acceptance: no manually edited database rows, no default capacity assumptions, and no regression
    in ELEV/RAD/AEGIS forecasts.

## #82 - Marion Virtual Factory Capacity Map

**Decision:** Build a spatial view of capacity and work centers as a decision-support layer. It is
visual only and must not become a scheduler input without an explicit future design decision.

**Implementation plan:** `docs/plans/82-marion-virtual-factory-capacity-map.md`

- [x] **#82-1 - Define the floor-map data model**
  - Create a versioned mapping from work center to plant, floor zone, coordinate, display label,
    and optional shared-resource group.
  - Acceptance: mappings cover existing TwinWorks centers and can add BCA centers such as `P3TRI`,
    `TRI A`, `236`, `P3 QA`, `PRNG`, `P3NDI`, `3FINL`, and `235` without code changes.

- [ ] **#82-1a - Complete the governed IFS work-center catalog refresh**
  - Add a repeatable read-only `WORK_CENTER_CFV` refresh for Marion site `59`. Use the
    authoritative `P1`, `P2`, or `P3` description prefix, department, and production line to
    update the catalog while preserving the separately reviewed coordinate overlay.
  - Acceptance: the map imports all active P1/P2/P3 work centers and correctly classifies the
    current TwinWorks centers, including P2 `221`, `32684`, `42676`, `244`, `32678`, `32687`, and
    P3 `236`, `235`, `P3 QA`, `P3TRI`, `TRI A`, `AEROL`, `AEROA`, `ATUP`, `238`, `P3NDI`, and `PRNG`.
    Each refresh reports added, changed, inactive, and unclassified WCs for review; it never
    overwrites fixed/mobile/unplaced decisions or coordinates.
  - Constraint: `CALENDAR_ID` is not a building key. IFS does not provide floor, room, or X/Y
    coordinates, so zone placement must remain a reviewed overlay against the Marion floor plan.
- [x] **#82-2 - Expose capacity and WIP telemetry for the map**
  - Provide per-WC load, active-unit count, queued work, and late/at-risk signals using the existing
    forecast and bottleneck services.
  - Acceptance: every map signal has a traceable data source and clearly distinguishes measured data
    from modeled capacity.

- [x] **#82-3 - Add the interactive factory visualization**
  - Add a Marion floor-plan view with clickable work centers, capacity state, current WIP, and
    drill-through to the affected units and levers.
  - Acceptance: the view renders in light and dark themes, supports the active program filter, and
    does not alter the simulation or program configuration.
  - Delivered 2026-08-26: `GET /factory-map` renders VAMA02/VAMA03 Floor 01 as interactive
    canvases with model-backed work-center state, an HTMX inspector, mobile/unplaced-resource
    handling, and drill-through to forecasts and levers. See
    `docs/plans/82-marion-virtual-factory-capacity-map.md`.

- [ ] **#82-4 - Complete deferred physical coverage from reviewed annotations**
  - Add a fixed `PRNG` / P3 RANGE placement after Ryan supplies its annotation. Add VAMA01 and
    Plant 4 floors only after their source drawings and WC locations are reviewed.
  - Acceptance: every new marker records floor, normalized coordinate, label, status, and
    annotation source. `P3 QA` remains mobile, and no unknown location is inferred from IFS text.

- [ ] **#82-5 - Run the authenticated live-map acceptance check**
  - With a real Connect IFS session, compare the map's active/queued units and WC risk signals to
    current IFS positions, including BCA after onboarding. Capture page response time and confirm
    the one-pooled-simulation-per-request contract remains true as programs are added.
  - Acceptance: live and snapshot modes both render without writes; the route, registry, WIP,
    budgets, and golden forecasts are unchanged by map use; any materially stale catalog facts are
    surfaced through #82-1a rather than silently accepted.
