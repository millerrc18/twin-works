# RATE-01c Labor and Throughput Calibration

## Status

Provisional evidence delivered 2026-09-17. The historical extraction and scoring path is working,
but RATE-01c has not passed. Both programs fail the current diagnostic timing/WIP bands, the bands
are not owner-approved, staffing evidence is unresolved, and tooling remains unresolved. RATE-01d
solver recommendations and the owner-facing Rate Planner remain disabled.

## Evidence Contract

- Scope: current configured top-level Elevator and Aeronose parts only; BCA and Aegis are excluded.
- History window: first top-level IFS labor clock from 2025-12-01 through 2026-09-17.
- Measurement window: 2026-03-01 through 2026-09-17; open units remain in actual WIP through the
  measurement end.
- Calendar buckets clip exactly to the first and final measurement dates. Events after 2026-09-17
  cannot change this evidence, and the partial September WIP denominator is 17 days rather than 30.
- Actual completion: latest finish clock on the configured Pack and Ship operation only when that
  IFS operation is closed.
- Modeled completion: current published TwinWorks route simulated from each actual first labor
  clock under one immutable published baseline context.
- Actual labor: non-reversed IFS `LABOR_RPT` setup plus labor time, summed by order and WC. Both the
  posting timestamp and transaction date must fall on or before 2026-09-17; live cumulative totals
  are not used as historical measurement truth.
- Modeled labor: current TwinWorks route hours. IFS historical planned hours are retained only as a
  diagnostic and do not replace the modeled baseline.

IFS extraction is staged into first-clock cohort, order/labor detail, terminal completion, and WC
labor queries. The IFS MCP does not support the original CTE form and limits responses to 100 rows.
Every stage rejects failed or truncated responses; an incomplete cohort cannot be scored as no data.

## Diagnostic Bands

These values are engineering diagnostics, not approved release criteria:

| Measure | Diagnostic maximum |
| --- | ---: |
| Completed-order sample | 8 minimum |
| Cycle-time MAE | 14.0 days |
| Monthly completion WAPE | 25% |
| Monthly average-WIP WAPE | 25% |
| Per-order labor WAPE | 25% |

`THRESHOLDS_UNAPPROVED` is therefore a blocker even if a numeric band happens to pass.

## Results

| Program | Completed n | Flow units | Historical revisions | Cycle MAE | Cycle bias | Completion WAPE | WIP WAPE | Labor WAPE | Result |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Elevator | 8 | 30 | 1, 2 | 45.5 d | -45.5 d | 200.00% | 60.28% | 21.88% | FAILED |
| Aeronose | 24 | 33 | 15, 16, 17 | 75.4 d | -75.4 d | 58.33% | 86.72% | 53.55% | FAILED |

Negative cycle bias means the current deterministic route completed earlier than IFS actuals. For
Elevator, the model completed six units in June and six in July while IFS recorded no terminal
completions until August. August average WIP was 20.29 actual versus 7.16 modeled. Aeronose actual
monthly WIP ranged from 8.94 to 15.23 from March through May while modeled WIP ranged from 1.55 to
2.26.

## Work-Center Diagnostics

Current-route planned hours are compared with IFS actuals for the completed measurement cohort.
These are reconciliation leads, not approved capacity factors.

| Program / WC | Current-route plan | IFS actual | Actual minus plan | WC error |
| --- | ---: | ---: | ---: | ---: |
| Elevator `32684` | 2,026.400 h | 2,542.083 h | +515.683 h | 20.29% |
| Elevator `32687` | 162.400 h | 333.550 h | +171.150 h | 51.31% |
| Elevator `INSP` | 0 h | 124.850 h | +124.850 h | 100.00% |
| Aeronose `AEROL` | 543.120 h | 2,141.817 h | +1,598.697 h | 74.64% |
| Aeronose `P3 QA` | 66.600 h | 503.483 h | +436.883 h | 86.77% |
| Aeronose `238` | 52.560 h | 281.483 h | +228.923 h | 81.33% |
| Aeronose `ATUP` | 52.560 h | 267.083 h | +214.523 h | 80.32% |
| Aeronose `INSP` | 0 h | 410.867 h | +410.867 h | 100.00% |

The historical cohorts span older route revisions while modeled labor uses the current route. WC
deltas can also include rework, support/inspection reporting, queue behavior, and current WC mapping
differences. They do not prove a staffing number, a tooling wait, or a causal capacity constraint.

## Decision and Next Gate

RATE-01c remains open. Before rerunning it as an acceptance gate:

1. Manufacturing/IE and the program owner must review one Elevator and one Aeronose interval and
   approve the release/completion semantics, measurement window, and error thresholds.
2. Reconcile current route content against historical revisions and classify actual labor on WCs
   absent from the current modeled route, especially `INSP`, `AEROL`, `P3 QA`, `238`, and `ATUP`.
3. Record productive-hours/FTE, current staffing, WC/shift eligibility, learning curves, and
   retention/training-completion yield through RATE-01a governance.
4. Keep tooling readiness `UNRESOLVED` until TOOL-01/02/03 evidence passes. Do not attribute the
   observed timing gap to tooling without occupancy evidence.
5. Rerun the immutable published baseline after approved corrections. RATE-01d stays blocked until
   the approved calibration gate passes.

## Reproduction

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts\calibrate_rate_history.py
```

The generated raw evidence is local and ignored at
`output/rate_calibration_2026-09-17.json`; this validation record contains the reviewed summary.
The script is read-only against IFS and does not modify operational WIP, forecasts, epochs, slots,
staffing assumptions, tooling, or IFS records.

## Verification

- Live read-only IFS calibration completed for both programs and wrote the local evidence JSON.
- Focused RATE-01c suite: 18 passed.
- Full regression suite: 171 passed with the existing warning set.
- `ruff check app tests scripts`: passed.
- `python -m tests.golden check`: exact, no forecast drift.
- `git diff --check`: no whitespace errors; only the repository line-ending advisory was emitted.
- Gemini 3.1 Pro found and required removal of live cumulative labor leakage. After per-order and
  WC labor were bounded by both posting timestamp and transaction date, the follow-up review
  returned `SATISFIED`; threshold, staffing, tooling, and late-closure governance remain explicit
  residual risks rather than hidden assumptions.
