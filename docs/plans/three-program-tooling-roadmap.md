# Three-Program Tooling Roadmap

## Decision

As of 2026-09-02, TwinWorks product scope is Elevator (`ELEV`), Aeronose (`RAD`), and Aegis
(`AEGIS`). BCA is paused indefinitely and is not part of active navigation, data collection,
capacity modeling, forecasts, KPIs, or promotion work.

Completed BCA discovery, immutable epoch history, and quarantine evidence are retained as audit
history. They are not deleted, promoted, or allowed to influence the three active programs. A future
BCA restart requires a new explicit product decision and fresh source/resource recertification.

## Why This Pivot

BCA is materially larger than the current programs and its tooling, labor-pool, machine, and dwell
constraints are not sufficiently known. Continuing would create a precise-looking forecast with an
incomplete physical model. Aeronose has a known initial tooling inventory, an RTG plan, and enough
operational familiarity to validate the general occupancy model safely.

The generic resource-governance work remains valuable. Physical pool identity, immutable
assumptions, candidate epochs, replay, readiness, and causal comparison apply directly to tooling
for all three active programs.

## Product Boundary

| Program | Planning basis | Tooling approach |
| --- | --- | --- |
| Elevator | RTG plan slots | Survey after Aeronose pilot; no guessed tool constraints |
| Aeronose | RTG plan slots | First complete tooling inventory, bindings, and shadow pilot |
| Aegis | Contract dates | Document present-rate nonbinding assessment with owner and expiry |
| BCA | Out of active scope | Retain history only; no refresh, model, navigation, or forecast |

## Aeronose Initial Tool Inventory

The program manager has identified the following physical counts:

| Tool pool | Count | Current status |
| --- | ---: | --- |
| Assembly jigs | 2 | Owner-supplied count; operation span pending |
| Holding fixtures | 2 | Owner-supplied count; operation span pending |
| Trim fixture | 1 | Owner-supplied count; operation span pending |
| Shell lamination molds | 3 | Owner-supplied count; operation span pending |
| Core-forming mold set | 1 | Owner-supplied count; operation span pending |

Counts alone do not authorize schedule impact. Each pool also requires instance/fungibility review,
acquire and release events, minimum hold and cleanup/changeover time, maintenance exceptions,
owner, approver, evidence source, effective date, and review date.

## Workstreams

### SCOPE-01 - Park BCA without deleting history

**Delivered 2026-09-02:** `BCAFIN` is inactive and its sole candidate epoch is `ARCHIVED`.
ELEV/RAD/AEGIS are the only active registry/sync/WIP/simulation programs. The 73 BCA position rows
and 12 `BCALAY` quarantine events remain intact; BCA has zero forecast-log rows. Backup SHA-256:
`22ADC5E690FA00328D11A0EF241FE67345BF850DEE3BCAB55D906C38F7888FA6`.

1. Transition the BCA finishing candidate from `OBSERVE` to `ARCHIVED` through the authorized
   lifecycle service.
2. Mark the BCA program inactive so it leaves navigation, portfolio reads, sync targets, and data
   collection. Do not delete its program row, epochs, snapshots, or source metadata.
   Enforce `Program.active` at the program registry, sync/data-ingress queries, WIP state matrix,
   pooled simulation inputs, and forecast-log stamping; hiding a UI link is not sufficient.
3. Retain `BCALAY` quarantine events and policies as read-only audit evidence. It remains absent
   from the program registry.
4. Prove ELEV/RAD/AEGIS forecasts, navigation, refresh, and forecast logging are unchanged.
5. Record restart criteria: explicit product approval, new candidate epoch, current routing/WIP
   rediscovery, resource/tooling approval, and a new shadow pilot.

### RES-01 - Preserve the generic resource foundation

**Delivered 2026-09-02:** the physical effort-pool runtime, governed capacity/calendar/reserve
inputs, immutable shadow candidates, replay compatibility, and causal profile comparison remain as
three-program platform infrastructure. No BCA physical pool was created.

1. Reframe the completed physical labor-pool runtime as platform infrastructure rather than a BCA
   deliverable.
2. Preserve legacy publication and the `LEGACY`, `DB_SHADOW`, and `DB_ACTIVE` run separation.
3. Keep physical capacity and tooling changes candidate-only until their own acceptance gates pass.
4. Remove BCA-specific next-step language from current handoffs while retaining historical BCA
   validation documents as archived evidence.

### TOOL-01 - Aeronose tooling pilot

#### TOOL-01a - Inventory and authority

**Progress 2026-09-02:** all five counts are persisted as visible `DRAFT` / `INTERNAL_ONLY` slot
pools with zero bindings. The task remains open for floor/process approval, fungibility, calendar,
changeover, shared-consumer, and operation-span decisions. See
`docs/validation/tool-01a-aeronose-inventory.md`.

- Create draft `TOOL` pools for the five known tool families and their confirmed counts.
- Record whether instances are fungible or individually constrained.
- Classify every pool as dedicated or physically shared. A shared tool must identify every known
  consuming program; demand is never hidden or treated as a nonblocking ghost record.
- Assign floor/process owner, approver, evidence source, effective date, and review date.
- Keep every pool `INTERNAL_ONLY` until operation spans and operating rules are approved.

#### TOOL-01b - Generic occupancy allocator and parity

**Delivered 2026-09-02:** core fixed reservations, active lease primitives, approved-binding profile
compilation, operation/cure/route releases, and replayable occupancy traces are implemented;
existing cure stations use the allocator with exact golden parity. Future maintenance intervals,
initial WIP holdings, same-shift priority retry, and fatal no-progress handling are complete. Why
rendering follows real Aeronose bindings in TOOL-01d. See
`docs/validation/tool-01b-occupancy-core.md`.

- Implement deterministic, atomic acquisition of all tooling needed at an operation.
- A unit acquires none unless every required slot is available.
- Support fungible slots, named instances, multi-tool acquisition, minimum hold, lag,
  cleanup/changeover, maintenance exceptions, and approved release events.
- Reject invalid releases and fail loudly on deadlock/no progress.
- Queue requests deterministically by `(ready_time, DPAS-behind priority, commit date, program,
  serial, pool code)`. Input/database row order must never decide which unit acquires a tool.
- A deadlock raises a fatal `ResourceAllocationDeadlock`, aborts the candidate run, writes no
  forecast result/log, and opens a blocking review. It never skips the blocked units or mutates the
  immutable epoch into an ad hoc failure state.
- Migrate the existing Plant 2 paint-booth and Plant 3 electrical-seal station constraints through
  the same allocator and prove exact legacy/golden parity before Aeronose tools can affect a shadow.

#### TOOL-01c - Aeronose operation bindings

- Review the current Aeronose routing and work instructions with manufacturing/process ownership.
- Approve acquire/release spans for each tool pool; never infer spans from count or proximity alone.
- Validate overlapping requirements and atomic acquisition where a unit needs more than one tool.
- Freeze approved bindings in an immutable Aeronose candidate epoch.

#### TOOL-01d - Shadow evaluation and explainability

- Run identical Aeronose WIP through the published legacy model and tooling candidate.
- Show per-unit date movement, occupancy windows, blocked tool, wait duration, assumption IDs, and
  RTG-slot impact without changing published dates.
- Add tooling occupancy and availability to Resources, the unit Why view, and Factory Map detail;
  do not mix shadow tooling pressure with published commitment KPIs.
- All pressure-board and tooling views require an explicit `PUBLISHED` or candidate epoch context.
  Aggregation across those contexts is prohibited.

#### TOOL-01e - Pilot and decision

- Run a 2-4 week shadow pilot with replayable snapshots.
- Compare tool utilization/waits to floor reality and record false waits, missed constraints, and
  data freshness.
- Exit requires two consecutive reviewed weeks, zero unresolved severity-1 tool identity/span or
  missed-conflict defects, complete lease traces for every observed tool hold, and acquire/release
  timing MAE within one production shift for a sufficient reviewed sample. If the sample is too
  small, extend the pilot rather than waive the evidence gate.
- Promotion requires tooling owner, program, and scheduling approval. Rollback remains the current
  published legacy epoch.

### TOOL-02 - Elevator tooling survey and candidate

- Inventory assembly jigs, holding/trim fixtures, molds, dedicated gauges, and any cross-program
  shared tools.
- Apply the TOOL-01 evidence and binding contract; do not copy Aeronose spans or availability.
- Begin an Elevator shadow only after the inventory and acquire/release boundaries are approved.

### TOOL-03 - Aegis present-rate assessment

- Record the current rate-one-per-month assessment as an expiring owner-approved statement, not as
  a permanent absence of constraints.
- Inventory any tooling that could become binding under a rate or mix change.
- Classify each tool as Aegis-dedicated or physically shared. Shared demand participates in the same
  physical pool even at low rate; create dedicated occupancy constraints only when evidence shows
  they can affect the forecast horizon.

## Execution Order

1. SCOPE-01 park BCA and prove three-program no-drift.
2. RES-01 reframe and commit the generic resource foundation.
3. TOOL-01a create the governed Aeronose tooling inventory.
4. TOOL-01b build the generic occupancy allocator and migrate cure stations with exact parity.
5. #32b confirm the Plant 3 electrical-seal station count in a distinct successor candidate epoch;
   do not alter the parity epoch.
6. TOOL-01c approve Aeronose operation bindings.
7. TOOL-01d run the Aeronose tooling shadow and expose explanations.
8. DOC-01a/DOC-01b add the in-app handbook shell and core user documentation.
9. UI-01d add the three-program resource/tooling pressure board from governed data.
10. TOOL-02 execute the Elevator tooling survey and shadow candidate.
11. TOOL-03 record and periodically review Aegis present-rate assumptions.
12. DOC-01c add contextual help after tooling views stabilize.
13. PLAT-01d certify accepted physical/tooling candidates without promotion.
14. UI-01e/DOC-01d complete integrated UX and documentation acceptance.
15. TOOL-01e complete the pilot; PLAT-01e promotes only explicitly accepted epochs.

The governed work-center catalog (#82-1a), reviewed floor-map follow-ons, and DOC-01a/DOC-01b may
run in parallel once SCOPE-01 is complete. Contextual DOC-01c follows stable tooling views.

## Phase Gates

1. **Scope isolation:** BCA is absent from active product surfaces and refresh behavior; history is
   intact; `Program.active` excludes it at ingress and from the WIP/simulation state matrix; the
   three published forecasts are exact.
2. **Allocator parity:** existing cure-station results and the static golden forecast are unchanged
   after migration to generic occupancy leases. Queue ordering is explicit and independent of input
   order. Deadlock aborts the entire run and creates a blocking review rather than partial output.
3. **Tool identity:** every Aeronose pool has count, type, fungibility, provenance, owner, effective
   date, and review date.
4. **Binding validity:** every acquire/release event exists in the frozen routing; all multi-tool
   requirements are atomic and deadlock-tested.
5. **Shadow honesty:** tool effects are visible and replayable but excluded from published dates and
   portfolio commitment KPIs. UI/read models require one explicit published-or-candidate epoch
   context and cannot aggregate across contexts.
6. **Floor validation:** two consecutive reviewed weeks meet the lease-completeness, severity-1,
   sample-sufficiency, and one-shift timing-error criteria; insufficient evidence extends the pilot.
7. **Promotion:** pilot evidence and named owner approvals support promotion; otherwise the legacy
   epoch remains active.

## Explicit Non-Goals

- No active BCA program, refresh, forecast, KPI, or capacity/tooling work.
- No deletion of BCA audit history.
- No guessed Aeronose operation spans or tool availability.
- No automatic promotion based on test success alone.
- No assumption that Aegis tooling will remain nonbinding if rate or product mix changes.

## Critic Review Record

Gemini 3.1 Pro reviewed the proposed pivot and sequencing. The revised plan incorporates its
material findings:

- BCA isolation is enforced at registry and data ingress, not only in navigation.
- Occupancy requests use an explicit deterministic queue key.
- Deadlock aborts the candidate run and opens a blocking review; the existing epoch lifecycle is
  not mutated with an invented failure state.
- #32b calibration occurs in a successor candidate after allocator parity is frozen.
- UI/read models require one explicit published-or-candidate epoch context.
- Pilot acceptance uses reviewed lease coverage, severity, sample sufficiency, and timing error.

The suggestion to model shared Aegis demand as nonblocking or ghost demand was rejected. Physical
sharing must be represented honestly: a dedicated tool is partitioned, while a shared tool consumes
the same physical pool regardless of Aegis's current low rate.
