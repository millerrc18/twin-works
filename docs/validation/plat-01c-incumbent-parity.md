# PLAT-01c Incumbent Shadow Parity

**Run date:** 2026-08-31

**Scope:** ELEV, RAD, AEGIS

**Mode comparison:** published `LEGACY` versus explicit `DB_SHADOW` candidates

**Result:** PASS

## Evidence

- Static bootstrap WIP: 29 units (`ELEV` 17, `RAD` 9, `AEGIS` 3).
- Candidate epochs: ELEV 7, RAD 8, AEGIS 9.
- Candidate lifecycle: `OBSERVE`; no candidate was published.
- Legacy result SHA-256:
  `c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`.
- DB-shadow result SHA-256:
  `c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`.
- Mismatched serials: none.
- Replay: exact for both schema-v3 snapshots using frozen inputs, epoch routes, and scheduler profile.
- External-load gate: immutable source snapshots require an explicit horizon policy; no external
  demand was active in this parity run.
- Published epochs: unchanged ELEV/RAD/AEGIS legacy baselines.

## Readiness Debt

The parity result proves behavioral equivalence. It does not certify the inherited capacity
assumptions. The review queue intentionally remains open and the DB-shadow profile is
`PROVISIONAL`:

| Review type | Count | Required action |
|---|---:|---|
| Missing review date | 24 | Assign a next recertification date. |
| Migrated-evidence attestation | 24 | Named owner verifies the migrated source record. |
| Missing drift policy | 22 | Approve a pool-specific threshold and minimum sample count. |
| **Total** | **70** | Resolve individually through governed successor versions. |

This debt does not block the parity proof or observation-only data collection. It does block
promotion of the candidate resource model to commitment-ready use.

## Reproduce

```powershell
# Read-only verification; rolls back any newly generated records.
.\.venv\Scripts\python.exe -X utf8 scripts\verify_incumbent_shadow.py

# Persist newly required candidates/reviews only after exact parity.
.\.venv\Scripts\python.exe -X utf8 scripts\verify_incumbent_shadow.py --commit
```

The command exits nonzero on any legacy/shadow mismatch or replay mismatch.
