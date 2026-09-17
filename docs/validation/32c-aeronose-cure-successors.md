# #32c Aeronose Cure Successors

## Status

Delivered 2026-09-17 as two separate immutable candidates. The published `RAD:LEGACY` epoch and its
40-hour cure/station parity remain unchanged.

## Candidate Chain

| Epoch | State | Op-775 process | Station | Approval state |
| ---: | --- | --- | --- | --- |
| 11 | `OBSERVE` | 40-hour cure | None | Physical no-station fact accepted |
| 12 | `DRAFT` | 2-hour flashoff + 8-hour cure | None | DRDI approval pending |

The accelerated candidate can enter `OBSERVE` only when its immutable definition contains one or
more DRDI identifiers, an authorized approver, approval timestamp, and effective date. Verbal or
in-process approval cannot satisfy the gate.

## Shadow Comparison

The no-station candidate was compared against the published baseline over persisted current RAD WIP.
Baseline snapshot 30 and candidate snapshot 31 replay exactly. Six units changed:

| Serial | Delta hours |
| --- | ---: |
| 520 | -32.70 |
| 522 | -47.00 |
| 523 | -19.31 |
| 525 | -14.19 |
| 526 | +5.31 |
| 527 | -11.69 |

Negative is earlier. The small adverse movement for 526 is retained because removing an artificial
serialization changes queue ordering; the comparison does not assume every unit must improve.

## Controls

- Candidate routing and cure definitions are frozen inside the epoch.
- The scheduler consumes the selected epoch's frozen routing rather than mutable router constants.
- Candidate compilation rejects resource-registry drift.
- Both baseline and candidate results use schema-v3 replay envelopes.
- The accelerated route remains non-runnable while approval evidence is incomplete.
- No candidate creation or comparison changes publication.

## Verification

- Seven focused cure-successor tests pass.
- Full regression: 133 passed with the existing warning set.
- Focused Ruff: passed.
- Static golden forecast: exact.

## Backup

Pre-successor database backup:
`data/rtg_app_migrated.pre_op775_successors_20260917.bak`

SHA-256:
`469C13313DCAC50546A9F04F5DB93870DDB6C3129EAE357AB64BAF0746CE1F2A`
