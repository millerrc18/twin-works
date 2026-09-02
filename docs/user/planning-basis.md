# Planning Basis and Publication

Planning basis and model lifecycle answer different questions.

| Concept | Question |
| --- | --- |
| Planning basis | Which approved target is used for comparison? |
| Lifecycle | How mature is this model definition? |
| Publication | Which commitment-ready epoch may appear in operating forecasts? |

## Planning bases

- `PLAN_SLOTS`: unit assignments come from an approved plan such as the RTG schedule.
- `CONTRACT_DATES`: the contractual date is the comparison target.
- `NONE`: position and evidence may be observed, but no target comparison is valid.

## Lifecycle

Candidate definitions progress through `DRAFT`, `OBSERVE`, and `PROVISIONAL` before they may reach
`COMMITMENT_READY`. Publication is a separate authorized event. Pausing or archiving a candidate
does not delete its history.

TwinWorks suppresses candidate dates and delivery KPIs until a commitment-ready epoch is explicitly
published. See [Resources and Tooling](/handbook/resources-tooling) for assumption readiness.
