# Rate Readiness Planner

## Status

Approved for backlog execution 2026-09-14 after a two-pass Gemini 3.1 Pro critique. This plan adds
a governed, scenario-only rate planner to TwinWorks. It does not change published forecasts, active
model epochs, resource assumptions, or IFS.

Implementation progress through 2026-09-17: RATE-01a and RATE-01b are complete. RATE-01c1 now
provides the historical IFS extraction and labor/throughput diagnostic, but both programs fail the
initial unapproved diagnostic bands. RATE-01c remains open for owner/IE threshold review,
historical-route/WC reconciliation, and governed staffing/ramp evidence. RATE-01d and owner-facing
RATE-01f remain blocked. See `docs/validation/rate-01c-labor-calibration.md`.

## Product Decision

Add a **Rate Readiness Planner** under the existing Scenarios workspace. A user can enter a monthly
or annual production rate, product mix, ramp timing, and operating policy. TwinWorks will calculate:

- the highest sustainable rate under the selected baseline;
- labor-hour and headcount gaps by shared skill pool, allocated visibly to work centers;
- additional tooling slots required by physical pool;
- the first period each addition is needed;
- the sequence of bottlenecks exposed after each addition;
- feasible resource packages, assumptions, readiness, and unresolved blockers.

The feature is a capacity-planning aid, not an automatic hiring or procurement authorization.

## Scope and Boundaries

Initial active scope is Elevator, Aeronose, and Aegis. BCA remains inactive and cannot enter demand,
capacity, recommendations, navigation, or saved rate scenarios without its explicit restart gate.

The planner runs against one explicit immutable baseline context:

- `PUBLISHED`: the currently published epoch and governed active-resource data; or
- `CANDIDATE:<epoch_key>`: one selected OBSERVE/PROVISIONAL candidate.

Published and candidate inputs cannot be blended. Scenario output is always labeled `WHAT-IF` and
cannot update an epoch, capacity version, staffing assumption, availability event, plan slot, or
forecast log.

The first release sizes physical labor and discrete tooling. It does not estimate recruiting or
procurement cost unless governed cost inputs are later supplied, does not create purchase requests,
and does not claim that unmodeled tooling is nonbinding.

## User Inputs

### Demand

- one or more active programs;
- monthly units, or annual units with an explicit monthly-shape policy;
- product mix within each program, including Elevator hand or other route-distinct variants;
- start date and planning horizon;
- level load, entered monthly profile, or linear/stepped ramp;
- optional planned backlog at the start of the scenario.

Annual rate defaults to an explicitly displayed level-loaded monthly profile. Fractional monthly
demand is accumulated deterministically; it is never rounded independently each month. A user must
review the generated release calendar before running the scenario.

### Operating Policy

- working calendar and planned shutdowns;
- allowed shifts and overtime policy;
- maximum planned utilization or reserve target by resource class;
- minimum-viable or resilient posture;
- optional hiring/procurement lead times and cost weights;
- governed new-hire learning curves by skill pool and hire cohort;
- scenario baseline (`PUBLISHED` or one candidate epoch).

No global default may silently turn missing calendars, productivity, skill mappings, tool spans, or
external demand into zero constraint.

## Demand Construction

Create deterministic synthetic orders from governed route templates. Synthetic demand carries a
scenario-only ID and never enters `position_state`, `forecast_log`, plan slots, or IFS-derived WIP.

The planner combines:

1. live WIP at the scenario cutover;
2. synthetic releases after the cutover;
3. demand from other tracked programs sharing the same physical pools;
4. approved external-load policy for untracked consumers.

Shared pools retain their real governed dispatch rule. Capacity added because of one program is not
silently reserved for that program unless an approved allocation policy says so. Other programs may
consume the increment, and the solver must re-evaluate the entire portfolio demand set. Results show
capacity consumption and delivery effects by program so shared-capacity bleed is visible rather
than hidden behind the target program's recommendation.

A demand-netting contract prevents double counting. Open WIP is the inherited backlog; synthetic
releases represent only demand after the cutover. Any customer-demand import must identify rows
already represented by tracked WIP before it can be added.

The simulation includes a warm-up and measurement window plus a cool-down tail. Sustainable rate
is judged only on uncensored measurement-period releases. Throughput, backlog slope, service level,
and utilization are calculated strictly from the start of measurement through the instant before
cool-down begins. Cool-down exists only to diagnose measurement-period WIP completion and horizon
censoring; falling backlog after demand stops can never satisfy the sustainability gate. A scenario
fails if measurement-period backlog grows beyond tolerance, target completions are missed, or
measurement-period work remains horizon-censored.

## Readiness Contract

Each route/resource receives one of these states:

- `READY`: approved/current route, binding, calendar, capacity, and shared-demand evidence;
- `PROVISIONAL`: internal-only or expiring evidence suitable for sensitivity analysis;
- `UNRESOLVED`: a required identity, span, calendar, skill mapping, or demand source is missing.

The scenario's overall readiness is the weakest material input. Confidence is evidence readiness,
not a statistical probability.

Rules:

- `READY` resources may produce quantified hiring/procurement recommendations.
- `PROVISIONAL` resources may produce ranges and sensitivity results, labeled provisional.
- `UNRESOLVED` tooling yields `tool requirement unresolved`; it never yields zero tools required.
- Missing productive-hours-per-person or learning-curve data yields an hours/steady-state gap and
  `ramp headcount unresolved`, not a ramp headcount claim.
- A scenario with unresolved material resources cannot be called feasible or resilient.

This allows labor-only foundations to proceed now while Aeronose, Elevator, and Aegis tooling mature
through TOOL-01/02/03.

## Labor and Headcount Model

Headcount is derived from governed **physical skill pools**, not independently summed work-center
rows. A cross-trained employee appears once in the hiring total even when allocated across several
WCs.

For each skill pool and time bucket:

```text
net productive hours per FTE
  = scheduled paid hours
  * attendance factor
  * direct-labor availability factor
  * approved shift/calendar factor

capacity FTE lower bound
  = required pool hours / net productive hours per FTE
```

Added hires are modeled as dated cohorts. Each cohort receives a governed, skill-pool-specific
efficiency curve such as training/nonproductive time by month since hire. The curve modifies the
cohort's productive-hour supply; it does not reduce operation demand. Existing/tenured staffing and
new-hire cohorts are kept separate so the ramp cannot assume every added person is fully productive
on day one. Each cohort also carries a governed retention/training-completion yield; a 10-person hire
cohort cannot silently become 10 fully productive employees when expected attrition or washout is
material. If either curve is provisional, TwinWorks shows a governed sensitivity range. If learning
or retention evidence is missing, only steady-state staffing may be quantified.

The simulation then validates the integer staffing pattern by shift. Outputs show:

- added heads by skill pool and shift;
- allocated hours/FTE by WC;
- overtime hours if permitted;
- peak and sustained utilization;
- the governed productive-hours and cross-training assumptions;
- first-need month and lead-time status.

`crew_by_op` affects operation execution but is not itself headcount. Support labor, touch labor, and
machine-attendance rules remain separate. Where an employee can cover only specified WCs or shifts,
the skill matrix must enforce that restriction.

## Tooling Model

For every approved occupancy pool, calculate an analytical lower bound from peak concurrent leases,
then validate discrete slot additions in the finite-capacity simulation. Tool recommendations show:

- baseline physical count and effective available count;
- peak concurrent need and utilization;
- required additional pooled slots;
- impacted operations and units;
- first-need month;
- outage/maintenance sensitivity;
- procurement lead-time status;
- evidence owner, binding revision, and readiness.

Count-only inventories remain pooled. Named instances are used only where compatibility or
maintenance evidence requires them. A listed asset is not assumed serviceable or interchangeable
without evidence.

## Joint Resource Solver

Labor and tooling must be solved together because relieving one constraint exposes another.

1. Run the selected baseline with inherited WIP and scenario demand.
2. Calculate labor-hour and tooling-concurrency lower bounds.
3. Form a bounded candidate set around the lower-bound resource vector and every observed blocking
   resource, including coupled labor/tool clusters at the same or downstream operations.
4. Evaluate integer **joint capacity vectors**, not only one-resource-at-a-time increments. Use
   deterministic branch-and-bound or equivalent bounded enumeration with dominance pruning,
   content-addressed result caching, and explicit search bounds.
5. Re-run the full deterministic simulation for every retained vector. Zero marginal gain from one
   isolated addition does not terminate search when a coupled vector remains unexplored.
6. Stop only when the demand/service target passes, the bounded search space is exhausted, or a
   governed runtime/node limit is reached. A bounded-out result is `SEARCH INCOMPLETE`, not infeasible.
7. Record coupled bottleneck clusters, the constraint sequence within each evaluated run, and the
   marginal rate gain of complete resource packages.

Without governed cost or preference weights, TwinWorks must not collapse unlike resources into a
dimensionally meaningless single score. The default frontier minimizes three explicit objectives:

1. distinct added FTE across physical skill pools;
2. added pooled tool slots, with dominance also checked componentwise by tool pool so one mold and
   one dolly are never treated as interchangeable merely because both count as one slot;
3. time to the first stable measurement period at the requested rate.

The UI labels FTE and total tool slots as coarse comparison axes and always shows the pool-level
vector. It presents a bounded set of non-dominated packages plus named anchors (fewest hires, fewest
tool additions, earliest stable rate), not an unfiltered list. When approved labor and tooling costs
exist, a separate cost-aware frontier minimizes total governed investment and time-to-rate while
retaining the resource-vector view.

Two postures are reported:

- **Minimum viable:** passes the demand target under the selected base calendar and utilization cap.
- **Resilient:** also passes governed stress cases such as planned absence, one approved tool outage,
  demand mix change, or the selected reserve policy.

The initial resilience model uses deterministic, named stress cases. Monte Carlo claims are out of
scope until calibrated variability distributions exist.

## Feasibility and Output Contract

A rate is sustainable only when all of the following pass:

- measurement-period completion rate meets demand;
- ending backlog is not growing beyond the defined tolerance;
- no unit is silently dropped, skipped, or horizon-censored;
- utilization stays within the selected policy;
- every material resource is `READY`, or the result is explicitly provisional/unresolved;
- shared and external demand are included under their approved policies.

Primary output:

| Resource | Current | Effective | Required | Addition | Need by | Readiness |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Skill pool / WC allocation | | | | | | |
| Tool pool | | | | | | |

The work surface also shows:

- requested versus sustainable monthly rate;
- baseline and scenario throughput/backlog curves;
- bottleneck sequence;
- resource-package comparison;
- marginal units/month gained by each addition;
- assumptions, exclusions, unresolved resources, and source freshness;
- exact baseline epoch and scenario-run ID;
- shared-pool capacity consumption and service effects by program;
- downloadable audit JSON/CSV.

The UI separates **Capacity Required Date** (first modeled shortage period) from **Requisition
Date** (required date minus governed lead time). If lead time is absent, Requisition Date reads
`UNRESOLVED - MISSING LEAD TIME`; TwinWorks never invents a procurement date. A calculated
requisition date before the scenario run date is labeled `PAST DUE - EXECUTION RISK` and reports the
minimum modeled lateness rather than presenting a historical date as actionable.

## Persistence and Reproducibility

Add versioned scenario definitions and immutable executions:

- `rate_scenario`: editable identity plus current version pointer;
- `rate_scenario_version`: immutable canonical input, baseline epoch, demand profile, policies,
  author, and content hash;
- `rate_scenario_run`: immutable engine version, frozen WIP/resource snapshots, result payload,
  readiness, diagnostics, timestamps, and input/result hashes.

Runs reuse the existing simulation snapshot/replay envelope where possible. A candidate baseline is
deep-copied into the run envelope as its canonical epoch definition, transition state, resource
profile, and content hash; a pointer or epoch key alone is insufficient. Identical inputs are
content-addressed. Historical runs never re-read mutable candidate or registry state during replay.

Ephemeral local execution may be read-only, but saving, sharing, or deleting scenario identities
requires authenticated identity, server-derived authorization, secure session cookies, and CSRF.
Executions and version history are append-only; deleting an editable scenario identity cannot erase
its audit runs.

## Application Design

Extend the existing `/levers` Scenarios workspace into three tabs:

1. `Current WIP` - existing tactical presets and unit pull-in results;
2. `Rate Planner` - demand/ramp inputs, baseline selection, and run control;
3. `Saved Runs` - immutable comparisons and audit exports.

The Rate Planner is a dense operational work surface, not a wizard or marketing page:

- compact input rail with monthly/annual segmented mode;
- editable monthly demand grid and product-mix controls;
- baseline/candidate selector with readiness badge;
- results table separating skill-pool hires, WC allocations, and tool additions;
- throughput/backlog chart and constraint-sequence timeline;
- package comparison with minimum-viable/resilient labels;
- assumptions drawer with unresolved items first;
- links to Resource Registry, Factory Map, and affected WCs.

Long-running searches run asynchronously with progress, cancellation, bounded search diagnostics,
and stale-input detection. Desktop/mobile, keyboard, light/dark, print/export, and WCAG A/AA are part
of delivery rather than deferred polish.

## Delivery Plan

### RATE-01a - Contracts and readiness

- Define canonical demand, operating-policy, skill-pool, product-mix, feasibility, and result DTOs.
- Add explicit baseline epoch selection and active-program enforcement.
- Build the readiness matrix and fail-closed unresolved-resource behavior.
- Define productive-hours-per-FTE and skill-matrix evidence contracts.

Acceptance: annual/monthly inputs canonicalize deterministically; inactive BCA and mixed epoch
contexts are rejected; missing tool spans or labor denominators cannot produce definitive additions.

### RATE-01b - Synthetic demand and steady-state engine

- Generate deterministic scenario-only orders and release calendars.
- Add WIP netting, shared-program demand, external-demand policy, warm-up/measurement/cool-down, and
  backlog stability checks.
- Produce analytical labor/tool lower bounds and baseline sustainable-rate search.

Acceptance: synthetic units never enter operational tables; boundary/censoring tests pass; known
closed-form fixtures match the simulation; input order does not change results.

### RATE-01c - Historical calibration and ramp evidence gate

- Backtest the demand generator and baseline engine against historical releases, WIP, completions,
  work-center labor hours, staffing, and validated occupancy evidence.
- Establish productive-hours-per-FTE and new-hire learning curves by skill pool, with owners,
  retention/training-completion yields, evidence windows, review cadence, and sensitivity ranges.
- Review at least one Aeronose and one Elevator historical rate interval with manufacturing/IE.

Progress 2026-09-17: the staged read-only IFS cohort and current published-baseline replay are
implemented. Elevator n=8 produced cycle MAE 45.5 days, completion WAPE 200.00%, WIP WAPE 60.28%,
and labor WAPE 21.88%. Aeronose n=24 produced 75.4 days, 58.33%, 86.72%, and 53.55%. Both fail the
diagnostic timing/WIP bands. The thresholds are not approved, staffing evidence is unresolved, and
tooling remains unresolved; this is evidence for reconciliation, not a resource recommendation.

Acceptance: baseline throughput, WIP/backlog, labor-hour, and cycle-time errors meet owner-approved
thresholds; learning curves and staffing denominators are READY or explicitly provisional; the
joint solver cannot produce release-candidate headcount/tool packages before this gate passes.

### RATE-01d - Joint labor/tool package solver

- Add integer shift staffing, skill eligibility, overtime, tool-slot increments, and deterministic
  joint-vector branch-and-bound search, including coupled blocking-resource clusters.
- Enforce configurable hard upper bounds by skill/tool pool plus global node, runtime, horizon, and
  frontier-size limits. Pathological shared-priority consumption must terminate as
  `SEARCH INCOMPLETE` with the exhausted bounds identified.
- Produce the explicitly defined FTE/tool-slot/time Pareto frontier, componentwise pool-vector
  dominance, bounded anchor packages, bottleneck sequence, package gains, and optional cost-aware
  selection when governed weights exist.
- Add deterministic resilience stress cases.

Acceptance: no worker is double-counted across WCs; labor and tools are re-solved jointly; every
recommended package is feasible in a replayable run; isolated zero-gain additions cannot terminate
coupled search; search-bound exhaustion is visible; unresolved tools remain unresolved.

### RATE-01e - Immutable scenarios and audit

- Add scenario/version/run persistence, content hashes, actor attribution, replay, export, and
  retention behavior.
- Keep runs separate from published epochs, forecast logs, plan slots, and IFS state.
- Add cancellation, bounded-search diagnostics, and stale-input rejection.

Acceptance: exact replay succeeds without mutable registry reads; update/delete cannot alter run
history; saving/sharing is unavailable before identity/CSRF controls pass.

### RATE-01f - Rate Planner UI

- Add the Rate Planner and Saved Runs tabs to Scenarios.
- Render demand profile, throughput/backlog, headcount by skill pool and WC allocation, tooling,
  package frontier, readiness, source provenance, and drill-through links.
- Add CSV/JSON export and print view.

Acceptance: the UI never labels provisional/unresolved results as feasible; no cross-context data is
blended; desktop/mobile, keyboard, light/dark, WCAG A/AA, and performance budgets pass.

### RATE-01g - Release validation and owner acceptance

- Run forward shadow cases and compare recommended additions to owner judgment and observed rate
  performance; document false constraints, missed constraints, and shared-capacity spillover.
- Validate each program/resource class after its tooling evidence gate passes.

Acceptance: resource-gap and time-to-rate error thresholds are approved; readiness is sufficient for
each resource class; the feature remains scenario-only until owner acceptance. Tool procurement
recommendations remain gated by TOOL-01d/TOOL-02/TOOL-03 evidence.

## Dependencies and Recommended Sequence

- RATE-01a and RATE-01b can begin using current governed labor/resource foundations.
- RATE-01c calibration must pass before RATE-01d solver recommendations or RATE-01f production UI
  are eligible for owner use. UI scaffolding may be developed behind a disabled/internal gate.
- AVAIL-02 identity/CSRF is required before saved-scenario authoring; ephemeral read-only runs may be
  developed earlier.
- UI-01d shared-capacity data contracts should be reused, not duplicated.
- Aeronose tool recommendations require TOOL-01c/01d; until then they remain provisional/unresolved.
- Elevator tooling recommendations require TOOL-02.
- Aegis tooling recommendations require TOOL-03 or must show unresolved at rates beyond the reviewed
  present-rate case.
- RATE-01g follows those program-specific evidence gates; it does not block calibration prototypes.

## Test Strategy

- pure unit tests for demand accumulation, calendars, FTE conversion, readiness, Pareto dominance,
  lead-time logic, and deterministic tie-breaking;
- analytical fixtures with known labor and tooling solutions;
- shared-pool tests proving no cross-program or cross-WC double counting;
- mixed labor/tool cases where isolated additions have zero gain but a joint vector is feasible;
- learning-curve cohort tests proving new hires do not receive full productivity on day one;
- retention-yield tests proving planned hires and productive retained FTE are not conflated;
- unresolved/provisional evidence tests;
- horizon warm-up, measurement-only backlog slope, cool-down isolation, censoring, and infeasibility tests;
- replay/hash and append-only persistence tests;
- past-due requisition and hard solver-bound diagnostics;
- authorization/CSRF tests for saved scenarios;
- full regression and exact static golden forecast;
- browser coverage for desktop/mobile, keyboard, light/dark, WCAG A/AA, cancellation, and failure
  states;
- bounded performance tests for demand horizon and search-space size.

## Explicit Non-goals

- No automatic hiring requisition, purchase request, budget approval, or epoch promotion.
- No single optimal package without governed comparison weights.
- No probabilistic resilience claim without calibrated distributions.
- No headcount claim from labor hours without productive-hours and skill-pool evidence.
- No zero-tool recommendation for an unresolved tooling family.
- No BCA demand or resources while BCA remains inactive.
- No mutation of operational WIP, forecast logs, plan slots, IFS, or published outputs.

## Open Product Decisions

During RATE-01a/01c and before RATE-01d solver acceptance, owners must approve:

1. default minimum-viable utilization/reserve policy by labor and tooling class;
2. named deterministic stress cases for the resilient posture;
3. whether cost/priority weights will be entered or the UI will show only the Pareto frontier;
4. productive-hours-per-FTE ownership and review cadence;
5. learning-curve ownership, cohort granularity, and review cadence by skill pool;
6. retention/training-completion yield ownership and whether it is modeled separately from the
   learning curve;
7. maximum scenario horizon, per-pool/global capacity-vector bounds, solver node/runtime budget,
   and frontier size;
8. which roles may save/share scenarios versus run ephemeral local analyses.

## Critic Review Record

Gemini 3.1 Pro reviewed the initial plan and returned `NOT SATISFIED` on five material issues. The
revised plan:

- replaces greedy single-resource increments with bounded joint-vector search;
- adds governed dated-hire learning curves;
- moves historical calibration before solver recommendations and owner-facing UI;
- defines the Pareto objectives and componentwise tooling dominance;
- isolates sustainability measures from cooldown backlog clearing;
- exposes shared-capacity consumption, required/requisition dates, and frozen candidate definitions.

The second review returned `SATISFIED`. Its optional refinements are also incorporated: past-due
requisition risk, cohort retention yield, and hard per-pool/global search bounds.
