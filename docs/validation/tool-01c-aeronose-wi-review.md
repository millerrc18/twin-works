# TOOL-01c Aeronose Work-Instruction and IFS Review

## Status

Evidence review completed 2026-09-03. No live occupancy binding was created or approved. The five
Aeronose pools remain `DRAFT` / `INTERNAL_ONLY`, carry zero bindings, and cannot affect published
or shadow forecasts yet.

Ryan Miller is recorded as owner and current approver. Seven pools are Aeronose-dedicated.
Assembly jigs and shell lamination molds are owner-confirmed fungible within their families. The
holding and trim fixtures are singletons. Paint- and handling-dolly compatibility remains open. The core-forming capacity is represented as one
coordinated set pending component-stream integration.

## Controlled Sources

Current controlled files were read from the SharePoint `MVA Manufacturing Document Library` with
`ProgramSelectionId = 14`:

| Work instruction | Controlled revision | Modified |
| --- | --- | --- |
| `WI 3700ED0001-101 LAM` | F | 2026-07-20 |
| `WI 3700COREKIT` | H | 2026-07-02 |
| `WI 3700ED0001-101 ASSY` | K | 2025-07-30 |
| `WI 3700ED0001-101 PAINT` | B | 2026-06-25 |

Working copies and extracted Markdown remain outside the repository under
`C:\Users\ryan.c.miller\Downloads\Aeronose_WI_Current`. They are controlled/export-restricted
manufacturing material and are not committed.

Read-only IFS evidence was captured 2026-09-03 from Marion site `59`, project `C48178`, using
`scripts/audit_aeronose_tooling.py`. The audit selected active routing revisions 16 for
`3700ED0001-101`, 5 for `3700ED0001-101SUBRING`, and 3 for `3700COREKIT`. At capture time those
routes had 7, 11, and 9 active shop orders respectively. Timing summaries use at most the 100 most
recent orders per part since 2025-01-01 and contain no employee-level data.

## Findings by Pool

### Assembly jigs: `3700AF0001`, two slots

The ASSY WI and IFS show that ring construction is a separate component route,
`3700ED0001-101SUBRING`, rather than part of the top-level RAD route.

- Subring acquire: op 600, when the rings and details are loaded and pinned to the assembly fixture.
- Subring release: start of op 612. The WI explicitly says to remove the ring from the AF and perform
  op 612 on a table.
- Top-assembly reacquire: op 620 dry fit. Hinges locate to AF attachments and the shell is centered
  in the drill basket; op 625 lowers and pins the shell to the fixture.
- Top-assembly release: unresolved. A second pass through the original ASSY Rev K DOCX, including
  document XML and embedded figures, confirmed that op 630 explicitly removes only the drill basket.
  No text or figure establishes when the radome itself leaves the AF.
- Instance note: the WI says `3700AF0001 Dup 1` uses larger drill-basket pins. Ryan confirms the two
  jigs are functionally interchangeable but does not know whether the difference adds setup time or
  compatibility limits. Keep the distinction unresolved until manufacturing validates it.

IFS first-start/last-finish clock spans cannot supply the missing physical release. Against two
owner-confirmed jigs, subring spans reached four concurrent units, candidate top-level op 620-to-630
spans reached three, and the combined spans reached five. Those contradictions show that labor
clocking spans include queueing, pauses, or off-fixture work. They do not disprove the count, but
they prohibit deriving occupancy from raw clock duration.

### Holding fixture: `3700HF0001`, one slot

The reviewed WIs do not identify a numbered holding fixture. Ryan confirms one Aeronose-dedicated,
wooden, blue fixture, tool `3700HF0001`. It is separate from both the paint and handling dollies.
Its purpose and physical acquire/release steps remain unresolved, so no binding is permitted until
the actual fixture use is explicit.

### Dolly inventory: six paint, nine handling

The tooling list identifies six paint dollies (`3700HD0001`, `SN4`, `SN5`, `SN6`, `-2`, `-3`) and
nine handling dollies (`3700HD0003-DUP0` through `DUP8`). Paint dollies move radomes from assembly
through paint. Compatibility, current serviceability, exact occupancy spans, and the handling
dollies' purpose are not yet approved. Both pools therefore remain count-only and unbound.

### Trim fixture: `3700TF0001-A01`, one slot

The fixture is acquired within op 580 when the radome is placed nose-down and pinned. The same WI
then requires trim/drain-hole inspection before the radome is removed from the trim table and placed
on a work dolly for chamfering. Release therefore occurs in the middle of op 580, not at operation
completion.

Eighty-five recent complete op-580 clock spans reached two concurrent units against the one
owner-confirmed fixture. That is expected when post-release dolly work is charged to the same op,
and it proves that an op-start-to-op-complete lease would create false waits. TwinWorks needs a
reviewed sub-operation release milestone, or equivalent observed release event, before this fixture
can be bound.

### Shell lamination molds: `3700LM001`, three slots

The LAM WI uses the mold from tool preparation and outer-skin layup through honeycomb, diverter,
inner-skin layup, bagging, and cures. Op 570 starts by demolding the shell, so the defensible
candidate is acquire at op 50 start and release at op 570 start. TwinWorks' current static RAD route
starts at op 130 even though IFS revision 16 contains ops 50 and 90; a tooling candidate must add
those route events rather than silently acquiring late at op 130.

Across 86 complete IFS clock intervals, the WI-derived op-50/90/130-to-op-570-start span reached a
maximum concurrency of three, matching the owner count. Greedy reuse across three slots produced a
minimum observed gap of 0.567 hours and median 32.117 hours. This supports the absence of a long
mandatory post-demold hold, but it does not prove zero cleanup.

The WI places routine wipe/release preparation in op 50. Mold-release touch-up may require a
30-minute ambient cure; a first-use or repaired mold may require three coats and a 250 F, 30-minute
cure. Those are setup/maintenance exceptions, not an invented post-release lag.

### Core-forming mold set: `3700LM0002`, `3700LM0003`, and nose mold

The COREKIT WI requires the lower mold, upper mold, and nose-forming mold for op 600, then bags and
cures the pieces before op 700 unbags and removes them. The candidate hold is op 600 start through
op 700 completion. Seventy-four complete IFS intervals reached one concurrent set; the minimum
observed reuse gap was 2.35 hours and the median was 125.467 hours.

This is a separate `3700COREKIT` component stream. It cannot be honestly bound to top-level RAD op
210 until TwinWorks models the component order and its availability relationship to the consuming
radome.

## Op 775 Electrical Sealing

The ASSY WI identifies only shop aid `SA0145` for a cure puck. The puck remains with the part, while
the currently published/parity route receives a minimum 40-hour cure. No fixed electrical-seal
station is identified, and Ryan confirms the work is performed on a dolly wherever inspection needs
permit. DRDI approval is now being pursued for a separate 2-hour flashoff plus 8-hour cure path.

IFS reinforces that conclusion: 78 recent op-775 labor spans reached four concurrent units. Labor
clock spans are not the 40-hour cure, but the observed concurrency is incompatible with one exclusive
station. Epoch 11 removes `P3_ELECTRICAL_SEAL` while retaining 40 hours and is in `OBSERVE`.
Epoch 12 freezes the proposed 2+8-hour process but remains `DRAFT` pending complete DRDI evidence.
Neither changes the published `RAD:LEGACY` epoch.

## Changeover and Maintenance

Ryan's current operating assumption is immediate reuse after physical release. IFS does not record a
separate cleanup operation and supports short observed reuse for shell/core molds, but its clocking
granularity cannot validate zero lag for trim or assembly fixtures. Keep zero lag as an
owner-confirmed draft, not an approved measured fact.

One shell mold is confirmed in the tool shop as a physical aid for fabrication of the new core and
plug locating template; no work is being performed on the mold. It can return to production use
immediately when Ryan confirms it is back. Actual removal and return times remain follow-up evidence. Other maintenance exists but no
production-impacting intervals are known; do not invent additional dates. Current shell/core holders
will be reconstructed from IFS rather than manually entered.

## Binding Gate

Before freezing the Aeronose tooling candidate:

1. Complete the floor check: confirm the top-assembly AF release, `3700HF0001` and dolly spans,
   dolly compatibility/serviceability, Dup-1 pin setup, current WIP assignments, and outage dates.
2. Confirm whether routine cleaning/setup is contained in the acquiring operation before approving
   zero post-release lag. Do not treat observed idle gaps as cleanup duration.
3. Split op 580 at the reviewed trim-fixture release point, or add an equally explicit frozen
   substep. A generic op-complete release is known to be wrong.
4. Add component-stream modeling for `3700ED0001-101SUBRING` and `3700COREKIT`.
5. Add ops 50 and 90 to the RAD candidate route before binding the shell mold.
6. Record complete DRDI approval evidence before advancing the accelerated epoch from `DRAFT`.

Until all applicable gates are resolved, the registry must retain zero approved Aeronose tooling
bindings and published dates must remain unchanged.

## Reproduction and Backup

Run the read-only audit after connecting TwinWorks to IFS:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\audit_aeronose_tooling.py `
  --window-start 2025-01-01 `
  --output C:\Users\ryan.c.miller\Downloads\Aeronose_WI_Current\aeronose_tooling_ifs_audit.json
```

Before the 2026-09-03 draft metadata update, the local database was copied to
`data/rtg_app_migrated.pre_tooling_review.bak` (git-ignored), SHA-256
`DFA2FDB3688AC4A8C48C23C429D11C940839EE174A6262D31215437E0FD8B992`.

## AI Critic Review

Gemini 3.1 Pro reviewed the evidence and sequencing on 2026-09-03. The plan adopts its material
controls: obtain floor answers before changing route topology, preserve the Dup-1 pin distinction,
never bind an assembly jig without an explicit release, and represent trim with a split/substep
rather than an ambiguous mid-operation release. The suggestion that observed shell/core idle gaps
prove mandatory cleanup was not adopted; IFS timing is non-causal, and the WI places routine setup
inside the acquiring operation. Zero post-release lag therefore remains an owner-confirmed draft.
