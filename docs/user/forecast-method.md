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
