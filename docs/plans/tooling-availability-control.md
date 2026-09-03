# Tooling Availability Control Plan

## Status

AVAIL-01 delivered 2026-09-03: schema, lifecycle fold, database concurrency/immutability guards,
startup integrity, audit export, clean migration, and tests are complete. The live event table is
empty. AVAIL-02 identity and authorization is next; no write route exists.

## Decision

Add a governed, count-based tooling availability control to TwinWorks before the Aeronose tooling
shadow is activated. The first release manages effective availability for fungible pools; it does
not require tool serial numbers or create a preventive-maintenance system.

For the current Aeronose shell-mold case, the shadow assumption is:

- baseline physical count: 3 shell lamination molds;
- one mold unavailable from 2026-09-03 through 2026-09-25, yielding 2 / 3 available;
- the outage ends at 2026-09-26 00:00 America/New_York, restoring 3 / 3;
- if the mold returns sooner, record an immediate return-to-service event;
- outage reason: tool-shop work for the new core and plug locating template;
- source status: owner-confirmed provisional until actual tool-shop status is verified.

The change remains shadow-only until an Aeronose replacement epoch is explicitly promoted.

## Product Experience

### Resource Registry

Tool rows add a compact availability signal:

- `2 / 3 available now`;
- next change and date;
- reason and evidence status;
- `Published` or named candidate context;
- overdue or conflicting state when applicable.

Availability is never blended across publication contexts.

### Tool Detail

The tool detail view becomes the operating surface, with four unframed sections:

1. **Current state** - total slots, available now, occupied/as-of inferred, unavailable, and next
   planned change.
2. **Availability timeline** - horizontal count bands by effective date, with outage reason and
   early-return markers. It displays count, not serial, in this phase.
3. **Shadow impact** - affected candidate epoch, units delayed, first affected RTG slot, and causal
   wait hours. Published dates are shown separately and remain unchanged.
4. **Audit history** - immutable events with actor, role, effective time, reason, evidence, and the
   successor candidate created from the event.

### Authoring Workflow

Use an action menu with `Record outage`, `Return to service`, and `Extend expected return`.
`Record outage` opens a focused side panel containing:

- available-count stepper constrained to `0..baseline count`; the service stores the resulting
  unavailable quantity, not an absolute capacity;
- effective local date/time;
- expected return local date/time;
- reason menu plus required detail;
- evidence/source note;
- optional review date;
- target candidate context.

Before confirmation, a preview shows the resulting availability timeline, named as-of holding
conflicts, and shadow date movement. The preview carries a source-state hash; confirmation fails if
the baseline, event stream, candidate, or WIP state changed after preview. The confirmation text
explicitly states that published forecasts will not change. Early return requires one action and appends a return event effective at the chosen time.
Corrections append `VOID` or another compensating event; prior history is never edited or deleted.

All users may view availability. Initially, only Ryan Miller and authenticated TwinWorks data
administrators may author events. Actor and authority come from the authenticated server session,
never request form fields.

## Domain Model

### Append-only availability events

Add generic `resource_availability_event` records rather than rewriting
`ResourceCapacityVersion.calendar_policy_json`. Phase 1 accepts only `TOOL` pools with `SLOTS`;
the contract can later serve cure stations or spaces without creating a second event system.
The event stream supports:

- `OUTAGE_OPEN` - pool, unavailable quantity, effective start, expected end, reason, evidence;
- `RETURN_TO_SERVICE` - records the actual early, on-time, or late return timestamp;
- `EXTEND` - supplies a later expected end without changing the original event;
- `CANCEL` - cancels a future outage before it becomes effective;
- `VOID` - records a retrospective correction when the entered outage never occurred.

Each event carries `event_key`, `outage_key`, monotonically increasing sequence, pool ID, optional
future instance code, event type, unavailable quantity, effective timestamp, expected end, reason
code, free-text reason, actor, authority role, evidence JSON, and creation timestamp. Database `BEFORE UPDATE` / `BEFORE DELETE` triggers and ORM guards prohibit mutation; insert
validation rejects invalid sequence, count, timestamp, or cross-pool references.

Phase 1 uses `instance_code = null` and pooled counts. The schema reserves instance targeting so a
later tool-serial/PM feature can use existing `ResourceInstance` identities without changing the
event contract.

### Effective timeline

A pure fold service converts the append-only stream into non-overlapping effective intervals.
Validation rejects unavailable quantities outside the baseline, invalid sequences, and ambiguous
concurrent events. Available capacity at time `t` is the effective baseline count at `t` minus active
outage quantities, floored at zero. This protects a later baseline increase: a one-tool outage still
removes one tool rather than resetting the pool to an old absolute count.

Expected return is stored as an end-exclusive UTC timestamp and displayed in Marion local time. The
current date-only input means two molds are available through September 25 and the third returns at
local midnight beginning September 26. An early return appends a later event that shortens the
interval and restores pooled availability immediately.

The allocator gains pool-level capacity-reduction windows. It must enforce aggregate concurrency
directly and must not bind a count-only outage to a fake physical serial or fixed anonymous slot.
For fungible tools, the only true as-of conflict is when inferred active holders exceed the reduced
available count. A factual outage is retained in that case, while candidate readiness is blocked and
the UI names the affected IFS units; the system neither discards the outage nor silently moves a
unit.

### Epoch and snapshot behavior

Availability events are included in the immutable resource definition and replay envelope. Creating,
returning, extending, or cancelling an event creates a successor candidate only when an existing
`OBSERVE` candidate consumes that pool. The confirmed event and successor creation are one
transaction; a controlled TwinWorks service identity performs the lifecycle step and references the
event in its rationale. The prior candidate remains immutable and historical. Published selections
are untouched.

If no selected candidate consumes the pool, the event is retained as operational evidence and the UI
states `No model impact yet`; no empty epoch is created. Once bindings are approved, candidate
creation freezes all effective availability events.

## Authentication and Authorization Gate

Current admin routes do not bind writes to authenticated application identity. Tooling authoring
must remain disabled until this is corrected.

1. Do not treat an IFS access token as application authorization. Reuse the Azure/OpenID flow only if
   its issuer, audience, nonce, signature, expiry, and email claims are validated for TwinWorks;
   otherwise add a separate application OIDC client.
2. Store only the minimum identity in an encrypted, signed, HTTP-only session cookie with
   `Secure` and `SameSite=Strict` outside local development.
3. Derive actor and role server-side. Never accept either from the form.
4. Grant tooling authoring to Ryan Miller's configured identity and `DATA_ADMIN` identities; all
   other users are read-only. Do not hardcode a personal email in source control.
5. Use CSRF tokens for cookie-authenticated write requests and restrictive CORS. Add 401/403 and
   forged-request coverage for every availability route.
6. Keep role grants in deployed configuration or a governed role table managed by an authenticated
   administrator. The automated candidate compiler uses a separately identified service role.

## Current-WIP Reconstruction

Initial occupancy should come from IFS rather than manual serial entry:

- shell mold: acquire when op 50/90 begins; release at op 570 demold start;
- core-forming set: acquire at COREKIT op 600; release after op 700 removal;
- assembly/holding fixtures: defer until their physical spans are approved.

Reconstruction records the unit as holding an anonymous fungible slot. Conflicts between inferred
holders and available count are surfaced for review and block the shadow; they are not resolved by
due-date ordering.

## Turnaround Sensitivity

Do not publish a guessed cleanup duration. TOOL-01d runs three candidate scenarios for shell and
core-forming molds only:

- 0 hours;
- 2 hours;
- 4 hours.

Assembly, holding, and trim padding stays unset until their release events are known. Each scenario
must report date movement, waits, utilization, and the assumption identifier. The pilot selects a
turnaround only after reviewed floor observations; IFS idle gaps alone are not causal evidence.
This production-release lag is separate from tool-shop return: an early return-to-service restores
availability at its effective timestamp, as requested.

## Implementation Sequence

### AVAIL-01 - Schema and event fold - Delivered 2026-09-03

- Add the generic resource-availability-event table, migration, constraints, SQLite append-only/
  sequence triggers,
  and event service.
- Add pure folding/validation for open, early-return, extension, future cancellation, retrospective void, and overlap cases.
- Extend permanent audit export with availability events.

### AVAIL-02 - Identity and write authorization

- Bind the existing OAuth/OpenID flow to validated app identity.
- Add server-derived resource roles and CSRF protection.
- Keep all availability POST routes unavailable until this gate passes.

### AVAIL-03 - Compiler and candidate succession

- Add pool-level capacity-reduction windows to the allocator; do not assign count-only outages to
  synthetic serials or fixed anonymous slots.
- Include folded events in candidate definitions, readiness, snapshots, hashes, and replay.
- Create successor `OBSERVE` candidates after confirmed changes without touching publication.
- Detect as-of holding conflicts and open blocking review debt.

### AVAIL-04 - Operational UI

- Add registry availability signals and the tool-detail timeline.
- Add outage, early-return, and extension workflows with stale-preview rejection and explicit
  shadow context.
- Add keyboard, mobile, light/dark, and failure-state coverage.

### AVAIL-05 - Aeronose seed and shadow scenarios

- Record the provisional shell-mold outage as two available through 2026-09-25, three afterward.
- Reconcile current shell/core holders from IFS.
- Run 0/2/4-hour shell/core turnaround sensitivities.
- Keep all five tooling pools unbound until the applicable TOOL-01c floor questions are resolved.

## Test and Acceptance Gates

- Event history is append-only at ORM and database levels.
- Invalid counts, timestamps, sequences, overlaps, identities, and CSRF requests fail closed.
- An unauthorized viewer cannot submit or replay an authoring request.
- A one-tool shell-mold outage resolves to 2 / 3 through 2026-09-25 and 3 / 3 from
  2026-09-26 local time, while remaining correct if baseline capacity later changes.
- Early return immediately restores the third pooled slot in a successor candidate.
- Aggregate capacity reduction is deterministic under input and database-row reordering and never
  invents a physical tool serial.
- As-of holdings above available count produce a blocking review, never partial output.
- Each event and candidate replays to the original hashes and causal results.
- Published ELEV/RAD/AEGIS forecasts and the static golden master remain exact.
- The UI states `shadow only` wherever an unpromoted availability can affect dates.
- Desktop/mobile, light/dark, keyboard, axe, and server response-time checks pass.

## Explicit Non-goals

- Tool serial-number management.
- Preventive-maintenance scheduling or work-order integration.
- Automatic capacity changes inferred from IFS clocking.
- Editing or deleting historical availability events.
- Availability writes before authenticated identity/role binding.
- Promotion of the Aeronose tooling candidate.

## Related Evidence

- `docs/validation/tool-01c-aeronose-wi-review.md`
- `docs/validation/tool-01c-open-floor-questions.md`
- `docs/plans/three-program-tooling-roadmap.md`

## AI Critic Review

Gemini 3.1 Pro reviewed the plan on 2026-09-03. The revised plan incorporates its material findings:

- persist outage quantity rather than absolute available count;
- enforce pooled reductions directly instead of assigning an arbitrary anonymous slot;
- show named capacity violations when inferred holders exceed reduced count;
- enforce append-only behavior with SQLite triggers as well as ORM guards;
- make cookie-session and CSRF behavior explicit;
- use strict UTC event timestamps and Marion-local display semantics.

The critic's suggestion to apply production turnaround padding after an early tool-shop return was
not adopted. The user defined early return as immediate return to service; the 0/2/4-hour study is a
separate post-production-release sensitivity for shell and core molds.
