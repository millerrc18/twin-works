# Forecast Method

TwinWorks separates physical scheduling from statistical correction.

## Physical floor

The finite-capacity simulation advances all active units through their remaining routing. Units
compete for labor budgets and approved occupancy resources. Cure and dwell steps elapse in calendar
time. Priority and resource rules are deterministic so a frozen snapshot can be replayed exactly.

## Residual correction

The model predicts the residual between completed-unit reality and the physical simulation. It does
not replace the scheduler or predict a ship date directly. Programs remain empirical until enough
forward-scored shipments support a trained correction.

## Dates

- Simulation finish is the physical model result.
- P50 is the central corrected forecast.
- P80 is the conservative planning date.
- Delta is measured against the effective planning basis.

Tooling candidates remain shadow-only until their assumptions and operation spans pass review.
## Accuracy v1.1

Accuracy uses the latest IFS finish clock on a closed terminal Pack & Ship operation and never scores
against RTG targets or contract dates. Administrative close is a fallback only when no qualifying
terminal-operation date exists. For each shipped unit, TwinWorks selects the latest forecast
captured in the 7-13, 14-20, and 21-27 day windows before physical shipment.

Each horizon reports a 0-100 score built from MAE, percentage within seven days, and absolute bias.
Confidence is separate: fewer than five eligible units is `Insufficient`, 5-11 is `Preliminary`,
12-24 is `Developing`, and 25 or more is `Established`. The blended headline is withheld until all
three horizons have at least five eligible units. P80 coverage is a separate calibration measure
with an uncertainty interval; it does not inflate or reduce the accuracy score.

Retrospective backtesting, model-training maturity, and Accuracy v1.1 remain distinct evidence
tracks. They are never summed or blended.
