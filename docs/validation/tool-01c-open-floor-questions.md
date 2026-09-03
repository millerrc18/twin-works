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
| HF-01 | What are the two Aeronose holding fixtures, what condition do they hold, and when are they acquired and released? | Their identity and span are required before they can constrain the model. | Ryan confirms they are Aeronose-dedicated, interchangeable, and separate from paint dollies. No numbered holding fixture appears in the reviewed WIs. | Floor owner identifies the fixtures and physical hold boundaries. |
| MAINT-01 | Is one shell lamination mold currently at the tool shop, and what was its actual removal date? | The shadow will provisionally use two available molds, but the source condition must be confirmed. | Ryan believes one mold may be out for a new core/plug locating template. | Confirm actual status and effective outage start. |
| MAINT-02 | When does the shell mold actually return to service? | The provisional calendar restores the third mold after 2026-09-25; an early return should be recorded immediately. | Expected back on or before 2026-09-25. | Record actual return through the tooling availability control. |
| TURN-01 | What turnaround allowance best represents normal mold reuse after release? | Immediate reuse is possible in the engine but may overstate practical cadence. | No separate cleanup operation is clocked; observed idle gaps are non-causal. Ryan expects some practical padding. | Run 0-, 2-, and 4-hour shell/core shadow sensitivities and select a value from reviewed observations. |

## Questions Assigned to Data Validation

These do not require Ryan to inventory tools manually:

| ID | Validation | Method |
| --- | --- | --- |
| WIP-01 | Determine current units occupying shell molds and the core-forming set. | Derive as-of holders from IFS acquire/release operation status and clocking, then flag any count conflict for floor review. |
| WIP-02 | Determine current units occupying assembly or holding fixtures after their spans are known. | Reconstruct from the approved route events; do not infer before AF-01/HF-01 are resolved. |

## Resolved Clarifications

- All five tooling families are dedicated to Aeronose.
- Assembly jigs, holding fixtures, and shell molds are fungible within their families.
- Holding fixtures are not the paint dollies. Paint dollies move each part from assembly through
  paint work centers.
- The core-forming capacity is one atomic set consisting of `3700LM0002`, `3700LM0003`, and the
  nose-forming mold.
- Op 775 is performed on a dolly and has no fixed electrical-seal station.
- For the current shell-mold shadow, available count is two through 2026-09-25 and three beginning
  2026-09-26, with immediate early return-to-service entry if the mold comes back sooner.
- Individual tooling serials and preventive-maintenance scheduling are deferred. Availability is
  count-based in the first release.