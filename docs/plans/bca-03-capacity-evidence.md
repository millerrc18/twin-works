# BCA-03 Work-Center Capacity Evidence

## Status

Deferred historical evidence as of 2026-09-02. BCA is not active TwinWorks product scope and these
utilization findings do not authorize further BCA modeling or refresh work.

Read-only IFS evidence pass completed 2026-08-27 for `P3TRI`, `TRI A`, `PRNG`, and `P3NDI`.
No production capacity values were changed. These findings constrain the BCA-03 design.

The BCA-03b software gate was implemented on 2026-09-01. It can now enforce physical pool IDs,
finite calendars, explicit external reserves, immutable shadow epochs, replay, and causal profile
comparison. The four BCA capacity decisions below remain unapproved, so no live physical pool was
created. See `../validation/bca-03b-physical-pool-shadow.md`.

## Sources and Window

- Site: Marion `59`.
- Configuration: `WORK_CENTER_CFV`, `WORK_CENTER_RESOURCE`, and
  `WORK_CENTER_RESOURCE_AVAIL`.
- Actual labor: `GD_SHOP_FLOOR_CLOCKING`, Labor clockings completed from 2026-05-28 through
  2026-08-27. Shift buckets: 1 = 06:00-14:00, 2 = 14:00-22:00, 3 = 22:00-06:00.
- Current demand: released/in-process rows in `SO_OPER_DISPATCH_LIST_CFV`.
- Project identities: `PROJECT_CFV`.

## IFS Configuration Findings

| WC | IFS description | Calendar | Avg capacity | Demonstrated | Resource rows | IFS scheduling |
| --- | --- | --- | ---: | ---: | ---: | --- |
| `P3TRI` | P3 TRIM | MARION 2 | 8.000 | 4.191 | 1 active | Infinite |
| `TRI A` | P3 ASSY TRI | MARION 2 | 8.000 | 24.346 | 1 active | Infinite |
| `PRNG` | P3 RANGE | MARION 3 | 23.983 | 2.071 | 1 active | Infinite |
| `P3NDI` | P3 NDI | MARION 2 | 8.000 | 1.839 | 1 active | Infinite |

Each resource row is operable at 100 percent efficiency with no end date. These rows identify the
resource, but do not establish a finite labor-hour ceiling. The clocking records have no resource
or team assignments, so IFS cannot provide a reliable staffing roster for these WCs.

## Recent Labor Envelope

| WC | Total h | Active weeks | Median active week | P80 active week | Peak week | Shift mix 1/2/3 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `P3TRI` | 744.47 | 14 | 58.76 | 64.55 | 87.72 | 87% / 2% / 11% |
| `TRI A` | 1277.78 | 14 | 96.52 | 127.14 | 146.92 | 65% / 25% / 10% |
| `PRNG` | 244.58 | 12 | 18.28 | 26.84 | 47.47 | 24% / 29% / 47% |
| `P3NDI` | 6.68 | 1 | 6.68 | 6.68 | 6.68 | 0% / 100% / 0% |

These are utilization envelopes, not capacity. P80/peak values are useful validation anchors for a
floor owner, but cannot be written directly into the scheduler without confirming staffing,
equipment concurrency, overtime policy, and untracked-program reservations.

## Shared-Resource Evidence

All four WCs are site-wide physical resources, not BCA-private resources.

- `P3TRI`: BCA recorded 638.80 of 744.47 recent labor hours (85.8 percent). Current released
  demand is 69.8 of 99.7 planned labor hours (70.0 percent). Other consumers include C17 Triband,
  F-16, NGJ, C-130, and repair programs.
- `TRI A`: BCA recorded 1124.27 of 1277.78 recent hours (88.0 percent). Current released demand is
  305.0 of 436.8 hours (69.8 percent). C17 Triband is the largest other consumer.
- `PRNG`: BCA recorded 233.68 of 244.58 recent hours (95.5 percent). Current released demand is
  182.0 of 215.0 hours (84.7 percent). C17 Triband and repairs also use the range.
- `P3NDI`: recent clocking is too sparse to characterize capacity, while current released demand is
  about 498.81 labor hours across many radome programs. BCA is only 37.5 hours (7.5 percent).

## BCA-03 Design Recommendation

Use a normalized physical-capacity-pool model rather than program-local WC budgets.

1. Store one site/WC pool with shift budgets, effective dates, evidence source, confidence, and
   validation owner.
2. Map each program/WC to that pool. Shared programs consume one budget; budgets are never summed
   merely because multiple programs reference the same physical WC.
3. Represent untracked-program demand explicitly as an external reserve, or store a clearly named
   effective capacity available to TwinWorks. Do not silently assume all site capacity is available.
4. Preserve the existing seed-program behavior exactly during migration and prove it with the
   golden forecast.
5. Block onboarding when a production WC has no validated pool. Removing the unknown-WC warning
   must require a real persisted pool, not an acknowledgement of `DEFAULT_SHIFT`.

## Validation Questions Before Initial Values

- `P3TRI`: Is day shift the only normally staffed shift, with nights as overtime? Is 65 h/week a
  sustainable envelope or merely recent demand?
- `TRI A`: How many assemblers can work concurrently, and is the 127 h/week P80 level sustainable?
- `PRNG`: Is the range constrained by equipment occupancy, operator labor, or both? The MARION 3
  calendar and machine-time routing make labor clocking alone unsuitable as the constraint.
- `P3NDI`: What NDI equipment/operator pool is actually available across the many consuming
  programs? Historical BCA clocking is insufficient for any default.

Until these are answered, BCA-03 should implement persistence and blocking behavior but leave all
four BCA pool values unvalidated and prevent BCA onboarding.
