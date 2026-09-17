# Aeronose Tooling Open Floor Questions

## Purpose

This is the follow-up list for questions that could not be resolved from controlled work
instructions, IFS clocking, or the program manager interview completed 2026-09-03. These questions
block only the affected tooling bindings. They do not block recording known inventory or running
explicit sensitivity studies.

## Questions Requiring Floor or Manufacturing Input

| ID | Question | Why it matters | Current evidence | Required disposition |
| --- | --- | --- | --- | --- |
| AF-01 | At what exact event is the top-level radome removed from assembly fixture `3700AF0001` and the fixture reusable? | An assembly-jig lease cannot be released safely without a physical event. | ASSY Rev K pins the shell to the AF in op 625 and removes only the drill basket in op 630. A second review of the source DOCX XML and figures found no radome-removal instruction. | Manufacturing/process owner identifies the physical release step and the corresponding route or modeled substep. |
| AF-02 | Does the larger drill-basket pin arrangement on `3700AF0001 Dup 1` add setup time or restrict compatibility? | The two jigs are owner-confirmed interchangeable, but a setup penalty or compatibility rule may still be required. | ASSY Rev K documents larger pins on Dup 1. Ryan does not know the operational impact. | Manufacturing confirms no impact or supplies the setup/compatibility rule. |
| HF-01 | What condition does the wooden blue holding fixture `3700HF0001` support, and when is it acquired and released? | Its identity/count are resolved, but its span is required before it can constrain the model. | Ryan confirms one Aeronose-dedicated holding fixture, separate from both dolly families. | Floor owner identifies the physical hold boundaries. |
| PD-01 | Are all six listed paint dollies serviceable/interchangeable, and when does a radome acquire and release one? | Count alone does not establish available capacity or occupancy duration. | Tooling list identifies six records; paint dollies move radomes from assembly through paint. | Floor owner confirms compatibility, current serviceability, and physical boundaries. |
| HD-01 | What work do the nine `3700HD0003-DUP0` through `DUP8` handling dollies support, and when are they acquired/released? | Their purpose and span are required before deciding whether they constrain flow. | Tooling list confirms nine handling dollies. | Floor owner confirms purpose, compatibility, serviceability, and physical boundaries. |
| MAINT-01 | What was the shell lamination mold's actual removal date? | The shadow uses two available molds during the outage, so its effective start must be auditable. | Ryan confirms one mold is in the tool shop as a fabrication aid for the new core/plug locating template; no work is being performed on the mold. | Confirm effective outage start. |
| MAINT-02 | When does the shell mold actually return to service? | The third slot must not restore before physical return. | Ryan will confirm return; the mold can be used immediately once back. | Record actual return through the tooling availability control. |
| TURN-01 | What turnaround allowance best represents normal mold reuse after release? | Immediate reuse is possible in the engine but may overstate practical cadence. | No separate cleanup operation is clocked; observed idle gaps are non-causal. Ryan expects some practical padding. | Run 0-, 2-, and 4-hour shell/core shadow sensitivities and select a value from reviewed observations. |

## Questions Assigned to Data Validation

These do not require Ryan to inventory tools manually:

| ID | Validation | Method |
| --- | --- | --- |
| WIP-01 | Determine current units occupying shell molds and the core-forming set. | Derive as-of holders from IFS acquire/release operation status and clocking, then flag any count conflict for floor review. |
| WIP-02 | Determine current units occupying assembly or holding fixtures after their spans are known. | Reconstruct from the approved route events; do not infer before AF-01/HF-01 are resolved. |

## Resolved Clarifications

- All seven tooling families are dedicated to Aeronose.
- Assembly jigs and shell molds are fungible within their families; `3700HF0001` is a singleton.
- The one holding fixture is wooden, painted blue, and separate from both dolly families.
- Six paint-dolly and nine handling-dolly identifiers are recorded from the tooling list.
- The core-forming capacity is one atomic set consisting of `3700LM0002`, `3700LM0003`, and the
  nose-forming mold.
- Op 775 is performed on a dolly and has no fixed electrical-seal station.
- One shell mold is confirmed in the tool shop as a template-fabrication aid. It is immediately
  production-ready upon owner-confirmed return; actual removal and return dates remain open.
- Individual tooling serials and preventive-maintenance scheduling are deferred. Availability is
  count-based in the first release.
