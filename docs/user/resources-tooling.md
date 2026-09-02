# Resources and Tooling

TwinWorks models two different constraint types.

## Effort capacity

Labor and machine pools consume hours. Shared programs draw from one physical budget. Gross-site
capacity subtracts an approved external reserve; net-tracked capacity is already reduced.

## Occupancy

Jigs, fixtures, molds, booths, and stations occupy discrete slots. A unit may hold a tool across
multiple operations or cures while consuming little labor. Multi-tool requests acquire every
required slot atomically or wait without taking any.

## Readiness

- `COMPLETE`: approved, current, fully covered, and commitment-ready.
- `PROVISIONAL`: present but internal-only, stale, or under review.
- `MISSING`: required evidence, capacity, calendar, or binding is absent.

The current Aeronose counts are draft inventory facts only. They have no bindings and cannot affect
forecasts. Operation spans will be approved under TOOL-01c.
