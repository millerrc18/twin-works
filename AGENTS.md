# AGENTS.md — guidance for AI agents working in this repo

Read this before editing. It captures the architecture, conventions, and the gotchas that
have actually bitten us. For the full human-facing reference see **MASTER.md**.

> **Naming note:** the product is **TwinWorks** (git `twin-works`). The folder remains
> `rtg-tracker-build/`, and RTG remains a domain and compatibility term for Return-to-Green targets,
> plan files, legacy workbook artifacts, and the `RTG_` environment prefix.
---

## HANDOFF (2026-09-02) - read first if you are picking this up

**Current status:** Active product scope is Elevator, Aeronose, and Aegis. SCOPE-01 is complete:
`BCAFIN` is inactive, epoch 10 is `ARCHIVED`, and registry/sync/WIP/simulation/forecast surfaces
exclude it without deleting history. RES-01 retains the generic physical-resource shadow runtime.
The next modeling path is TOOL-01:
generic occupancy leases and Aeronose tooling. Feature #81, the read-only Marion factory map,
PLAT-01a through PLAT-01c, and UI-01a through UI-01c remain complete. The regression suite has
**79 passing tests**; the run still emits existing Python 3.14
`datetime.utcnow()` deprecation warnings from `program_service.py` and `position_state.py`.

**TOOL-01a live inventory:** pools 25-29 record Aeronose assembly jigs (2), holding fixtures (2),
trim fixture (1), shell lamination molds (3), and core-forming mold set (1). All are DRAFT,
INTERNAL_ONLY, unbound, and mathematically inactive. Do not approve or bind them until the questions
in `docs/validation/tool-01a-aeronose-inventory.md` are answered.

**Current git state:** branch `codex/resource-assumption-registry`, tracking the matching origin
branch. Remote: `https://github.com/millerrc18/twin-works.git`. The BCA-03b/generic physical-pool
runtime and three-program tooling plan are currently uncommitted. Preserve the git-ignored live
SQLite database and its backups.

**#81 completed:**
- `program` table and migration `b4e2f7a1`; DB-or-routers source flag; seed-the-3; `create_program`; snapshots; IFS metadata, program ordering, names, thresholds, and pack operations routed through `program_service`.
- IFS routing discovery, unknown-WC acknowledgement gate, and the `/admin/programs` onboarding UI.
- Plant-guarded, transitive shared-WC pooling in `rtg_wrapper.run_pooled(units_by_program, as_of)`.
- Registry-driven simulation profile passes per-program crew, DPAS, shared-WC, and shift-budget metadata into `capacity_engine`. It intentionally corrects the old seed-only `32678` mapping by deriving the actual ELEV/Aegis shared WC `32687`; the seed golden baseline was recaptured for that forecast change.
- Deterministic golden-master coverage: the golden test is scoped to the 3 seed programs and 40 static bootstrap WIP units. It ignores mutable `PositionState` and extra configured programs.
- Synthetic fourth-program coverage in `tests/test_program_onboarding.py`: creates `TEST4` in an
  isolated SQLite DB, verifies Plant 2/WC 221 pooling, confirms a draft forecast, proves the
  ELEV/RAD/AEGIS forecasts do not move, and confirms TEST4 cannot enter the authoritative forecast
  log without a published epoch.
- Registry rebuilds refresh existing references in place, so already-imported services see a newly
  onboarded program immediately. Daily forecast stamping includes only programs with a currently
  valid published epoch.

**Remaining work:**
1. **#32b station calibration:** confirm the one-versus-two Plant 3 Radome electrical-seal station count. The allocator is live with a documented conservative value of one; see `TASKS.md`.
2. **Three-program tooling pivot:** execute SCOPE-01, then RES-01 and TOOL-01 in the order defined
   by `TASKS.md` and `docs/plans/three-program-tooling-roadmap.md`. Do not start BCA capacity,
   external-demand, machine/dwell, or pilot work. Historical BCA facts are retained below only for
   audit and a possible future restart. BCA-01/02 are complete; live revision-3 discovery
   shows A = 69.603 labor / 104.303 machine hours and C = 69.603 / 104.603.
   The BCA-03 evidence pass found `P3TRI`, `TRI A`, `PRNG`, and `P3NDI` are site-shared and
   IFS-infinite; do not derive final budgets from observed clocking. Use the evidence report in
   `docs/plans/bca-03-capacity-evidence.md`. The approved architecture and execution sequence are
   in `docs/superpowers/specs/2026-08-27-resource-assumption-registry-design.md` and
   `docs/superpowers/plans/2026-08-27-resource-assumption-registry-plan.md`. BCA-03a is complete.
   BCA-03b has exact legacy parity plus the physical-pool compiler/scheduler, finite calendar and
   external-reserve gates, immutable OBSERVE successors, exact replay, and causal comparison.
   Do not create live BCA pools. The generic physical-pool software is retained under RES-01; the
   historical acceptance record is `docs/validation/bca-03b-physical-pool-shadow.md`.
   PLAT-01a added append-only model epochs, authorized transition events, append-only publication
   selections, and simulation-snapshot epoch links. ELEV/RAD/AEGIS are published as legacy
   `COMMITMENT_READY` epochs; candidates cannot replace them without explicit publication.
   Pre-migration DB backup: `data/rtg_app_migrated.pre_resource_registry.bak`, SHA-256
   `DC4A711FC988E807E170C70D30EB3E52056A6F38BFBB61B9A3548B7FFC0347DB`. Retain through the
   accepted resource-registry pilot cycle; it remains git-ignored because it contains OAuth state.
   UI-01a separates configured planning basis from lifecycle and suppresses dates/KPIs outside
   commitment-ready publication. PLAT-01b adds schema-valid evidence, immutable review resolution,
   permanent audit export, and exact schema-v3 input/result replay. PLAT-01c created current
   ELEV/RAD/AEGIS `OBSERVE` candidates (IDs 7/8/9) and proved exact parity across 29 static WIP
   units with result hash `c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`.
   The 70-item review queue is intentional debt: 24 missing dates, 24 migrated-evidence
   attestations, and 22 missing drift policies. It keeps candidate readiness provisional and must
   not be dismissed wholesale.
   External-load snapshots are append-only and their source coverage cannot extend past the
   forecast horizon without an explicit approved policy. Live CRP ingestion is deferred.
   The local DB is at migration `fdb4c5d6e7f8`. PLAT-01a backup:
   `data/rtg_app_migrated.pre_model_epochs.bak`, SHA-256
   `1F63D0C88AD53DA0CAF0E0BE2852C68D0D7B656D4734EB52BCCA2FAF97D436FF`.
   PLAT-01b backups: `data/rtg_app_migrated.pre_recertification.bak` SHA-256
   `C5033AB6BB6413256EAE60784B6E6F493269B1F2CDAA30AD3A7DAB8190F23791` and
   `data/rtg_app_migrated.pre_incumbent_shadow.bak` SHA-256
   `FDB68AD4B32019A8EDAD5F2304DE3F722CD6B97CA026BCFB78D139F685B37E93`.
   Pre-external-integrity backup: `data/rtg_app_migrated.pre_external_integrity.bak`, SHA-256
   `D8AE83AC62FE93636BB0024FE41CE5B7E8B1B437F9B5E688E6436ED7A34BB74A`.
   Pre-BCA-layup-quarantine backup: `data/rtg_app_migrated.pre_bca_layup_quarantine.bak`, SHA-256
   `B056287443BCE92A0C31900C1A5710850978BCE0F2589CFCEB46AF3B32309EA4`.
   Historical BCAFIN epoch `BCAFIN:CANDIDATE:ad7afe75ea9f` is `ARCHIVED`; its 73 position rows are
   retained but excluded from active WIP. Its eight WC binding gaps remain historical, and it has
   no published forecasts or forecast-log rows. Immutable metadata carries both revision-3 A/C
   economics.
   BCA layup remains separate and not onboarded. Stream `BCALAY` has 12 active append-only
   quarantines for op-9999-closed/SO-Started conflicts. Use `scripts/audit_bca_layup.py` then
   `scripts/reconcile_bca_layup_quarantine.py`; never include quarantined SOs in TRI L/ATUP demand.
   `app/data/bca_layup_policy.v1.json` blocks activation until TRI L labor capacity, ATUP operator
   capacity, physical autoclave slots/calendar/compatibility/external demand, and P3 QA are approved.
3. **SCOPE-01 BCA park complete:** `BCAFIN` is inactive and archived; its 73 position rows and 12
   `BCALAY` events remain historical. Backup `data/rtg_app_migrated.pre_bca_park.bak`, SHA-256
   `22ADC5E690FA00328D11A0EF241FE67345BF850DEE3BCAB55D906C38F7888FA6`.
4. **#82 Marion virtual factory capacity map:** Phase 1 is implemented at `/factory-map`. Keep it
   display-only: it surfaces WIP and modeled capacity without changing forecast inputs.
   VAMA02/VAMA03 coordinates live in `app/data/marion_floor_map.v1.json`; `P3 QA` stays mobile and
   `PRNG` stays unplaced. Follow-ons #82-1a, #82-4, and #82-5 cover the governed full catalog
   refresh, reviewed physical expansion, and authenticated live acceptance.
5. **Flag-gated cutover:** after 2-4 weeks of clean live runs, remove the routers.py program-constants fallback and `RTG_PROGRAM_SOURCE=routers`. Keep the fallback until then.
**Rules that will bite you if ignored:**
- Run `pytest` after every engine, registry, or pooling change. The golden baseline is 40 static seed WIP units; do not re-capture it after a live sync. Its latest intentional re-capture includes the registry-derived `32687` shared-capacity correction. State any future static bootstrap/router forecast change in the commit.
- Use a throwaway DB for standalone or isolated tests: `RTG_DATABASE_URL=sqlite+aiosqlite:///./data/_tw_x.db`. Never write test data or fake OAuth tokens into `data/rtg_app_migrated.db`.
- Pooling is plant plus shared WC, not a label. Plant is a hard guard; see `rtg_wrapper.pool_groups`.
- Do not rewrite `routers.py`, `capacity_engine.py`, or `schedule_engine.py`; they remain the seed and fallback source of truth during the cutover period.
- Model epochs, lifecycle transitions, publication selections, simulation snapshots, and snapshot
  epoch links are append-only. Use `model_epoch_service`; never update or delete their rows.
- Approved assumptions and capacities change only through successor versions. Review scans are
  idempotent; resolved reviews are immutable. Do not bypass the 70 recorded recertification items.
- Forecast-log snapshots use schema-v3 replay envelopes. Schema-v2 historical snapshots remain
  valid profile evidence but are intentionally reported as non-replayable because their WIP inputs
  and results were never captured.
- Physical labor-pool definitions must go through `define_physical_labor_pool`. A `GROSS_SITE`
  pool requires a separately approved per-shift external reserve; calendars require seven weekday
  factors, explicit exception dates, and a finite coverage end. Physical mode never uses
  `DEFAULT_SHIFT`. Create successor shadows with `create_physical_shadow_epochs`; do not change
  publication while evaluating them.
- Portfolio and workspace routes must keep published and candidate metrics separate. The portfolio
  read model performs one published-program simulation and one capacity aggregation. OBSERVE tabs
  may show WIP, flow, source contract references, resources, assumptions, and history, but never P50,
  P80, target deltas, or behind counts. Program navigation comes from `program_service`, not code.
- Observation quarantine is append-only governance, not an IFS correction mechanism. Never delete
  quarantine history or manually resolve events; rerun the live audit and let reconciliation append
  RESOLVE/REOPEN events. `BCALAY` must remain absent from program configuration while blockers exist.
- Console is cp1252; use `PYTHONIOENCODING=utf-8` for non-ASCII output. Use a fresh port if a local uvicorn process is already listening.

---

## What this is
A manufacturing ship-date forecasting web app (FastAPI) for 3 GD Mission Systems composite
programs — elevator (531335), radome (C48178), Aegis (530349). It fuses a mechanistic
finite-capacity scheduler with an ML "slip" correction and a lever/what-if engine.

## Core principle (never violate)
**sim = physics floor · ML = the slip on top · app = a decision tool.** The ML model predicts
the RESIDUAL (`actual - sim`), never the date directly, so it stays auditable and can be
turned off. Everything is honesty-first: EMPIRICAL vs TRAINED model badges, PRELIMINARY
caveats, Δ measured vs the RTG target the team actually works to.

## Layout
- **Reused engine (repo root, do NOT rewrite):** `capacity_engine.py` (`simulate`),
  `routers.py` (ops/cures/crew/shift constants — source of truth), `schedule_engine.py`,
  `build_tracker.py` (Excel builder — has module-level side effects, see gotcha), `backtest_accuracy.py`.
- **`app/`** — FastAPI. `main.py`, `config.py` (pydantic-settings, `RTG_` env prefix),
  `database.py` (async SQLAlchemy/aiosqlite), `models.py` (**25 tables**), `templating.py`.
  - `app/engines/` — `router_registry.py` (`build_registry()` reads the `program` table via
    program_service, falls back to routers.py; `rebuild()` after add/edit), `rtg_wrapper.py`
    (`run_pooled(units_by_program, as_of)` + `pool_groups`/`shared_wcs` — plant-guarded transitive
    shared-WC pooling), `lever_engine.py` (counterfactuals).
  - `app/data/` — `source.py` (DataSource ABC), `snapshot_source.py`, `live_source.py`
    (OAuth IFS MCP; IFS meta now from program_service), `ifs_mcp_client.py`, `token_store.py`,
    **`ifs_routing.py`** (active-revision selection + operation economics/classification +
    unknown-production-WC gate), `wip_tables.py`
    (bootstrap WIP — SEED for PositionState), `rtg_targets.py`.
  - `app/services/` — `forecast_service`, `matrix_service`, `slot_service`, `lever_service`,
    `slip_service`, `position_state` (mutable WIP layer), `forecast_log_service`, `sync_service`
    (the IFS refresh loop), `accuracy_forward`, `model_history`, `model_units` (admin units panel),
    **`program_service`** (DB-backed program registry: load_specs / seed_from_routers /
    create_program / ifs_meta / program_order / names / threshold).
  - `app/routers/` — `dashboard`, `levers`, `auth`, `admin` (sync buttons + `/admin/programs`
    onboarding: `programs_page` / `programs_discover` / `programs_create`).
  - `app/templates/` (Jinja) incl. `programs.html` + `app/static/charts.js`. Backups in `templates_bak/`.
- **`tests/`** — pytest suite (golden-master forecast + db-vs-routers + pooling). Run after edits.
- **`ml/`** — `wi/` (extractor/validator/wi_service — LLM WI constraint extraction),
  `model/` (features/dataset/registry/trainer/loader — the residual model).
- **JSON data (repo root):** accuracy_results (retrospective backtest), **accuracy_forward**
  (real forward closes — separate on purpose), backtest_timeline, forecast_log (legacy;
  DB `forecast_log` table is now authoritative), rtg_data, rtg_targets, wi_signals, _rad_std.
  **DB:** `data/rtg_app_migrated.db` (the live one — see config).

## Conventions
- **Restyle vs logic:** UI work is restyle-ONLY unless asked — don't change services/engine/
  routes/data or the Jinja context vars. Design system = "calm canvas, loud signal": CSS
  tokens in `base.html` (light+dark), amber = WIP ONLY, mono (`.num`) for numbers only,
  shape-redundant Δ pills (▲/▼/—), no glow/blink. See MASTER.md "Design system".
- **DataSource is the seam:** never query IFS outside `live_source`/`ifs_mcp_client`/`sync_service`.
  Snapshot fallback must always work (app never 500s on a live-query failure).
- **Slots:** the matrix is slot-anchored (RTG delivery slot → assigned serial), reassign is an
  atomic swap. Aegis has no RTG plan → serial-anchored by contract.
- **PositionState is the mutable data layer, NOT wip_tables.** `wip_tables.py` is immutable SEED.
  Once `position_state` is seeded, SnapshotDataSource reads it; syncs upsert it; `reset` re-seeds
  from the module. Never rewrite `wip_tables.py` at runtime. It's read via stdlib sqlite3
  (`position_state.load_state()`, mtime-cached) because the snapshot source is a sync hot path.
- **The refresh loop lives in `sync_service`** (the ONE place). Two entry points, both require
  live OAuth + take a single-run lock (`SyncRun`): `sync_positions` (Button 1 — pull positions,
  upsert PositionState, stamp today's ForecastLog build) and `process_ships_fast`/`_slow`
  (Button 2 — record closes + backfill accuracy fast; rescore/retrain in a BackgroundTask).
  IFS reads run in `asyncio.to_thread` (blocking urllib) and NEVER inside a DB transaction.
- **Forward vs retrospective accuracy are SEPARATE files/counts.** Backtest → `accuracy_results.json`;
  real forward closes → `accuracy_forward.json`. The train gate counts FORWARD ships only
  (`accuracy_forward.forward_counts()`), fed to the registry by `loader.refresh_registry`. Never
  blend them (double-counts + corrupts the gate).
- **ForecastLog stamping is an idempotent daily upsert** keyed `(build_date, serial)`,
  last-write-wins. Slip diff (`slip_service`) compares the two most recent DISTINCT build_dates —
  so multiple same-day refreshes don't corrupt it.
- **Program config lives in the `program` table (via `program_service`), NOT in code.** Iterate
  programs with `program_service.program_order()`, never a hardcoded `("ELEV","RAD","AEGIS")` tuple.
  `router_registry` builds specs from the DB with a routers.py fallback (flag `RTG_PROGRAM_SOURCE`).
  Adding a program = a DB row (via `/admin/programs` or `create_program`), zero code changes.
- **Pooling = same plant + shared WC** (`rtg_wrapper.pool_groups`), computed as connected
  components of the Program↔WorkCenter graph over `shared_wcs()`, guarded by plant. Do NOT
  reintroduce a hardcoded pool list or a "pool_group" label. New programs auto-pool correctly.
- **Onboarding a program blocks on unknown WCs** — a WC with no `routers.WC_SHIFT` budget silently
  falls back to DEFAULT_SHIFT (plausible-wrong dates). `ifs_routing.unknown_wcs()` gates the save;
  the PM must define the budget or acknowledge. Never auto-accept unknown WCs.

## GOTCHAS (these have actually bitten us)
1. **Use a THROWAWAY DB for isolated tests.** Test scripts writing to `data/rtg_app_migrated.db`
   polluted real OAuth tokens (fake `cid123`) and cost a debugging session. Point `RTG_DATABASE_URL`
   at a temp file for any standalone test.
2. **Importing `build_tracker` runs the Excel builder** (module-level `wb.save`). Never import
   it from app code — use `schedule_engine`/`router_registry` instead. (Already fixed in matrix_service.)
3. **IFS MCP is OAuth-only** (`https://ifs-mcp-auth.prod.azure.gd-ms.us/mcp`): auth_code + PKCE,
   NO service-account/client_credentials. Unattended pulls impossible; needs browser login.
   The OAuth callback is a FastAPI route on the APP's own port (`RTG_APP_PORT`), not a separate port.
   MCP transport requires the `initialize` → `notifications/initialized` → `tools/call` handshake.
4. **Head serials ARE in IFS — in `SHOP_ORD_CFV.NOTE_TEXT`** as `S/N nnn` (often zero-padded:
   `S/N 0515`). There is no serial COLUMN, but the note carries it. `sync_service._serials_from_notes`
   parses it (strip leading zeros) + elevator hand from `PART_NO` (…501=LH/…502=RH). This is the
   source of truth — the old wip_tables SHIPPED elevator serials were SO fragments with wrong hands.
   Never guess serials by due-date order (that produced wrong radome data earlier).
   NOTE: this supersedes the earlier "serials not in IFS" assumption — they're in the note.
   Both live rendering and sync must use `app/data/serial_resolver.py`; live rendering falls back to
   the last persisted `PositionState` mapping before bootstrap data. Never label a known S/N with
   its SO number. `slot_service.get_slots` returns current-WIP slots only while retaining completed
   assignment rows as history.
4b. **Ship detection = pack-op clocked OR SO closed, not close-only.** `CLOSE_DATE` lags the
   physical ship by days (a unit packs Friday, the SO closes the next week). `SQL_CLOSED` LEFT
   JOINs the pack-op clock (ELEV 4200 / RAD 790 / AEGIS 380); ship date = pack preferred, else
   close. `SHIP_SINCE=2026-08-01` floors the window so it doesn't pull all history.
5. **Python can't call the IFS/ai-critic MCP** — only the assistant can. Scripts read pre-pulled JSON.
6. **Console is cp1252** on this box — Δ/▲/✓/• chars crash `print`; write to a UTF-8 file or use PYTHONIOENCODING=utf-8.
7. **Kill Excel before rebuilding** the workbook: `powershell Get-Process EXCEL | Stop-Process -Force`, remove `~$` lock.
8. **Model stays EMPIRICAL** until a program hits its threshold of real FORWARD scored ships
   (proven right: at n=8 the trained model loses to empirical on leave-one-out). Thresholds are
   **per-program**: ELEV 25, RAD 25, **AEGIS 12** (Aegis is a ~5-unit program; 25 unreachable).
   Config `n_train_threshold` is a DICT now (+ `n_train_threshold_default`); read it via
   `registry_model.threshold_for(program)` / `trainer._threshold_for(program)` — NOT as a scalar.
9. **`static/charts.js` is browser-cached — bump the `?v=` query** in `forecast.html`/`levers.html`
   when you change it, or the browser serves stale JS (cost a debugging loop). Current tag `v=bullet4`.
10. **Numeric shape coords silently re-type a Plotly categorical axis to linear** (collapses all
    rows onto one line). For per-row markers on a categorical y-axis use a SCATTER trace with the
    category (serial) as y, not `shapes` with numeric y — see `renderForecastBullet`.
11. **The retrospective backtest (`accuracy_results.json`) and forward accuracy
    (`accuracy_forward.json`) must stay separate.** The gate counts forward only. Don't "unify" them.

## Run / test
```
# run the app
RTG_DATA_SOURCE=snapshot ./run.sh        # offline, safe for dev
RTG_DATA_SOURCE=live ./run.sh            # live IFS (browser Connect first)

# regression suite — RUN AFTER EVERY engine/registry/pooling change
RTG_DATA_SOURCE=snapshot .venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m tests.golden capture   # re-baseline ONLY for an intended change

# isolated experiment on a throwaway DB (never touch the real one)
RTG_DATABASE_URL="sqlite+aiosqlite:///./data/_tw_x.db" .venv/Scripts/python.exe -c "..."
```
run.sh sets RTG_APP_PORT to match --port (needed for the OAuth redirect URI). Alembic:
`.venv/Scripts/alembic.exe upgrade head`. Verify: `pytest` green, then walk every page light+dark,
confirm reassign + lever-run + view-toggle + admin sync/programs work, data matches prior state.
On Windows, prefix Δ/✓/● output with `PYTHONIOENCODING=utf-8`. Lingering uvicorn ports are common —
boot on a fresh port if BUSY.
