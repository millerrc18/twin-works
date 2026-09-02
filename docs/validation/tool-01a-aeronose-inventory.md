# TOOL-01a Aeronose Tooling Inventory

## Status

Initial inventory facts were registered 2026-09-02 as `DRAFT` / `INTERNAL_ONLY`. They are visible
in the Resource Registry and have no operation bindings, so they cannot alter any schedule.

| Pool | Slots | Pool ID | Assumption | Capacity version |
| --- | ---: | ---: | ---: | ---: |
| `AERONOSE_ASSEMBLY_JIG` | 2 | 25 | 25 | 25 |
| `AERONOSE_HOLDING_FIXTURE` | 2 | 26 | 26 | 26 |
| `AERONOSE_TRIM_FIXTURE` | 1 | 27 | 27 | 27 |
| `AERONOSE_SHELL_LAM_MOLD` | 3 | 28 | 28 | 28 |
| `AERONOSE_CORE_FORM_MOLD_SET` | 1 | 29 | 29 | 29 |

All five use `OWNER_CONFIRMED` basis from Ryan Miller's program inventory, retain a 2026-10-02
review date, have no approver, and have zero `OperationResourceBinding` rows.

## Remaining Approval Questions

1. Name the floor/process owner and approver for each tool family.
2. Confirm whether each multi-slot family is fungible or has named/non-interchangeable instances.
3. Confirm whether the core-forming mold set is one atomic set or separable components.
4. Identify maintenance/unavailable dates and normal availability calendar.
5. Define cleanup/changeover and minimum-hold requirements.
6. Approve acquire/release operation boundaries from the frozen Aeronose routing and work
   instructions.
7. Identify any physical sharing with Elevator, Aegis, repair, or other site programs.

Until these are resolved, counts remain inventory facts only.

## Controls

- Seeder: `scripts/seed_aeronose_tooling.py`
- Service: `app/services/tooling_seed.py`
- Seed is idempotent and refuses conflicting resource types.
- Draft versions are displayed but remain readiness `MISSING`.
- No tooling instances or operation bindings were guessed.
- Static golden forecast remains exact after live seeding.
- Full regression suite: 79 passed; focused Ruff checks passed.

## Backup

Pre-seed database backup:
`data/rtg_app_migrated.pre_aeronose_tooling_drafts.bak`

SHA-256: `B2AE370BCCB4936480F2275DF11C9351FAAA39024C59B03B5321C8D0AF581D56`
