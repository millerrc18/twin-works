# BCA-06 Layup and Autoclave Quarantine

**Audit date:** 2026-09-01

**IFS scope:** Marion site `59`, project `521938`, part `3301ED0032-101`

**TwinWorks stream key:** `BCALAY` (not onboarded)

## Result

The layup/autoclave route is a separate manufacturing stream from BCA finishing. Live IFS selected
routing revision `3`, alternative `*`, with 29 open shop orders and 26 routing rows. After correcting
op 2 `Change Notes (NOWB)` to administrative classification, the route contains 19 production
operations, 86.2 included labor hours, and 72.0 included machine hours.

Twelve shop orders are quarantined because `SHOP_ORD_CFV.OBJSTATE` remains `Started` while operation
9999 is status `90` (closed). They are excluded from WIP, cadence, capacity, autoclave demand, and
shared-resource conclusions until a later IFS audit no longer detects the conflict.

| Serial | Shop order | Last clock | Due |
|---:|---:|---:|---:|
| 42 | 1452412 | 2026-05-22 | 2026-06-03 |
| 107 | 1458151 | 2026-07-30 | 2026-03-12 |
| 119 | 1458902 | 2026-08-12 | 2026-08-25 |
| 120 | 1458903 | 2026-08-26 | 2026-03-12 |
| 122 | 1458905 | 2026-08-12 | 2026-03-12 |
| 126 | 1458909 | 2026-08-17 | 2026-03-12 |
| 139 | 1460789 | 2026-08-27 | 2026-09-09 |
| 140 | 1461898 | 2026-08-27 | 2026-09-15 |
| 141 | 1461899 | 2026-08-27 | 2026-09-15 |
| 142 | 1461900 | 2026-08-27 | 2026-09-15 |
| 144 | 1461902 | 2026-08-30 | 2026-09-15 |
| 145 | 1461903 | 2026-08-31 | 2026-09-15 |

The append-only quarantine event stream is local governance only; no IFS rows were modified. A
second reconciliation generated no additional events, proving idempotency.

## Eligible Demand

Seventeen open orders are not quarantined. Fourteen currently have remaining TRI L or ATUP demand:

| Resource | Orders | Labor h | Machine/occupancy h |
|---|---:|---:|---:|
| TRI L | 14 | 921.0 | 756.0 evidence only |
| ATUP | 14 | 51.8 | 84.0 occupancy |

Unfiltered project demand is not suitable for capacity conclusions because it includes the twelve
terminal-state conflicts.

## Resource Semantics

The machine-readable policy is `app/data/bca_layup_policy.v1.json`.

- **TRI L labor:** gross-site shared labor pool using effort hours for ops 1000, 1100, 1200, 1300,
  1400, 1500, 1550, 1600, 1650, and 2100. Routing machine hours are evidence only and are not added
  to labor demand. Staffing and external reserve remain unapproved.
- **ATUP operator:** separate gross-site labor effort of 3.7 hours per op 2000.
- **ATUP autoclave:** discrete occupancy of one slot for six 24/7 hours from op 2000 start through
  completion. Physical slot count, compatible load grouping, maintenance/calendar availability,
  and external demand remain unapproved.
- **P3 QA:** inspection effort remains a mobile resource and requires a separate approved binding.

IFS reports both TRI L and ATUP as infinite-capacity work centers. The displayed average and
demonstrated capacity values are evidence, not approved TwinWorks limits. ATUP has open demand from
at least 15 other projects; TRI L has open demand from two other projects. `DEFAULT_SHIFT` and
program-local budgets are prohibited.

## Onboarding Gate

`BCALAY` remains absent from the program registry. Onboarding is blocked until:

1. every open quarantine event is resolved by corrected IFS source state;
2. TRI L staffing/effective capacity and external reserve are owner-approved;
3. ATUP physical slot count, load compatibility, calendar, and external-load policy are approved;
4. P3 QA route effort has an approved binding; and
5. a fresh audit confirms revision and demand have not drifted.

Reproduce with:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\audit_bca_layup.py
.\.venv\Scripts\python.exe -X utf8 scripts\reconcile_bca_layup_quarantine.py
```
