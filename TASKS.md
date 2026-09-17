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

- [x] **#32b - Calibrate Radome electrical-seal station count**
  - Floor ownership confirms op 775 is performed on a movable work dolly and has no fixed physical
    station. ASSY Rev K identifies only cure-puck shop aid `SA0145`; read-only IFS clocking shows up
    to four concurrent op-775 labor spans across 78 recent completed spans.
  - Delivered 2026-09-03: the one-slot rule is rejected as a physical fact and retained only in the
    frozen parity model. Evidence: `docs/validation/tool-01c-aeronose-wi-review.md`.

- [ ] **#32c - Govern the op-775 physical and accelerated-cure successors**
  - [x] **#32c1 - No-station physical correction:** epoch 11 is an `OBSERVE` successor that retains
    the 40-hour cure and removes `P3_ELECTRICAL_SEAL`. The published `RAD:LEGACY` epoch is unchanged.
    Baseline/candidate snapshots 30/31 replay exactly; six current units move, including one small
    adverse queue redistribution that remains visible rather than being hidden.
  - [ ] **#32c2 - DRDI accelerated cure:** epoch 12 contains sequential 2-hour flashoff and 8-hour
    cure gates with no fixed station, but remains `DRAFT` while DRDI approval is pending. Transition
    to `OBSERVE` requires DRDI identifier(s), authorized approver, approval timestamp, and effective
    date. Never infer approval from verbal progress or replace the 40-hour published/parity route.
  - Acceptance: both paths are immutable and replayable; accelerated dates are unavailable before
    complete DRDI evidence; no successor changes publication; final promotion still requires the
    integrated pilot. See `docs/validation/32c-aeronose-cure-successors.md`.

## Program Forecast Accuracy

- [x] **ACC-01 - Add honest per-program Accuracy v1.1 scoring**
  - [x] **ACC-01a - Eligibility and anti-leakage:** use completed IFS terminal-operation dates;
    reject same-day/post-ship forecasts; select one latest forecast per unit in fixed 7/14/21-day windows.
  - [x] **ACC-01b - Score and immutable provenance:** implement the critic-reviewed 0-100 formula,
    independent confidence tiers, separate P80 Wilson coverage, headline gating, and append-only
    daily summary rows with frozen source cohorts and hashes.
  - [x] **ACC-01c - Portfolio and program UX:** add the portfolio Accuracy signal and a responsive
    program Accuracy tab with horizon detail, exclusions, evidence contract, and score history.
  - [x] **ACC-01e - Reconcile terminal shipment truth:** require the configured Pack & Ship
    operation to be closed before accepting its latest finish clock; surface changed ship dates as
    corrections; reconcile forecast history by shop order across zero-padded serial variants.
  - [ ] **ACC-01d - Accumulate and validate forward evidence:** continue daily forecast stamping and
    physical shipment processing; do not rank programs or publish a headline until all horizons have
    at least five eligible units. Revisit weights/SLA only through a new formula version.
  - Delivered 2026-09-04 and corrected 2026-09-09: first baseline shows Aegis 7-day score 11 with
    n=1/Insufficient;
    Elevator and Aeronose have no eligible standardized horizon cohort; all headlines are withheld.
    Current maturity counts are ELEV 4, RAD 3, AEGIS 1. See
    `docs/validation/acc-01-program-accuracy.md`.

## Rate Readiness Planning

- [ ] **RATE-01 - Backsolve labor and tooling required to support a target production rate**
  - Design: `docs/plans/rate-readiness-planner.md`. Critic status: Gemini 3.1 Pro returned
    `SATISFIED` after joint-vector search, learning/retention cohorts, pre-solver calibration,
    explicit Pareto dimensions, and measurement-only sustainability were added.
  - [x] **RATE-01a - Define demand, staffing, readiness, and feasibility contracts**
    - Canonicalize monthly/annual rate, product mix, ramp, calendar, shift/overtime, reserve policy,
      explicit published-or-candidate baseline, skill pools, productive hours/FTE, learning curves,
      retention yield, and READY/PROVISIONAL/UNRESOLVED behavior.
    - Acceptance: inactive BCA and mixed contexts are rejected; missing tooling spans cannot produce
      zero-tool recommendations; missing labor denominators cannot produce headcount.
    - Delivered 2026-09-17: active-program and mixed-context gates; monthly/annual/profile demand;
      product mix; readiness/tool uncertainty; productive-hours staffing contracts; immutable
      published/candidate baseline snapshots; and effective-dated labor-pool evidence for current
      FTE, eligible WCs/shifts, learning curves, retention yield, ownership, and review dates.
      No staffing values are seeded without owner evidence. See
      `docs/validation/rate-01a-governance.md`.
  - [x] **RATE-01b - Build deterministic synthetic demand and steady-state measurement**
    - Generate scenario-only releases; combine inherited WIP, shared-program demand, and governed
      external load without double counting. Add warm-up, measurement, cool-down, censoring, and
      measurement-only throughput/backlog stability.
    - Acceptance: synthetic units never enter operational tables; analytical fixtures match; input
      order is irrelevant; cooldown backlog clearing cannot make an undersized scenario pass.
    - Delivered 2026-09-17: deterministic fractional accumulation and product mix; explicit
      production-release months; working-day calendars; future `release_at` enforcement; exact WIP
      order/quantity netting; required shared-program WIP coverage; defensive tracked-project
      exclusion; weighted external pool demand with quality/readiness; measurement-only backlog
      checks; remaining-route labor and tool-concurrency lower bounds; and bounded exhaustive rate
      search with `SEARCH_INCOMPLETE` diagnostics. See
      `docs/validation/rate-01b-demand-capacity.md`.
  - [ ] **RATE-01c - Calibrate throughput, labor productivity, and ramp evidence**
    - Backtest releases, WIP, completions, labor hours, staffing, cycle time, productive-hours/FTE,
      learning curves, and retention yield. Review Aeronose and Elevator intervals with IE/floor owners.
    - Acceptance: owner-approved error thresholds pass before solver recommendations or production UI.
  - [ ] **RATE-01d - Implement the bounded joint labor/tool package solver**
    - Search integer capacity vectors with coupled labor/tool clusters, componentwise dominance,
      hard per-pool/global bounds, result caching, and deterministic stress cases.
    - Return the FTE/tool-slot/time Pareto frontier, named anchor packages, bottleneck sequence,
      shared-capacity effects, and `SEARCH INCOMPLETE` when bounds are exhausted.
    - Acceptance: no worker is double-counted across WCs; isolated zero-gain additions cannot stop
      coupled search; every feasible package replays; unresolved resources remain unresolved.
  - [ ] **RATE-01e - Persist immutable scenario versions, runs, replay, and audit exports**
    - Freeze demand, WIP, epoch definition, transition state, resources, policies, engine version,
      diagnostics, and hashes. Saving/sharing requires identity, authorization, secure sessions,
      and CSRF; operational WIP, forecasts, plans, IFS, and published epochs remain untouched.
  - [ ] **RATE-01f - Add the Rate Planner and Saved Runs workspaces**
    - Extend Scenarios with monthly/annual inputs, demand profile, results, throughput/backlog,
      skill-pool hires with WC allocations, tooling, package comparison, readiness, audit export,
      progress/cancellation, and required-date/requisition-date risk.
    - Acceptance: provisional/unresolved results are never labeled feasible; responsive, keyboard,
      light/dark, print, WCAG A/AA, stale-input, cancellation, and performance gates pass.
  - [ ] **RATE-01g - Complete forward validation and owner acceptance**
    - Compare recommendations with owner judgment and observed rate performance; document false and
      missed constraints plus shared-capacity spillover.
    - Acceptance: approved resource-gap/time-to-rate thresholds pass. Tool recommendations remain
      gated by TOOL-01d, TOOL-02, and TOOL-03; the feature remains scenario-only.
  - Sequence: RATE-01a/b may begin from current foundations. RATE-01c must pass before RATE-01d or
    owner-facing RATE-01f. AVAIL-02 gates saved scenarios. RATE-01g follows program tooling evidence.

## Platform-Wide Resource Adoption

**Status:** Revised 2026-09-02. Active product scope is Elevator, Aeronose, and Aegis. The migration
must preserve their published forecasts while the enhanced resource model is evaluated in shadow.
BCA was parked through SCOPE-01; its completed evidence remains historical and cannot affect
active product behavior.

- [ ] **PLAT-01 - Apply resource governance and candidate epochs to existing programs**
  - Reuse the Resource and Assumption Registry for all three active programs. Capacity values,
    tooling, evidence, and readiness remain program- or physical-pool-specific.

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
      Physical-resource calibration and pilot gates remain in PLAT-01d and TOOL-01e.

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
      External actor writes remain disabled pending authenticated role binding. Live
      `CRP_ORDER_LOAD2` capture and tracked-demand exclusion are deferred until an active
      three-program resource case requires them.

  - [x] **PLAT-01c - Backfill and verify existing-program shadow coverage**
    - Confirm ELEV, RAD, and AEGIS operation bindings, readiness, owners, evidence, review dates,
      and immutable snapshot linkage. Build on the 24 legacy-equivalent pools and 162 bindings
      delivered by the Resource Registry foundation rather than reseeding a second registry.
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
      slots for Elevator/Aeronose, use contract anchoring for Aegis, and remove
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
      3.29 seconds (2.84-4.63 seconds). Out-of-scope/deferred programs remain outside delivery-risk
      denominators.
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

The active critical path is now three-program tooling, beginning with Aeronose. BCA work is removed
from the execution sequence and retained only in the deferred evidence section.

1. SCOPE-01 park BCA and prove three-program no-drift. **Complete 2026-09-02.**
2. RES-01 reframe and commit the generic physical-resource shadow foundation. **Complete
   2026-09-02.**
3. TOOL-01a create and review the governed Aeronose tooling inventory. **Counts and owner review
   recorded 2026-09-03; binding prerequisites remain open.**
4. TOOL-01b build the generic atomic occupancy allocator and migrate cure stations with exact
   legacy parity. **Complete 2026-09-02.**
5. #32b confirm the Plant 3 electrical-seal physical constraint. **Complete 2026-09-03: no fixed
   station.**
6. TOOL-01c complete the floor check, then implement component routes/substeps and approve bindings.
7. TOOL-01c1 implement governed, authenticated tooling availability controls in parallel with the
   floor follow-up; it must finish before the tooling shadow.
8. #32c1 no-station successor is complete. Finish #32c2 only after DRDI approval evidence is
   available; do not alter the parity or published epoch.
9. TOOL-01d run the Aeronose tooling shadow and expose causal explanations.
10. DOC-01a/DOC-01b add the in-app handbook shell and core user documentation. **Complete
   2026-09-02.**
11. UI-01d add the three-program resource/tooling pressure board from governed data.
12. TOOL-02 survey and model Elevator tooling in its own candidate.
13. TOOL-03 document and periodically review Aegis present-rate assumptions.
14. DOC-01c add contextual documentation links after tooling views stabilize.
15. PLAT-01d certify accepted physical/tooling candidate inputs without promoting them.
16. UI-01e and DOC-01d complete integrated UX/documentation acceptance.
17. TOOL-01e complete the 2-4 week Aeronose pilot.
18. PLAT-01e promote only explicitly accepted replacement epochs; retain rollback.

**Phase gates:**
- Gate 1 - foundation: authorized lifecycle transitions, immutable epoch snapshots, expiry/drift
  behavior, and deterministic replay are verified before non-parity shadow modeling.
- Gate 2 - baseline: the static golden suite and live refresh comparisons show exact incumbent
  legacy parity, with no production assumption silently supplied by `DEFAULT_SHIFT`.
- Gate 3 - scope isolation: BCA leaves active navigation, refresh, and portfolio reads while its
  immutable evidence remains available for audit; `Program.active` excludes it at sync ingress and
  from the WIP/simulation matrix; three-program outputs remain exact.
- Gate 4 - occupancy parity: cure stations migrate to the generic allocator without date drift,
  deadlock, or nondeterminism. Queue order is explicit; any deadlock aborts the whole run and opens
  a blocking review rather than producing partial output.
- Gate 5 - Aeronose tooling integrity: counts, calendars, instances, and acquire/release spans are
  approved; shadow waits explain material changes and agree with floor reality. Published and
  candidate UI/read-model contexts cannot be aggregated.
- Gate 6 - promotion: two consecutive reviewed weeks meet the lease-completeness, severity-1,
  sample-sufficiency, and one-shift timing-error criteria, and the named tooling/floor,
  program, and master-scheduling owners approve the candidate epoch.

Tasks #82-1a/#82-4/#82-5 may proceed in parallel because they do not change the tooling candidate
critical path. The legacy resource fallback remains until the accepted pilot and rollback-retention
gates are complete. Full rationale and acceptance details are in
`docs/plans/three-program-tooling-roadmap.md`.

RATE-01a/b may also proceed as a parallel architecture track. RATE-01c calibration must precede its
solver and production UI; definitive tool recommendations remain blocked on TOOL-01d/02/03.

## Three-Program Tooling Adoption

- [x] **SCOPE-01 - Park BCA and restore the three-program product boundary**
  - Archive the BCA finishing candidate through the lifecycle service and mark its program inactive.
  - Remove BCA from navigation, portfolio reads, sync targets, and active data collection without
    deleting its program row, epochs, snapshots, source metadata, or `BCALAY` quarantine evidence.
  - Enforce `Program.active` at registry loading, sync/data ingress, the WIP state matrix, pooled
    simulation inputs, and forecast-log stamping; UI hiding alone does not satisfy isolation.
  - Acceptance: only ELEV/RAD/AEGIS appear in active product surfaces; refresh and forecast logs do
    not touch BCA; all three published forecasts and the static golden master remain exact.
  - Restart gate: explicit product approval, current IFS rediscovery, fresh resource/tooling
    approval, a new candidate epoch, and a new shadow pilot.
  - Delivered 2026-09-02: `BCAFIN` is inactive and epoch 10 is `ARCHIVED`; active registry, sync,
    WIP, simulation, forecast routes/logging, portfolio, and navigation resolve only ELEV/RAD/AEGIS.
    All 73 BCA position rows, zero BCA forecast-log rows, and 12 `BCALAY` quarantine events were
    retained. Pre-change backup: `data/rtg_app_migrated.pre_bca_park.bak`, SHA-256
    `22ADC5E690FA00328D11A0EF241FE67345BF850DEE3BCAB55D906C38F7888FA6`.

- [x] **RES-01 - Preserve and reframe the generic resource shadow foundation**
  - Retain pool-ID allocation, finite calendars, explicit reserves, immutable candidates, replay,
    readiness, and causal comparison as platform capabilities for the three active programs.
  - Remove BCA-specific next-step framing from current handoffs while keeping historical evidence
    documents clearly labeled as deferred.
  - Acceptance: generic resource tests remain green, published outputs do not move, and no BCA
    capacity or tooling input is created.
  - Delivered 2026-09-02: pool-ID effort allocation, finite calendars, explicit static reserve,
    fail-closed DB-active compilation, immutable physical shadow epochs, exact v1/v2 replay, and
    causal baseline/candidate comparisons are platform capabilities. No BCA pool was created.

- [ ] **TOOL-01 - Add Aeronose tooling through a governed occupancy shadow**
  - Design and execution reference: `docs/plans/three-program-tooling-roadmap.md`.

  - [ ] **TOOL-01a - Register the Aeronose tooling inventory and authority**
    - Create internal-only draft pools for two assembly jigs, one holding fixture, one trim
      fixture, three shell lamination molds, one core-forming mold set, six paint dollies, and nine
      handling dollies.
    - Record fungibility/named-instance rules, owner, approver, evidence, effective date, review
      date, maintenance calendar, and changeover/cleanup assumptions.
    - Classify each pool as dedicated or physically shared and identify every known consumer. Shared
      demand is modeled honestly; it is never hidden as nonblocking or ghost demand.
    - Acceptance: counts are persisted as owner-supplied facts but cannot affect dates without
      approved operation bindings.
    - Progress through 2026-09-14: seven live draft pools carry counts `2/1/1/3/1/6/9`, owner
      attribution, internal-only status, and zero bindings. Holding fixture `3700HF0001` is a single
      wooden blue fixture. Six paint-dolly and nine handling-dolly identifiers are preserved as
      evidence, not scheduling instances. Physical spans, component links, current WIP assignments,
      dolly compatibility/serviceability, and the shell mold's actual return date remain open. See
      `docs/validation/tool-01a-aeronose-inventory.md`.

  - [x] **TOOL-01b - Implement atomic occupancy leases and prove cure-station parity**
    - Acquire all required tools atomically; support fungible slots, named instances, multi-tool
      acquisition, minimum hold, lag, cleanup/changeover, maintenance exceptions, and explicit
      release events. Reject invalid release targets and fail loudly on deadlock/no progress.
    - Queue deterministically by ready time, DPAS-behind priority, commit date, program, serial, and
      pool code. Database/input order must not decide acquisition.
    - Deadlock raises `ResourceAllocationDeadlock`, aborts the run, writes no forecast result/log,
      and opens a blocking review; partial or skipped-unit output is prohibited.
    - Migrate the current Plant 2 paint-booth and Plant 3 electrical-seal constraints through the
      same allocator before activating Aeronose tools.
    - Acceptance: deterministic results under input reordering, complete lease audit history,
      focused occupancy tests, exact cure-station behavior, and no static-golden drift.
    - Progress 2026-09-02: delivered deterministic fixed reservations, atomic multi-pool
      acquisition, named instances, minimum holds, release lag, explicit queue keys, fatal
      impossible-request/invalid-release errors, lease history, approved-binding/profile
      compilation, all four release events, replayable occupancy traces, future maintenance
      windows, initial WIP holdings, same-shift priority retry, fatal full-run no-progress handling,
      and exact cure-station/golden parity. Why rendering follows real bindings in TOOL-01d. See
      `docs/validation/tool-01b-occupancy-core.md`.

  - [ ] **TOOL-01c - Approve Aeronose acquire/release bindings**
    - [x] Review controlled LAM F, COREKIT H, ASSY K, and PAINT B work instructions; reconcile their
      routes with live IFS revision 16 top assembly, revision 5 subring, and revision 3 core kit.
    - [x] Record owner/approver, Aeronose dedication, fungibility, op-775 no-station decision, and
      read-only IFS clock-span evidence without creating bindings.
    - [ ] Complete the floor check first: top-assembly AF release; holding fixture `3700HF0001`'s
      purpose and span; paint/handling dolly spans and compatibility; Dup-1 pin setup; current WIP
      assignments; shell-mold removal and actual return dates.
    - [ ] Confirm whether normal cleaning/setup is contained in the acquiring operation before
      approving the owner-reported zero post-release lag; IFS idle gaps are not causal proof.
    - [ ] Add candidate route events for top-level ops 50/90 so shell-mold acquisition is not late.
    - [ ] Add component-stream linkage for `3700ED0001-101SUBRING` and `3700COREKIT` before their
      assembly/core tooling can constrain the top-level forecast.
    - [ ] Split op 580 at the reviewed trim-fixture release point, or add an equally explicit frozen
      substep event; op-complete release would hold the fixture during dolly chamfer and create false waits.
    - [ ] Freeze only the resulting approved bindings in an immutable Aeronose `OBSERVE` candidate.
    - Acceptance: every event exists in a frozen top or linked component route, no span is guessed,
      clocking is not treated as physical occupancy when it contradicts owner counts, and all
      overlapping/multi-tool requirements acquire atomically.
    - Evidence: `docs/validation/tool-01c-aeronose-wi-review.md`.

  - [ ] **TOOL-01c1 - Add governed tooling availability controls**
    - [x] **AVAIL-01 - Append-only event foundation:** added migration `0a1b2c3d4e5f`, generic
      availability events, lifecycle/count folding, SQLite concurrency and immutability guards,
      startup trigger verification, and permanent audit export. The live table is empty and no
      forecast behavior changed. See `docs/validation/tool-01c1-availability-foundation.md`.
    - [ ] **AVAIL-02 - Identity and write authorization:** validate application OIDC identity, bind
      server-derived roles, secure cookie sessions, and CSRF before exposing write routes.
    - [ ] **AVAIL-03 - Compiler and candidate succession:** compile pooled count reductions, detect
      as-of WIP conflicts, freeze events into snapshots/replay, and create OBSERVE successors only
      for consuming candidates.
    - [ ] **AVAIL-04 - Operational UI:** add the tooling timeline, outage/early-return/extension
      flows, stale-preview rejection, shadow impact, and permanent audit history.
    - [ ] **AVAIL-05 - Aeronose seed and sensitivity:** append the provisional shell-mold outage,
      reconstruct current shell/core holders, and run 0/2/4-hour turnaround candidates.
    - Implement the append-only, count-based availability event model and pooled capacity-reduction
      windows in `docs/plans/tooling-availability-control.md`.
    - Bind authoring to validated application identity. Ryan Miller and configured data
      administrators may edit; all other users are read-only. No write route is enabled before the
      identity, role, session-cookie, and CSRF gates pass.
    - Add Resource Registry/detail controls for outage, early return, and extension with stale-
      preview rejection, explicit candidate context, capacity-violation guidance, and permanent audit.
    - Record one provisional shell-mold outage from 2026-09-03 until owner-confirmed return. The
      mold is being used as a fabrication aid, has no work performed on it, and is immediately
      production-ready on return. Persist unavailable quantity, not absolute
      capacity; individual tool serials and PM scheduling are deferred.
    - Acceptance: event history is immutable; pooled reductions never invent a tool serial; affected
      OBSERVE candidates receive replayable successors; published forecasts remain exact; the UI
      passes responsive, keyboard, light/dark, axe, authorization, and CSRF checks.

  - [ ] **TOOL-01d - Run and explain the Aeronose tooling shadow**
    - Compare identical WIP under the published legacy epoch and tooling candidate.
    - Show occupancy windows, blocking tool, wait duration, assumption IDs, and RTG-slot impact in
      Resources, the unit Why view, and Factory Map detail without changing published dates/KPIs.
    - Require an explicit published or candidate epoch context in every read model and UI request;
      never aggregate published ELEV/AEGIS output with Aeronose candidate tooling output.
    - Acceptance: every material date change has a causal tool wait; replay is exact; floor review
      confirms or rejects the modeled waits.

  - [ ] **TOOL-01e - Complete the Aeronose shadow pilot and promotion decision**
    - Run 2-4 weeks of replayable shadow forecasts and reconcile modeled occupancy with floor use.
    - Require two consecutive reviewed weeks, zero unresolved severity-1 tool identity/span or
      missed-conflict defects, complete traces for every observed lease, and acquire/release timing
      MAE within one production shift for a sufficient sample. Extend the pilot if evidence is thin.
    - Acceptance: tooling, program, and scheduling owners approve the candidate; otherwise the
      published legacy epoch remains active with no loss of functionality.

- [ ] **TOOL-02 - Survey and model Elevator tooling**
  - Inventory assembly jigs, holding/trim fixtures, molds, dedicated gauges, and shared tools.
  - Reuse TOOL-01 governance and allocator behavior, but approve Elevator-specific spans and
    calendars independently.

- [ ] **TOOL-03 - Record Aegis present-rate tooling assessment**
  - Record the current rate-one-per-month nonbinding assessment with owner, evidence, and review
    expiry. Reassess when rate, mix, or tooling availability changes.
  - Do not encode a permanent absence of constraints from today's low rate.
  - Classify tools as dedicated or physically shared. Any shared Aegis demand consumes the same
    physical pool; low rate is not permission to suppress real contention.

## Product Documentation

- [ ] **DOC-01 - Build an in-app documentation and operating-handbook section**
  - Use `/handbook` for the user-facing route because FastAPI already owns `/docs` for OpenAPI.
  - Render version-controlled, sanitized Markdown from a dedicated user-documentation directory;
    do not create a second manually maintained source of truth in templates or the database.
  - Separate stable methodology from live status. Documentation may explain calculations and data
    contracts, but mutable WIP counts, forecasts, readiness, and source freshness must come from
    live views rather than copied prose.

  - [x] **DOC-01a - Add the handbook information architecture and application shell**
    - Add registry-driven sections, left navigation, breadcrumbs, page metadata, full-text search,
      print-friendly rendering, and direct anchors.
    - Acceptance: `/handbook` is keyboard accessible, responsive, dark/light compatible, and does
      not conflict with `/docs` or expose repository paths, credentials, tokens, or sensitive logs.
    - Delivered 2026-09-02: manifest-driven navigation, sanitized Markdown rendering, search,
      breadcrumbs, ownership/review metadata, responsive reading layout, print styles, and the
      Reference navigation entry.

  - [x] **DOC-01b - Publish the initial operational content set**
    - Cover: Getting Started; program/planning-basis behavior; forecast methodology; data sources
      and freshness; interpreting Portfolio/Schedule/Flow/Resources; assumptions and lifecycle;
      tooling and capacity semantics; administrator runbooks; glossary; release notes.
    - Clearly label measured facts, model assumptions, provisional inputs, and published outputs.
    - Acceptance: every active top-level workflow has a concise procedure and every model term used
      in the UI has one canonical definition.
    - Delivered 2026-09-02: nine initial pages cover all listed topics. See
      `docs/validation/doc-01ab-handbook.md`.

  - [ ] **DOC-01c - Add contextual help and evidence links**
    - Link relevant handbook anchors from program tabs, Resource Registry, tooling views, planning-
      basis badges, freshness states, and Why panels without cluttering repeated workflows.
    - Acceptance: links preserve current program/epoch context where relevant and never imply that
      a candidate assumption is published.

  - [ ] **DOC-01d - Add documentation governance and acceptance**
    - Define owner, reviewer, version/effective date, review cadence, stale-page indicator, broken-
      link checks, content tests, and release checklist integration.
    - Acceptance: all links and anchors pass automated checks; content passes desktop/mobile,
      keyboard, light/dark, and print review; documentation changes are required when behavior or
      terminology changes.

## Deferred BCA Evidence - Not Active Product Scope

**Decision (2026-09-02):** Project `521938` is paused indefinitely. Completed discovery,
observation, and quarantine work is retained as historical evidence, but no BCA task below is on the
active execution path. SCOPE-01 removed the observation registration from active product surfaces
and refresh behavior without deleting audit history.

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

- [ ] **BCA-03 - Persist per-program work-center capacity configuration (DEFERRED)**
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
    - Progress 2026-09-01: one-to-one seeding and exact legacy parity are complete. The physical
      scheduler now allocates once by stable pool ID across differently named WCs, supports explicit
      gross-minus-static-reserve capacity, requires finite reviewed calendars, fails closed without
      bindings, freezes OBSERVE successor epochs, replays them exactly, and produces causal unit
      diffs. See `docs/validation/bca-03b-physical-pool-shadow.md`.
    - Remaining: approve shift capacity, calendar, external reserve, ownership, and review dates for
      `P3TRI`, `TRI A`, `PRNG`, and `P3NDI`; then create the physical pools and run the first live
      shadow comparison. IFS utilization envelopes are not approved capacity.
    - Deferred by the 2026-09-02 scope decision. The generic software is retained under RES-01;
      no BCA physical pool will be created.
  - [ ] **BCA-03c - Dynamic external demand and collision monitoring**
    - Materialize `CRP_ORDER_LOAD2`, prevent tracked-demand double counting, preserve horizon/source
      quality, and validate BCA against C17 Triband as a known external shared-resource consumer
      before reserve subtraction activates.
  - [ ] **BCA-03d - General discrete occupancy and Aeronose tooling**
    - Unify cure stations and tooling under atomic slot leases. Register the confirmed Aeronose tool
      counts, then block activation until acquire/release operation spans are approved.
    - Superseded for active execution by TOOL-01; no BCA occupancy work is authorized.
  - [ ] **BCA-03e - Integrated shadow pilot and stabilization gate**
    - After platform-level expiry, drift, recertification, and replay controls exist, complete the
      2-4 week integrated BCA/incumbent shadow pilot before any candidate epoch promotion or legacy
      fallback retirement.
    - Acceptance: source coverage remains current across each forecast horizon, replay hashes hold,
      calibration and interval-coverage thresholds pass, and named owners approve all activated
      shared-resource and tooling profiles.

- [ ] **BCA-04 - Model machine time and dwell deliberately (DEFERRED)**
  - Define whether BCA machine-heavy operations are labor, constrained machine time, or 24/7 dwell or cure gates; validate against work instructions and floor practice.
  - Acceptance: the modeling decision covers at least finish-route ops `4100` (34.2 machine hours),
    `5100` (21), and `5300` (10.5), with an auditable reason for each treatment. It also reconciles
    the A/C machine-time differences at ops `3000`, `3100`, and `4000` before selecting one shared
    program model or part-specific overrides.

- [ ] **BCA-05 - Onboard BCA finishing through the controlled `OBSERVE` lifecycle (DEFERRED)**
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
    - Deferred; SCOPE-01 archives the current observation candidate and stops BCA collection.

- [x] **BCA-06 - Keep the BCA layup stream separate and clean its state**
  - Treat `3301ED0032-101` as a separate 26-op layup/autoclave program, not a second part under
    the finishing program.
  - Acceptance: reconcile the 10 orders still in `Started` after terminal op `9999`, then define
    independent `TRI L` and `ATUP` capacity and machine/dwell semantics before onboarding. Quarantine
    inconsistent layup orders from shared-autoclave conclusions until their state is reconciled.
  - Delivered 2026-09-01: live revision-3 audit found 29 open orders and 12, not 10, current source
    conflicts where op `9999` is closed but the SO remains `Started`. All 12 are persisted in the
    append-only `BCALAY` quarantine and excluded from WIP/capacity conclusions; 17 orders remain
    eligible. The corrected 26-row route has 19 production ops, 86.2 labor h, and 72.0 machine h.
    The blocked policy separates TRI L shared labor effort, ATUP operator effort (3.7 h/unit), and
    ATUP discrete 6-hour 24/7 occupancy. IFS reports both WCs as infinite capacity; ATUP serves at
    least 15 other projects. Slot count, staffing, calendars, compatibility, and external reserve
    remain unapproved, so `BCALAY` is not onboarded and `DEFAULT_SHIFT` is prohibited. See
    `docs/validation/bca-06-layup-quarantine.md`.

- [ ] **BCA-07 - Run the live onboarding smoke test (DEFERRED)**
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
  - Acceptance: mappings cover existing TwinWorks centers and can retain deferred/future centers
    such as `P3TRI`, `TRI A`, `PRNG`, and `P3NDI` without making them active programs.

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
    current IFS positions for ELEV/RAD/AEGIS. Capture page response time and confirm the one-pooled-
    simulation-per-request contract remains true.
  - Acceptance: live and snapshot modes both render without writes; the route, registry, WIP,
    budgets, and golden forecasts are unchanged by map use; any materially stale catalog facts are
    surfaced through #82-1a rather than silently accepted.
