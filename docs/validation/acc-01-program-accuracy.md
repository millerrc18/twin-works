# ACC-01 Program Accuracy Score

## Status

Accuracy v1.0 delivered 2026-09-04. TwinWorks now computes a transparent 0-100 forward accuracy
score for each active program at fixed 7-, 14-, and 21-day horizons. The portfolio shows an honest
calibration state or the first eligible horizon; each program has a dedicated Accuracy workspace.

No retrospective backtest row is blended into the forward score. No score changes a forecast,
model epoch, planning target, or publication state.

## Truth and Eligibility

- Truth is the IFS physical pack-operation date persisted in `PositionState.pack` by an `ifs-sync`.
- Administrative close-only and bootstrap rows are excluded from the headline score.
- Same-day and post-pack forecasts are rejected.
- For horizon `H`, the eligible window is physical pack minus `H+6` through pack minus `H`,
  inclusive. The latest P50 within that window is selected.
- Each program/shop-order contributes at most one forecast per horizon.
- Missing windows remain visible as coverage debt instead of substituting a stale forecast.

The existing model-maturity track was corrected to use one earliest valid pre-pack forecast per
program/shop order. Its current eligible counts are Elevator 3, Aeronose 1, and Aegis 1. This track
remains separate from fixed-horizon Accuracy v1.0 and the retrospective backtest.

## Formula

For each program and horizon:

```text
Timing = 60 * max(0, 1 - MAE / 14)
Hit    = 25 * Hit7
Bias   = 15 * max(0, 1 - abs(Bias) / 14)
Score  = round(Timing + Hit + Bias)
```

`Hit7` is expressed as a fraction in the calculation. Negative bias means forecasts run early;
positive bias means forecasts run late.

Confidence is based only on eligible independent units:

| Eligible units | Confidence |
| ---: | --- |
| 0-4 | Insufficient |
| 5-11 | Preliminary |
| 12-24 | Developing |
| 25+ | Established |

The headline score is hidden until all three horizons have at least five eligible units. Once
eligible, it is `20% * 7-day + 35% * 14-day + 45% * 21-day`, with the weakest horizon confidence.

P80 coverage is displayed separately with a 95% Wilson interval and is not part of the 0-100 score.

## First Live Baseline

As of 2026-09-04:

| Program | 7-day | 14-day | 21-day | Headline |
| --- | --- | --- | --- | --- |
| Elevator | No eligible cohort | No eligible cohort | No eligible cohort | Withheld |
| Aeronose | No eligible cohort | No eligible cohort | No eligible cohort | Withheld |
| Aegis | 11 / 100, n=1, Insufficient | No eligible cohort | No eligible cohort | Withheld |

This sparse state is expected: the forward log began too recently to provide comparable fixed-
horizon evidence. The UI does not rank programs while confidence is insufficient.

## Immutable Provenance

Migration `1b2c3d4e5f60` adds append-only `accuracy_summary_log`. Every daily program/horizon row
freezes:

- formula version `TW-ACC-1.0`;
- as-of date and horizon;
- score, confidence, n, MAE, bias, Hit3, and Hit7;
- P80 coverage and Wilson interval;
- observed, excluded, and missing-window counts;
- source forecast IDs;
- the complete selected cohort payload;
- cohort and content SHA-256 hashes.

Summary updates and deletes are rejected by ORM and SQLite triggers. Ship processing captures a
new daily summary after forward rescoring. Repeated capture of identical same-day evidence is
idempotent.

Pre-migration database backup:
`data/rtg_app_migrated.pre_accuracy_score.bak`

SHA-256:
`B61FD77CD1385A32C0BDD8890BAA4CE6B96F43297E7707B22C3ACBC6524861A1`

## UI

- Portfolio: `Accuracy` column with headline, first eligible horizon, or `Calibrating`.
- Program workspace: dedicated `Accuracy` tab showing all horizons, confidence, n, MAE, bias
  direction, Hit7, P80 coverage/interval, exclusion count, formula, and immutable trend history.
- Desktop and 390px mobile views were verified without page-level horizontal overflow.

## AI Critic Record

Gemini 3.1 Pro reviewed the scoring contract before implementation. The implementation adopts its
material recommendations: standardized horizon windows, physical pack truth, strict leakage
rejection, separate confidence, withheld headline until all horizons reach n=5, separate P80
calibration, and no cross-program ranking at immature confidence.

## Remaining Operational Work

ACC-01d is ongoing evidence accumulation rather than missing software. Continue daily forecast
stamping and physical ship processing. Revisit the 14-day SLA denominator and headline weights only
through a formula-version successor after sufficient forward evidence exists.
## Implementation Review

Gemini 3.1 Pro reviewed the completed scoring and provenance design. It found no material
statistical, leakage, or UI-honesty issue. Verified controls include P50/P80 selection from the same
forecast row, explicit empty-cohort handling, strict physical-pack provenance, and disabled ranking
at immature confidence.

The critic raised potential growth from frozen cohorts. TwinWorks captures summaries once per
processed-shipment batch and suppresses identical content hashes; it does not append on page views or
position refreshes. The full cohort is retained because it is the independent evidence needed to
auditably reproduce a historical score if operational rows later change. Monitor table size during
ACC-01d and normalize source membership only if observed growth warrants it.

Desktop, 390px mobile, light-theme layout, page-level overflow, and WCAG A/AA axe checks passed with
zero violations. The accuracy-history table scrolls locally on narrow screens.
## Verification

- Full regression suite: 114 passed.
- Focused Ruff: passed.
- Static golden forecast: exact.
- Clean Alembic upgrade through `1b2c3d4e5f60`: passed.
- Live database: nine immutable 2026-09-04 program/horizon summaries with frozen cohort JSON.
- Desktop and 390px mobile browser checks: passed; no page-level horizontal overflow.
- WCAG 2 A/AA axe scan: zero violations and zero incomplete checks.
