# TOOL-01a Aeronose Tooling Inventory

## Status

Initial inventory facts were registered 2026-09-02 and reviewed with the program manager on
2026-09-03. They remain `DRAFT` / `INTERNAL_ONLY`, visible in the Resource Registry, and have zero
operation bindings, so they cannot alter any schedule.

Ryan Miller is the current owner and approver. Every listed family is Aeronose-dedicated. The draft
metadata now records the owner decisions and the controlled-WI/IFS review while deliberately
withholding approval until physical spans and component relationships are complete.

| Pool | Slots | Pool ID | Assumption | Capacity version | Family rule |
| --- | ---: | ---: | ---: | ---: | --- |
| `AERONOSE_ASSEMBLY_JIG` | 2 | 25 | 25 | 25 | Fungible; Dup 1 has larger drill-basket pins |
| `AERONOSE_HOLDING_FIXTURE` | 2 | 26 | 26 | 26 | Fungible; separate from paint dollies; identity/use pending |
| `AERONOSE_TRIM_FIXTURE` | 1 | 27 | 27 | 27 | Singleton `3700TF0001-A01` |
| `AERONOSE_SHELL_LAM_MOLD` | 3 | 28 | 28 | 28 | Fungible `3700LM001` family |
| `AERONOSE_CORE_FORM_MOLD_SET` | 1 | 29 | 29 | 29 | Coordinated set: `3700LM0002`, `3700LM0003`, nose mold |

## Resolved Decisions

- All five pools are dedicated to Aeronose; no cross-program consumers are currently identified.
- Assembly jigs, holding fixtures, and shell molds are interchangeable within their families.
- Ryan Miller is the current approver.
- Owner-reported post-release reuse is immediate. This remains a draft assumption where IFS cannot
  isolate physical release from operation clocking.
- One shell mold is provisionally treated as completely unavailable from 2026-09-03 through
  2026-09-25 for tool-shop work on a new core/plug locating template. The shadow restores 3 / 3 at
  local midnight on 2026-09-26 or immediately upon an earlier recorded return.
- Other maintenance exists but has no known production-impacting interval. No dates are fabricated.
- Op 775 is performed on a dolly and is not constrained to a fixed station. Its current one-slot
  rule is retained only in the frozen parity model pending a distinct successor candidate.

## Remaining Binding Questions

1. Confirm the top-assembly jig release after ops 620/625. A second review of ASSY Rev K, its
   source XML, and embedded figures found only the op-630 drill-basket removal, not radome release.
2. Identify the separate holding fixtures, what manufacturing condition they support, and their
   acquire/release steps. Paint-dolly movements are not proxy events.
3. Determine whether the larger Dup-1 drill-basket pins add setup time or compatibility limits.
4. Represent the trim-fixture release inside op 580; full-op clocking includes off-fixture chamfer.
5. Add the separate subring and core-kit component streams before binding their tooling.
6. Reconstruct current shell/core holders from IFS; add actual return timing when confirmed.

The controlled-WI and live IFS findings are recorded in
`docs/validation/tool-01c-aeronose-wi-review.md`.

## Controls

- Seeder/reviewer: `scripts/seed_aeronose_tooling.py`
- Read-only IFS audit: `scripts/audit_aeronose_tooling.py`
- Service: `app/services/tooling_seed.py`
- Seed/review is idempotent and refuses conflicting resource types or counts.
- Draft versions remain readiness `MISSING`.
- No tooling instances or operation bindings were guessed.
- Static golden forecast must remain exact.

## Backups

Pre-seed database backup:
`data/rtg_app_migrated.pre_aeronose_tooling_drafts.bak`

SHA-256: `B2AE370BCCB4936480F2275DF11C9351FAAA39024C59B03B5321C8D0AF581D56`

Pre-review metadata backup:
`data/rtg_app_migrated.pre_tooling_review.bak`

SHA-256: `DFA2FDB3688AC4A8C48C23C429D11C940839EE174A6262D31215437E0FD8B992`
