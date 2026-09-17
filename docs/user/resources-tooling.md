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
forecasts. The inventory includes two assembly jigs, one wooden blue holding fixture `3700HF0001`,
one trim fixture, three shell molds, one core-forming set, six paint dollies, and nine handling
dollies. Shell/core candidate spans have controlled-WI support, while assembly, holding/dolly,
trim sub-operation, compatibility/serviceability, and component-link questions remain open under
TOOL-01c.

Op 775 remains a 40-hour part cure, but it is performed on a movable dolly rather than at a fixed
electrical-seal station. The one-slot rule remains visible only as frozen parity history until a
governed successor candidate demonstrates and explains its removal.
## Availability Controls

The critic-reviewed tooling control in `docs/plans/tooling-availability-control.md` shows current
available count, future count changes, outage reason,
expected return, shadow impact, and immutable history. Outage and early-return entries affect only a
consuming candidate epoch until that model is explicitly promoted. The first release is pooled and
count-based; it does not require tool serial numbers or schedule preventive maintenance.

Availability editing will be enabled only after TwinWorks binds application identity and roles.
Ryan Miller and configured data administrators will be initial editors; all other users remain
read-only. Published dates are separated from candidate impact in every view.
