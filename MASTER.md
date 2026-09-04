# TwinWorks - Master Reference

Exhaustive documentation for TwinWorks, the RTG (Return-to-Green) ship-date forecasting web app.
Audience: humans (PM, engineers, reviewers). For AI-agent working rules see **AGENTS.md**.

---

## 1. What it is

A finite-capacity manufacturing **ship-date forecasting + decision tool** for three active GD
Mission Systems composite programs built at Marion. BCA is retained as deferred historical
evidence after SCOPE-01 archival:

| Program | Project | Top assembly | Notes |
|---|---|---|---|
| G500 Elevator | 531335 | 72P5520501-029P01 (LH) / 72P5520502-029P01 (RH) | ships as LH/RH shipsets |
| Aeronose Radome | C48178 | 3700ED0001-101 | |
| Aegis Reflector | 530349 | 00999000563 | DPAS-rated; **no RTG plan** (contract-anchored) |
| BCA Triband Finishing | 521938 | 3301ED0031-101A / -101C | deferred; inactive with archived candidate history |

It replaces/augments the Excel "RTG Operation Tracker" with a live web app that:
- forecasts each in-process unit's ship date from a finite-capacity shop simulation,
- corrects the forecast with a measured "slip" (ML residual) so it reflects reality, not the happy path,
- shows **where to act** (bottleneck + what-if capacity levers) to hold dates / increase rate,
- tracks its own **forecast accuracy** so it's credible before going in front of leadership.

### Guiding principle
**sim = physics floor · ML = the slip on top · levers = where to act.**
The mechanistic sim gives the best-case (uninterrupted-execution) date. ML predicts the
*residual* (`actual − sim`) — never the date directly — so the correction is auditable and
can be switched off. Honesty is a feature: model-status badges (EMPIRICAL/TRAINED),
PRELIMINARY caveats, and Δ measured against the **RTG target** the team actually works to
(not just the IFS contract date).

---

## 2. Tech stack
- **Python 3.14**, **FastAPI** + **uvicorn**.
- **SQLAlchemy 2.0 async** over **aiosqlite**; **Alembic** migrations.
- **Jinja2** templates + **HTMX** (partial posts) + **Alpine.js** + **Tailwind (CDN)** + **Plotly.js**.
- **scikit-learn** (quantile regressors), **cryptography** (Fernet token encryption),
  **httpx**/urllib (IFS MCP OAuth + JSON-RPC), **openpyxl** (RTG Excel extraction).
- No build step (Tailwind + fonts via CDN, with system fallbacks).

---

## 3. Architecture & data flow

```
                 ┌─────────────── DataSource (ABC) ───────────────┐
IFS (Azure OAuth MCP) ──► LiveMcpDataSource ─┐                     │
                                             ├─► services ─► routers ─► Jinja templates ─► browser
bootstrap JSON/tables ──► SnapshotDataSource ┘        │
                                                      ├─ forecast_service ─► rtg_wrapper ─► capacity_engine.simulate()
                                                      │        └─► ml.model.registry (residual: EMPIRICAL bias | TRAINED quantile)
                                                      ├─ matrix_service (slot-anchored grid)
                                                      ├─ lever_service ─► lever_engine (counterfactual re-sim)
                                                      └─ slot_service (RTG delivery slots ↔ serial, DB-persisted)
```

- **Data in** comes through one seam, `DataSource`, so IFS-live vs offline-snapshot is a
  swap. Live failures fall back to snapshot (the app never 500s on a bad query).
- **The sim** (`capacity_engine.simulate`) is the authoritative forecast; the app calls it
  via `rtg_wrapper.run_pooled` (elevator+Aegis pooled on shared paint/ovens, radome separate).
- **The ML layer** adds a residual to the sim finish → P50 (de-biased) + P80 (conservative).
- **Persisted state** lives in SQLite (`data/rtg_app_migrated.db`); reference/computed data
  lives in root JSON files.

---

## 4. Module-by-module reference

### 4.1 Reused engine (repo root — pre-existing, imported, not rewritten)
- **`capacity_engine.py`** — `simulate(units, ops_map, cures_map, as_of, profile=None)`: day/shift-stepped
  finite-capacity scheduler. Units compete for per-(program,WC,shift) labor-hour budgets;
  cures run 24/7 wall-clock; discrete cure-station slots constrain validated booth/seal processes; DPAS-behind units jump shared capacity; crew factor divides
  labor on swarm ops. Returns `{serial: {finish, op_dt{opno:dt}, cure_dt{label:dt}}}`.
- **`routers.py`** — the constants source of truth: `ELEVATOR_OPS/RADOME_OPS/AEGIS_OPS`
  (op tuple: opno,desc,wc,hr,ms), `*_CURES` (after_op,label,dwell_hr,note), `*_MILESTONES`,
  `CREW_BY_OP`, `PARALLEL_CURE_GATES`, `CURE_STATION_CAPACITIES`, `CURE_STATION_RULES`, `DPAS_PROGRAMS`, `SHARED_WC`, `WC_SHIFT`, and helpers
  `crew()`, `wc_shift_budget()`, `elevator_weekend_factor()`.
- **`schedule_engine.py`** — `forward_schedule()` (single-unit projection, no contention) +
  `add_labor_hours()`. Used for the "Earliest possible" column (side-effect-free).
- **`build_tracker.py`** — the original Excel workbook builder. **Has module-level side
  effects** (writes the .xlsx on import) — never import from app code.
- **`backtest_accuracy.py`** — retrospective backtest → `accuracy_results.json`. Reconstructs
  each of 8 recent-production closes' position at 7/14/21-day snapshots, runs the sim forward,
  scores vs actual pack/close. Headline: engine runs ~7d optimistic (MAE 7.1d, n=8, PRELIMINARY).

### 4.2 `app/` core
- **`main.py`** — FastAPI app + lifespan (create tables, load active trained models via
  `ml.model.loader.refresh_registry`), mounts static, includes routers, `/health`.
- **`config.py`** — pydantic-settings, env prefix `RTG_`: `data_source` (snapshot|live),
  `ifs_mcp_url`, `llm_provider`, `wis_dir`, `data_dir`, `database_url`
  (default → `data/rtg_app_migrated.db`), `app_port` (OAuth redirect must match),
  **`n_train_threshold`** (per-program DICT `{ELEV:25, RAD:25, AEGIS:12}`) +
  **`n_train_threshold_default`** (25 fallback), **`program_source`** (`db`|`routers`, default db —
  the add-program migration rollback flag), `use_cleaned_dwell`, `token_encryption_key`.
- **`database.py`** — async engine, `async_session`, `get_db` dependency, `Base`.
- **`models.py`** — core forecast/program tables plus the normalized Resource and Assumption
  Registry. Resource tables cover pools/instances, capacity versions, operation bindings,
  assumptions/reviews, external-load snapshots/rows, immutable simulation snapshots, and forecast
  constraint events. Model-epoch tables hold immutable definitions, append-only lifecycle decisions,
  append-only publication selections, and per-simulation epoch links.
  `forecast_log.simulation_snapshot_id` records the resource and epoch basis for a build.
  Existing core tables include `forecast_log` (per-build forecast + backfilled actual/error),
  `ml_training_row` (features + residual), `model_version` (trained blobs, audit trail),
  `wi_constraint` (LLM-extracted WI cures/gates), `oauth_token` (Fernet-encrypted),
  `slot_assignment` (RTG slot ↔ serial), `position_state` (mutable WIP/shipped layer,
  materialized from wip_tables then updated by IFS syncs; one row per SO, `closed`≠None = shipped),
  `model_history` (append-only per-sync model-state trend for the admin chart),
  `sync_run` (single-run lock + status/audit for each sync), **`program`** (config-driven program
  registry — code/name/plant/project/parts/pack-ship-floor ops/milestones/ceilings/ops/cures/
  crew/dpas/threshold/hand-split, all JSON where structural; the DB replacement for hardcoded
  routers.py/PROG_IFS/PACK_OP).
- **`templating.py`** — Jinja env + filters (`fmt_date`, `delta_color`).

### 4.3 `app/engines/`
- **`router_registry.py`** — builds a `ProgramRegistry` of `ProgramSpec`s (per program:
  ops/cures/milestones/ceilings/pack_op/ship_op/floor_op + `cure_floor_hours`, `milestone_of`).
  `build_registry()` prefers DB-defined programs (via `program_service.load_specs`) and falls back
  to `routers.py` when the `program` table is empty or `RTG_PROGRAM_SOURCE=routers`. `rebuild()`
  re-reads after an add/edit. routers.py is the seed source of truth + fallback.
- **`rtg_wrapper.py`** — `run_sim` + `run_pooled(units_by_program: dict, as_of)`. **Pooling is
  data-driven**: `pool_groups()` = connected components of the Program↔WorkCenter graph over
  `shared_wcs()` (WCs in ≥2 active programs), **guarded by plant** (`_plants`). ELEV+AEGIS pool
  (Plant 2, share paint WC221/32687); RAD is separate (Plant 3). Site facts: WC names are globally
  unique (a shared WC = same physical resource) AND plant is a hard boundary (a mis-entered WC
  can't pool across plants). A new program auto-pools iff same plant + shared WC.
  `_simulation_profile()` passes each active program's crew overrides, DPAS flag, shared WCs, and legacy shift budgets into `capacity_engine.simulate`; this intentionally activates the actual shared QA WC `32687` for ELEV and AEGIS instead of the old seed-only `32678` assumption.
- **`lever_engine.py`** — counterfactual driver: `run_lever` (re-sim with modified WC
  budgets/crew/priority, diff finishes), `bottleneck_load` (per-WC weekly demand vs
  available, util %), `back_solve` (tactical: binary-search capacity to hold a contract date;
  gated on TRAINED). Applies overrides by temporarily patching routers globals in a context manager.

### 4.4 `app/data/`
- **`source.py`** — `DataSource` ABC + `UnitRecord` / `ShippedRecord` dataclasses.
- **`snapshot_source.py`** — offline source. Reads the **`position_state` DB table when
  populated** (via `position_state.load_state()`), else falls back to the `wip_tables` module
  baseline. `closed`≠None → shipped; open → WIP. `as_of` advances to the latest synced clock.
- **`live_source.py`** — `LiveMcpDataSource` (auditable SQL templates → IFS MCP), + the
  `get_data_source(kind, tokens)` factory. Serial labels overlaid from `wip_tables` (not in
  IFS). Graceful fallback to snapshot on any live-query error. The SQL templates (`SQL_WIP`,
  `SQL_POSITION`, `SQL_LASTCLK`) are reused by `sync_service` for the refresh loop. IFS metadata
  (project/parts) now comes from `program_service.ifs_meta()` so new programs are picked up.
- **`ifs_routing.py`** — revision-aware add-program discovery. It uses active `SHOP_ORD_CFV`
  revision counts to select one manufacturing `ROUTING_OPERATION_CFV` revision, then retains labor
  and machine setup/run, crew, runtime/parallel flags, and reference-order status. Administrative,
  waiting, and terminal rows default excluded; only included production WCs reach `unknown_wcs()`.
- **`ifs_mcp_client.py`** — OAuth client: dynamic registration, PKCE S256 auth-code flow,
  localhost callback, token refresh, MCP Streamable-HTTP handshake
  (`initialize`→`notifications/initialized`→`tools/call execute_query`).
- **`token_store.py`** — Fernet-encrypted save/load of OAuth tokens (`oauth_token` table).
- **`wip_tables.py`** — bootstrap WIP data extracted from build_tracker: ELEV/RAD/AEGIS/SHIPPED
  tables, STATUS_MAXCLOSED, LAST_CLOCK, `true_maxop`, `is_stalled`, `units_for`. **Now the
  immutable SEED for `position_state`**, not read directly once seeded. **Radome SN↔SO corrected
  2026-08-21 from DPM/statusline** (old due-date-order guess was wrong).
- **`rtg_targets.py`** — loads `rtg_targets.json` (per-milestone RTG dates from the GAC RTG
  workbook); `rtg_ship`, `rtg_milestone`, `has_rtg`. Aegis has no RTG plan.

### 4.5 `app/services/`
- **`forecast_service.py`** — orchestrates DataSource → pooled sim → ML residual → P50/P80 +
  Δ vs RTG target (contract fallback) + model badge. `forecast_program`, `program_summary`.
- **`matrix_service.py`** — builds the slot-anchored matrix: columns = RTG slots grouped
  LH/RH/unassigned (Aegis serial-anchored by contract), header metric rows, op/cure/gate
  grid with cell states (done/wip/upcoming/cure/gate/blank), `first_in_group` separators.
  Uses `schedule_engine` for "Earliest" (no build_tracker import).
- **`slot_service.py`** — RTG delivery slots (fixed target + hand) ↔ assigned serial;
  `default_slots` (only currently-tracked WIP), `seed_slots`, `get_slots`, `reassign`
  (atomic swap: assigning a serial vacates its prior slot).
- **`lever_service.py`** — wraps lever_engine for the web layer; PRESETS (paint/assy/etc.
  capacity what-ifs), `get_bottlenecks`, `run_preset`, `back_solve_program`.
- **`slip_service.py`** — week-over-week slip per serial (latest p50 − prior-build p50), read
  from the `forecast_log` DB table (two most recent DISTINCT build_dates). Drives the matrix
  ↑/↓ slip arrows. Empty until ≥2 builds exist.
- **`position_state.py`** — the mutable WIP layer. `seed_from_baseline` (copy wip_tables in once),
  `upsert` (None-safe per-field), `reset` (re-seed), `load_state` (sync stdlib-sqlite3 read,
  mtime-cached — used by SnapshotDataSource), `invalidate_cache`.
- **`forecast_log_service.py`** — `stamp_build` (idempotent daily upsert of sim/p50/p80 per live
  unit, keyed build_date+serial), `backfill_close` (set actual_close + error_days on a serial's
  prior rows when it ships), `seed_from_json_once` (import the legacy forecast_log.json build).
- **`sync_service.py`** — **the IFS refresh loop** (see §5.1). `sync_positions` (Button 1),
  `preview_ships` / `process_ships_fast` / `process_ships_slow` (Button 2), `current_run`.
  Single-run lock via `sync_run`; IFS reads in `asyncio.to_thread`, never inside a DB tx.
- **`accuracy_forward.py`** — model-maturity counts using one earliest valid pre-pack forecast per
  program/shop order; same-day/post-pack and close-only records are excluded. Kept separate from
  fixed-horizon scoring and the retrospective backtest.
- **`accuracy_score.py`** — Accuracy v1.0 fixed 7/14/21-day cohorts, transparent 0-100 score,
  independent confidence, P80 Wilson coverage, headline gating, immutable daily summaries, and
  frozen cohort provenance.
- **`model_history.py`** — `append_all` (write one `model_history` row per program each sync:
  mode/n/threshold/bias/mae), `history` (read for the admin trend chart).
- **`model_units.py`** — `backtest_units()` / `forward_units()`: which program·SN·SO feed each
  track (retrospective backtest vs real forward closes), for the admin "Units in the model" panel.
  Resolves clean serials via SO (guards against SO-fragment placeholders).
- **`program_service.py`** — the DB-backed program config source (see §5.2). Sync cached
  `load_specs()` (DB row or {} → routers fallback), `program_order`/`names`/`name`/`ifs_meta`/
  `threshold`, `seed_from_routers` (one-time copy of the 3), `create_program` (validated write +
  snapshot export + registry rebuild), `invalidate_cache`. Snapshots export to `program_snapshots/`.
- **`resource_registry.py` / `resource_profile.py` / `resource_explain.py`** — immutable resource
  and assumption governance, effective-dated capacity validation, canonical profile/snapshot
  compilation, legacy parity seeding, exact schema-v3 replay, readiness aggregation, Resource
  Registry rows, and unit Why explanations. Resource mode defaults to `legacy`; DB shadow does not
  change published dates.
- **`assumption_evidence.py` / `assumption_drift.py`** — versioned evidence validation, expiry/
  drift/review-debt detection, race-safe review creation, successor-based recertification, and the
  permanent append-only audit export.
- **`model_epoch_service.py`** - creates immutable program model epochs, enforces the authorized
  lifecycle graph, resolves the currently published epoch, records publish/rollback selections, and
  bootstraps ELEV/RAD/AEGIS as commitment-ready legacy epochs. It also creates incumbent parity
  candidates, rejects live resource mappings that drift from their frozen definitions, and runs
  exact legacy-versus-shadow acceptance. Candidate epochs are runnable only when explicitly
  selected and never replace published output implicitly.

### 4.5b Serial resolution + ship detection (IFS truth)
- **Head serials live in `SHOP_ORD_CFV.NOTE_TEXT`** as `S/N nnn` (often zero-padded, e.g.
  `S/N 0515`). There is NO serial column in IFS. `sync_service._serials_from_notes` parses the
  note (strips leading zeros) + derives elevator hand from `PART_NO` (…501=LH, …502=RH). Source of
  truth — the old wip_tables SHIPPED elevator serials were SO fragments with wrong hands (fixed 8/24).
  `app/data/serial_resolver.py` is the shared parser for direct live reads and sync. Resolution order
  is live NOTE_TEXT, last persisted PositionState mapping, then curated bootstrap mapping. Current-
  WIP slot queries hide completed slots without deleting their assignment history.
- **Ship detection is pack-op-driven, not close-only.** A unit is "shipped" when its pack op
  (ELEV 4200 / RAD 790 / AEGIS 380) is clocked OR the SO is closed. `CLOSE_DATE` lags physical
  ship by days (S/N 0515 packed 8/21, SO still `Started`), so `SQL_CLOSED` LEFT JOINs the pack-op
  clock and `ship` = pack date preferred, else close. `SHIP_SINCE = 2026-08-01` floors the window.

### 4.6 `ml/`
- **`wi/extractor.py`** — `extract_docx_text` (proven), model-agnostic `LLMWIExtractor`
  (injectable LLM call — Claude now, GPT later) + `CachedWIExtractor` (offline), complexity
  features. LLM does structured EXTRACTION ONLY, never prediction.
- **`wi/validator.py`** — matches extracted cures vs router cures; IFS-sourced oven cures set
  aside (not WI-extractable). The gate that keeps extraction from silently diverging.
- **`wi/wi_service.py`** — orchestrates extract→validate→persist (`wi_constraint`);
  `get_complexity_features`. `PROGRAM_WIS` maps program→cache+source docs for ALL THREE programs:
  RAD (ASSY+LAM), ELEV (`ELEV_4401.json`, 11 cures @100% router match), AEGIS
  (`AEGIS_00999000563.json`, 4 WI cures + 3 IFS-autoclave set aside). Caches live in
  `wis/extractions/`. WI constraints only appear after clicking Ingest WI (writes wi_constraint rows).
- **`model/features.py`** — `FeatureBuilder`: crew-per-op, cleaned-dwell (span − WI cure floor
  − rework noise), WI complexity, milestone phase, sharedwc_queue (NaN until vetted).
- **`model/dataset.py`** — parameterized `maxop_at`/`concurrent_pool`; builds `ml_training_row`
  from the 8 shipped units (features + residual).
- **`model/registry.py`** — the threshold gate: EMPIRICAL (bias from accuracy_results.json)
  when n<threshold, TRAINED (quantile P50/P80) above. **`threshold_for(program)`** does the
  per-program lookup (ELEV/RAD 25, AEGIS 12). `predict`, `apply`.
- **`model/trainer.py`** — fits sklearn QuantileRegressor (α=.5/.8) per program above its
  `_threshold_for(program)` → `model_version`. Offline/admin-triggered only.
- **`model/loader.py`** — loads active trained models into the registry at startup / after
  retrain. **Scored counts fed to the gate come from `accuracy_forward.forward_counts()`**
  (real forward ships only), NOT the ml_training_row count — keeps the EMPIRICAL→TRAINED flip
  honest.

### 4.7 Frontend (`app/templates/`, `app/static/`)
- **`base.html`** — shared shell: sidebar + command bar, CSS design tokens (light+dark),
  Inter+JetBrains-Mono fonts (with fallbacks), theme toggle (localStorage), `.num` tabular
  class, focus rings, `@media print`. All pages extend it.
- **`dashboard.html`** — landing: KPI strip + program cards.
- **`matrix.html`** — the hero: slot-anchored ops×units grid (see §6).
- **`forecast.html`** — summary view (Plotly **bullet/range chart** + P50/P80 table).
- **`levers.html`** — bottleneck load + what-if scenario runner.
- **`admin.html`** (`/admin/model-status`) — model/WI status, ingest/rebuild/retrain buttons, the
  IFS refresh loop (Refresh positions / Process new ships w/ preview + status poll / seed / reset),
  the model-history table + bias-trend chart, the "Units in the model" panel, and a **"+ Manage /
  add programs"** link to programs.html. Alpine `syncPanel()` drives the sync UX.
- **`programs.html`** (`/admin/programs`) — add-program onboarding: existing-programs table +
  identity, revision selection, all/included labor and machine totals, operation inclusion/class,
  reference status, editable economics/crew/phase, unknown-production-WC gate, pooling preview,
  and save. Alpine `addProgram()`. NOTE: this is a SEPARATE page from the
  main admin page — the main admin page is unchanged.
- **`partials/`** — `view_toggle.html` (Matrix/Summary), `lever_result.html` (HTMX fragment).
- **`static/charts.js`** — theme-aware Plotly: **`renderForecastBullet`** (summary bullet/range,
  replaced the old scatter timeline), `renderBottleneckBar`, **`renderBiasTrend`** (admin
  model-history). Bump the `?v=` cache tag in templates when editing (current `v=bullet4`).
- **`templates_bak/`**, `charts.js.bak` — pre-redesign backups (rollback).

---

## 5. Data sources & the DataSource seam
- **Snapshot (default, offline):** WIP/positions/dates from `wip_tables` + JSON. Instant, safe.
- **Live (IFS MCP over Azure OAuth):** `LiveMcpDataSource` pulls SO-side truth (positions via
  `OPER_STATUS_CODE_DB`, due dates, closes) live; serial labels overlaid from `wip_tables`
  (head serials aren't serialized in IFS). Requires a browser "Connect IFS" login
  (auth-code + PKCE; no unattended path). Falls back to snapshot on any failure.

### 5.1 The refresh loop (PM self-service — how data is refined after ships)
The PM refreshes the app himself from `/admin/model-status`; he no longer asks the assistant to
hand-edit data. Everything routes through `sync_service` (the one place), requires a live OAuth
connection, and takes a single-run lock (`sync_run`). `wip_tables.py` stays immutable; the mutable
layer is the `position_state` table (seeded from the baseline, then upserted by syncs; `reset`
reverts).

**Button 1 — Refresh positions** (`POST /admin/sync-positions`, daily): pulls current op position
+ last-clock + due for every live WIP unit (reusing `live_source`'s `SQL_WIP/POSITION/LASTCLK`),
upserts `position_state`, and stamps today's `forecast_log` build (idempotent). Returns a diff
(units moved op A→B, newly-stalled, unknown-serial SOs). Stamping a daily build is also what makes
the matrix's week-over-week slip arrows work (they need ≥2 distinct build_dates). Does NOT retrain.

**Button 2 — Process new ships** (`/admin/process-ships`, on close): a preview→confirm, fast→slow
flow. **Preview** (`GET .../preview`, read-only) reports newly-closed SOs + which programs would
cross their train gate. **Fast** (synchronous) records each new close into `position_state`
(`closed`+pack → drops from WIP into shipped) and backfills its `forecast_log` accuracy — instant
feedback. **Slow** (FastAPI BackgroundTask, polled via `GET /admin/sync-status`) recomputes
`accuracy_forward.json`, rebuilds training rows, retrains any program at/over its threshold,
reloads the registry, and appends a `model_history` point. Partial-failure safe: each stage is
idempotent and the `sync_run` row records the failed stage.

**Model history / observability**: every sync appends a `model_history` row per program
(mode/n/threshold/bias/mae). The admin page renders a history table + a **bias-over-time trend
line** (`renderBiasTrend`) so the PM watches bias converge toward 0 and sees the EMPIRICAL→TRAINED
flip. `seed baseline` / `reset to baseline` links manage the `position_state` layer.

### 5.2 Config-driven program registry + add-program onboarding (feature #81)
A program was previously hardcoded across router data, program metadata, pack operations, thresholds,
and pooling callers. The `program` table and `program_service` now hold the configurable program
shape, while `routers.py` remains the migration seed and rollback source.
- **Source flip:** `RTG_PROGRAM_SOURCE=db` (default) reads active `program` rows; `=routers` forces
the hardcoded fallback. Keep this rollback lever through the live stabilization period.
- **Seed and registry:** `seed_from_routers` copies ELEV, RAD, and AEGIS once. `router_registry.rebuild()`
refreshes the existing registry object in place, so imported consumers see a newly created program
without a process restart.
- **Pooling:** `rtg_wrapper.pool_groups()` derives connected components from same-plant shared WCs.
New programs participate as soon as their DB routing is saved.
- **Onboarding UI:** `/admin/programs` accepts identity and IFS part data, discovers
`ROUTING_OPERATION_CFV`, exposes an editable operations grid, blocks unknown WCs until acknowledged,
shows a pooling preview, saves the program row, exports a snapshot, and rebuilds the registry.
- **Safety gate complete:** `tests/test_program_onboarding.py` creates `TEST4` in an isolated SQLite
DB, verifies Plant 2/WC 221 pooling and draft forecasting, and confirms seed-program forecasts do
not drift. Under PLAT-01a, new programs receive a DRAFT candidate epoch and are excluded from the
authoritative `ForecastLog.stamp_build` path until explicitly published.
- **Remaining:** SCOPE-01 parks BCA at registry and data ingress while preserving immutable history.
  RES-01 retains the generic physical-resource runtime. TOOL-01 then adds deterministic occupancy
  leases and Aeronose tooling in shadow. See `docs/plans/three-program-tooling-roadmap.md`.
- **Spatial capacity view (#82):** `/factory-map` is the delivered visual-only Marion capacity and
  work-center layer. It consumes forecast and bottleneck telemetry through one pooled simulation
  per request and never alters simulation inputs. See the as-built section below and `TASKS.md`.

### 5.3 Governed lifecycle, planning basis, and shadow integrity (PLAT-01a through PLAT-01c)
Program maturity and publication are append-only audit streams rather than mutable flags.
`ModelEpoch` stores the immutable model definition and lineage. `ModelEpochTransition` records every
authorized state change through `DRAFT`, `OBSERVE`, `PROVISIONAL`, `COMMITMENT_READY`, `PAUSED`, and
terminal states. `ProgramEpochActivation` selects which commitment-ready epoch may publish; its
authorization points to the exact transition that made the epoch ready.

The latest publication becomes ineffective if its epoch later leaves `COMMITMENT_READY`, and it does
not become active again without a new publication event. Every schema-v2 `SimulationSnapshot`
materializes the selected epoch definitions and has queryable `SimulationSnapshotEpoch` links.
Database triggers prevent direct edits/deletes and reject illegal transitions or publications.
ELEV, RAD, and AEGIS retain `*:LEGACY` as their published production epochs. Explicit candidate
selection is available for shadow runs; default runs continue resolving only published epochs.
Every app and Alembic SQLite connection verifies foreign-key and recursive-trigger pragmas. App
startup also audits the complete governance-trigger inventory and fails before serving traffic if a
required protection is missing. A snapshot records the selected epochs observed for that run; it is
not a global lock preventing later publication decisions.

Planning basis is independent from lifecycle. `PLAN_SLOTS`, `CONTRACT_DATES`, and `NONE` describe
the intended comparison target; `basis_effective` becomes true only for a published
`COMMITMENT_READY` epoch. ELEV/RAD retain RTG slots and AEGIS uses contract dates. The deferred BCA
configuration retains historical contract intent without active forecasts or delivery KPIs. Forecast
DTOs and logs retain contract, plan, and effective comparison targets separately. There is no
plan-to-contract fallback.

Approved assumptions carry canonical schema-v1 evidence. Expiry, missing review dates, migrated
evidence, missing drift policies, sparse evidence, and threshold drift create idempotent review
items. Reviews do not mutate an active value. Recertification or replacement creates successor
assumption and capacity versions, then permanently resolves the review. Resolved reviews and all
historical evidence are protected by ORM guards and SQLite triggers. The audit export is available
at `/admin/resources/audit.json`; retention policy is permanent append-only.

External-load snapshots and rows are also append-only. Each snapshot declares its coverage window
and one of `BLOCK`, `HOLD_LAST_COMPLETE_WEEK`, or `TRAILING_MEAN`. A run past source coverage is
incomplete under `BLOCK`; extrapolation requires an approved, commitment-ready policy assumption.
Live CRP capture and tracked-demand de-duplication are deferred until an active three-program
resource case requires them.

RES-01 retains the physical allocation mode developed during BCA-03b. Each labor operation resolves
to a stable pool ID, so differently named work centers can consume one physical budget. Gross-site
capacity subtracts an explicitly approved per-shift reserve; the raw deficit remains visible when
reserve exceeds capacity. Physical calendars include all seven weekday factors, explicit exception
dates, and a finite coverage end. Missing bindings, budgets, calendars, or reserve policy fail
closed and never consult `DEFAULT_SHIFT`. `define_physical_labor_pool` validates the complete owner
input packet before creating immutable assumptions/capacity and superseding covered effort
bindings. `create_physical_shadow_epochs` freezes that registry state in OBSERVE without changing
publication. `resource_shadow.compare_resource_profiles` reports per-unit date movement and the
causal pool waits/assumption IDs. No live BCA capacity values were created. The BCA validation note
is retained as historical evidence in `docs/validation/bca-03b-physical-pool-shadow.md`.

### 5.3a Three-program tooling pivot

The 2026-09-02 product decision limits active scope to Elevator, Aeronose, and Aegis. SCOPE-01 now
enforces `Program.active` at registry loading, sync/data ingress, the WIP state matrix, pooled
simulation, and forecast logging. BCA is inactive and archived; its immutable evidence remains.

TOOL-01 makes Aeronose the first tooling pilot. Known counts are two assembly jigs, two holding
fixtures, one trim fixture, three shell lamination molds, and one core-forming mold set. Ryan Miller
is the current owner/approver; all are Aeronose-dedicated, and the multi-slot families are fungible.
Counts and those owner decisions remain draft facts only. The 2026-09-03 WI/IFS review found that
subring and core tooling belong to separate component routes, trim releases inside op 580, the shell
mold is held from op 50 through demold at op 570 start, and the top-assembly jig release remains
unresolved. It also confirmed op 775 is a dolly-based 40-hour part cure with no fixed station; the
legacy one-slot rule awaits removal in a successor candidate. Schedule effects still require
approved route links, calendars, release events, WIP assignments, and unavailable intervals. The
generic allocator uses atomic acquisition and the deterministic queue `(ready_time, DPAS-behind
priority, commit, program, serial, pool)`. Deadlock aborts the candidate run and opens a blocking
review. Published and candidate UI/read-model contexts must remain separate. Full sequencing and
pilot criteria are in `docs/plans/three-program-tooling-roadmap.md`; evidence is in
`docs/validation/tool-01c-aeronose-wi-review.md`. TOOL-01c1 adds the authenticated, append-only,
count-based availability control defined in `docs/plans/tooling-availability-control.md`. It stores
outage quantities, compiles aggregate pooled reductions, creates only shadow successors, and defers
tool serials/PM scheduling. Open floor questions remain in
`docs/validation/tool-01c-open-floor-questions.md`. AVAIL-01 is implemented through migration
`0a1b2c3d4e5f` and `resource_availability.py`: outage lifecycles, pooled unavailable-quantity
folding, SQLite concurrency/append-only guards, startup integrity, and audit export are complete.
The live event table is empty; AVAIL-02 identity/authorization is the next gate.

Forecast stamps point to schema-v3 simulation snapshots containing the complete schema-v2 profile,
frozen WIP inputs, epoch routing definitions, canonical expected results, engine/serializer version,
and SHA-256 hashes. Replay does not consult the current program/resource registry. Older schema-v2
snapshots remain integrity-verifiable but cannot claim result replay because their WIP inputs were
not stored.

PLAT-01c created one current `OBSERVE` DB-shadow candidate for each incumbent and archived replaced
parity definitions. The 2026-08-31 29-unit run was exact with result hash
`c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`; published legacy epochs were
unchanged. Candidate compilation fails when the live one-to-one mapping differs from its immutable
definition. The 70 inherited review items keep shadow readiness provisional until owners recertify
them. See `docs/validation/plat-01c-incumbent-parity.md`.

### 5.4 Portfolio console and adaptive workspaces (UI-01b/UI-01c)
The portfolio home uses `portfolio_service.build_portfolio` as one read-model boundary. It resolves
all lifecycle/planning contexts, runs the published program set once, aggregates resource demand
once, and produces separate RTG-plan and contract-risk denominators. OBSERVE and candidate work is
shown in the maturity ledger and never enters published delivery metrics.

Program navigation is generated from the registry. Each program exposes URL-addressable Overview,
Schedule, Flow, Units, Resources, Assumptions, and History tabs. Schedule delegates to the existing
RTG matrix or contract timeline only when publication is effective; otherwise the locked view names
the lifecycle, configured basis, readiness, epoch, and next gate. Operational tabs remain usable in
OBSERVE and expose source contract references without computing a target delta. The responsive
sidebar becomes an inert off-canvas drawer on mobile, so hidden links are not keyboard- or screen-
reader-accessible. Axe WCAG A/AA audits pass with zero violations.

### 5.5 Observation quarantine and BCA layup boundary (BCA-06)
`ObservationQuarantineEvent` is an append-only OPEN/RESOLVE/REOPEN stream for source records that
must not influence modeling. BCA layup audit `BCALAY` excludes shop orders whose IFS state remains
Started after terminal operation 9999 closes. Reconciliation appends only state changes and never
modifies IFS or prior evidence.

The layup route remains outside the Program registry. Its blocked policy separates TRI L labor
effort, ATUP operator effort, and ATUP six-hour discrete 24/7 autoclave occupancy. IFS reports both
WCs as infinite capacity, so physical staffing, slot count, compatibility, calendar, and external
demand require governed approvals before onboarding. See `docs/validation/bca-06-layup-quarantine.md`.

---

## 6. The forecast matrix (the flagship view)
- **Columns = RTG delivery slots**, not raw serials. Each slot has a fixed RTG target date +
  hand (LH/RH), filled by a currently-assigned serial. Grouped **LH → RH → Unassigned/bumped**.
  Aegis (no RTG) is serial-anchored, sorted by contract.
- **Rows = operations** (down), grouped into milestone bands (AJ/A1/A2/FS or LAM/ASSY/PAINT/
  SHIP), with inline cure + gate rows.
- **Cells:** `C`=done (green check), `WIP`=current op (amber chip — the one loud in-grid
  signal), projected date=upcoming (muted mono), cure/gate=tinted rows with glyphs.
- **Header metric rows per column:** Contract (IFS) · RTG target · Earliest · Forecast P50 ·
  **Δ vs target** (shape-redundant pills: ▲ filled >2d late, ▲ outlined 1-2d late, ▼ early, — on-time).
- **Swap handling:** reassign a slot's serial inline (dropdown). Atomic — the passer takes the
  ship slot, the passed unit drops to the other's slot. Persisted in `slot_assignment`.

---

## 7. The ML accuracy system (honesty model)
Three accuracy tracks, **kept deliberately separate** (blending would double-count or misstate evidence):
- **Retrospective backtest** → `accuracy_results.json` — 8 recent-production closes × 7/14/21d
  horizons; MAE 7.1d, all errors negative (systematically optimistic). PRELIMINARY, n≈8. Seeds
  the EMPIRICAL bias the live model applies today.
- **Forward maturity** → `accuracy_forward.json` — real physical shipments scored once at the
  earliest valid pre-pack forecast. It controls the EMPIRICAL→TRAINED gate.
- **Accuracy v1.0** → immutable `accuracy_summary_log` rows — the latest forecast in fixed 7-13,
  14-20, and 21-27 day windows before physical pack. It reports score, confidence, MAE, bias, Hit7,
  separate P80 calibration, exclusions, source IDs, and frozen cohort payloads. A headline is hidden
  until every horizon has at least five eligible units.
- **Threshold gate (per-program, forward-only):** models stay **EMPIRICAL** (apply the measured
  optimistic bias) until a program has enough **real FORWARD scored ships** — **ELEV 25, RAD 25,
  AEGIS 12** — then flip **TRAINED** (quantile P50/P80 on features). The count fed to the gate is
  `accuracy_forward.forward_counts()`, NOT the training-row count. Verified correct: at n=8 the
  trained model loses to empirical on leave-one-out, so the threshold is a real guard. Aegis uses
  12 because it's a ~5-unit program that would never reach 25 (thinner data → higher overfit risk,
  noted in admin copy).
- **WI extraction** feeds the sim's cure floors (de-confounds "curing" from "stuck" in the
  dwell feature) and provides complexity features. LLM extraction only, validated against
  hand-mined cures.

---

## 8. Design system ("Refined Ops Console")
Applied app-wide via `base.html` tokens. Principle: **calm canvas, loud signal.**
- Grayscale field; **amber reserved exclusively for WIP** (the one loud in-grid element).
- **Monospace (`.num`) for numbers only** (dates/Δ/op#/hrs) — Inter for everything else.
- **Δ pills are shape-redundant** (▲/▼/—, always signed) and outlined unless >2d late.
- Cure = purple dot glyph, Gate = ◇ diamond glyph, RTG row = dotted neutral rule, milestone
  bands = grey + brand stripe (no rainbow of colored rules).
- Sticky header + first column (explicit z-ladder, opaque backgrounds).
- **Light default + dark toggle** (localStorage). WCAG-AA contrast both themes; print-clean.
- Hardened through 3 plan iterations + 2 AI-critic passes (Gemini + Claude Opus).
- **Summary bullet/range chart** (`renderForecastBullet`): one row per unit, x=ship date,
  P50→P80 bar colored by status (green P80≤target / amber P50≤target<P80 / red P50>target),
  sim-floor whisker, target tick (scatter marker — NOT a numeric shape, which would collapse the
  categorical axis), right-aligned +Nd slip label, sorted worst-first. Replaced an unreadable
  4-marker scatter.

---

## 9. Database (SQLite) & JSON files
**DB (`data/rtg_app_migrated.db`, Alembic-managed) — 27 application tables:** ten core forecast/runtime and
program tables; ten resource/assumption/snapshot tables; four epoch-governance tables, and one
append-only observation-quarantine event table:
`model_epoch`, `model_epoch_transition`, `program_epoch_activation`, and
`simulation_snapshot_epoch`; append-only `resource_availability_event` and
`accuracy_summary_log` retain tooling and accuracy evidence.
**JSON (repo root, reference/computed):** accuracy_results.json (retrospective backtest),
accuracy_forward.json (real forward closes — separate on purpose), backtest_timeline.json,
forecast_log.json (legacy; the DB `forecast_log` table is authoritative), rtg_data.json,
rtg_targets.json, wi_signals.json, _rad_std.json.
**Program snapshots:** every `create_program` save also writes a timestamped JSON artifact to
`program_snapshots/` (diffable history; export-only, never read back — the DB is the load source).
**Alembic migrations:** `7068f2b7` initial · `e2d2104b` slot_assignment · `a3f1c9d4` refresh-loop
(position_state/model_history/sync_run) · `b4e2f7a1` program table · `c7d9e2f4` resource registry ·
`d8ea03f5` approved-record protection · `e6a1b2c3` model epochs · `f7b2c3d4` audit hardening ·
`a8c3d4e5` clean-install slot schema reconciliation · `b9d4e5f6` planning basis ·
`cad0e1f2` assumption evidence/recertification · `dbe1f2a3` review-integrity hardening ·
`ecf2a3b4` external-snapshot integrity · `fdb4c5d6` observation quarantine ·
`0a1b2c3d4e5f` resource availability events · `1b2c3d4e5f60` Accuracy v1.0 summaries.
Migration `a3f1c9d4e5b6_add_refresh_loop_tables` adds the three refresh-loop tables (also created
idempotently by `create_all` at startup).

---

## 10. Running the app
```bash
# offline (safe for dev/demo)
RTG_DATA_SOURCE=snapshot ./run.sh          # → http://localhost:8000
# live IFS
RTG_DATA_SOURCE=live ./run.sh              # then click "Connect IFS", browser login
```
- `run.sh` / `run.ps1` set `RTG_APP_PORT` to match `--port` (the OAuth redirect URI depends
  on it), run `alembic upgrade head` (idempotent), then uvicorn `--reload`.
- Migrations: `.venv/Scripts/alembic.exe upgrade head`.
- Admin actions on `/admin/model-status`: WI ingest, rebuild training rows, retrain, **Refresh
  positions**, **Process new ships** (preview→confirm), **seed / reset** the position layer, and
  **+ Manage / add programs** (→ `/admin/programs`). The sync buttons require a live "Connect IFS"
  session; in snapshot mode they say "Connect IFS first."

### 10.1 Tests (pytest — the regression safety net)
```bash
RTG_DATA_SOURCE=snapshot .venv/Scripts/python.exe -m pytest -q      # run all
.venv/Scripts/python.exe -m tests.golden capture                    # re-baseline (INTENTIONAL only)
```
- `tests/golden.py` - deterministic golden-master forecast snapshot for the 3 seed programs and
  40 static bootstrap WIP units. It explicitly ignores mutable `PositionState` and additional
  configured programs. `capture` writes `tests/golden_forecast.json`; `check` diffs it.
- `tests/test_regression.py` - seed golden match, golden-state isolation, golden seed scope, and
  DB-vs-routers configuration parity.
- `tests/test_pooling.py` - 4 tests for transitive shared-WC and plant-guard pooling.
- `tests/test_cure_station_contention.py` - serial cure-slot allocation, concurrent-slot behavior,
  validated seed rules, and wrapper profile propagation. The frozen parity model retains one Radome
  electrical-seal slot; 2026-09-03 process evidence supersedes that as a physical assumption, and
  #32c removes it only in a governed successor candidate while retaining the 40-hour cure.
- `tests/test_program_onboarding.py` - isolated `TEST4` program creation, pooling, forecasting,
  active-registry forecast stamping, and no ELEV/RAD/AEGIS forecast drift from adding TEST4.
  It also verifies that dynamic shared capacity honors DB crew and DPAS metadata.
- `tests/test_ifs_routing_discovery.py` - active-revision selection, tied-revision blocking,
  explicit revision review, BCA economics/classification, excluded-WC behavior, and onboarding
  API/page contracts.
- **Discipline:** run `pytest` after every engine or registry change. Re-capture the golden master
  only after an intentional static bootstrap/router forecast change, never after a live sync. The current baseline includes the intentional `32687` shared-capacity correction.

### 10.2 Version control (git — NEW)
Repo `git@github.com:millerrc18/twin-works.git` (pushed over **HTTPS** — GD blocks SSH port 22).
`.gitignore` excludes DBs (encrypted tokens), `.venv`, `__pycache__`, and the large WI `.docx`
(>100MB, keep the extracted `.txt`/JSON caches). Commit per step; each step is `pytest`-gated.

---

## 11. Refresh procedures (data is point-in-time)
- **Daily / after ships (primary path)** → Connect IFS, then click **Refresh positions** and,
  when units close, **Process new ships** on `/admin/model-status`. This updates all WIP
  positions, moves closed units to shipped, backfills forward accuracy, and retrains eligible
  programs — no code edits, no assistant. This is the intended self-service loop (§5.1).
- **RTG plan changed** → `python extract_rtg_targets.py` (re-reads the GAC RTG workbook → rtg_targets.json).
- **New unknown SO from a sync** → labeled by SO and flagged "needs serial" in the sync result
  (serials aren't in IFS). Map it in `wip_tables.py` / statusline; never guess by due-date order.
- **Revert a bad sync** → **reset to baseline** (admin) re-seeds `position_state` from `wip_tables`.
- **Retrospective accuracy backtest** → `python backtest_accuracy.py` (needs assistant-pulled
  timeline JSON) — the historical seed, distinct from the forward loop.

---

## 12. Build history (6 phases)
- **P0** Foundation — FastAPI + async SQLAlchemy + Alembic, 5 tables, shell.
- **P1** Sim + snapshot dashboard — value ships (de-biased P50/P80).
- **P2** WI extraction pipeline — LLM cures/gates, validated, persisted.
- **P3** ML feature pipeline — crew/cleaned-dwell/WI-complexity, 8 training rows.
- **P4** Lever engine — bottleneck view + what-if scenarios (systemic, no ML dep).
- **P5** OAuth + live IFS-MCP data source.
- **P6** Trained ML + tactical levers (data-gated at n≥25).
- **Post:** radome SN↔SO correction, RTG-target integration, slot-anchored matrix + inline
  reassign, matrix/summary toggle, and the "Refined Ops Console" design overhaul.
- **Post (readability):** matrix Tiers 1–3 — today reference, column hover, collapse-completed
  bands, two-line op labels, behind/active filter + URL state, print/PDF, legend, Δ tooltip +
  week-over-week slip arrows.
- **Post (summary redesign):** replaced the scatter timeline with the bullet/range chart.
- **Post (refresh loop):** PositionState mutable layer + per-program train gate (ELEV/RAD 25,
  AEGIS 12) + two admin sync buttons (positions / ships w/ preview + background retrain) +
  forward-only accuracy + model-history bias-trend chart. Plan hardened via a Claude-Opus critic
  pass (materialize-baseline, keep forward/backtest separate, idempotent daily log, fast/slow split).

---

## 13. Known limitations / gotchas (see AGENTS.md for the full list)
- Model EMPIRICAL until each program's forward-ship threshold (ELEV/RAD 25, AEGIS 12); backtest
  n=8 is directional. Forward-n starts at 0 and only grows as real ships are processed — so
  TRAINED is months out for ELEV/RAD and Aegis-at-12 will be thin data.
- Refresh loop needs a **live "Connect IFS" session** — both sync buttons no-op with a clear
  message otherwise. Snapshot mode still works fully off the last-synced `position_state` (or the
  wip_tables baseline if never synced).
- Live IFS is semi-live (browser session, not unattended); snapshot otherwise.
- Head serials not in IFS — serial mapping is statusline/DPM-sourced; a synced unknown SO is
  flagged "needs serial," never guessed.
- IFS MCP OAuth is browser-only (local callback); GPT LLM endpoint currently broken (uses Claude).
- Isolated tests must use a throwaway DB (real-DB pollution has bitten us).
- `charts.js` is browser-cached — bump the `?v=` tag when editing or stale JS is served.

---

## 13. Marion Virtual Factory Capacity Map

`GET /factory-map` is a visual-only decision surface for reviewed Marion Plant 2 and Plant 3
Floor 01 layouts. It renders rasterized VAMA02/VAMA03 plans with accessible work-center markers,
modeled capacity pressure, WIP and forecast-risk counts, and an HTMX inspector that drills through
to the existing forecast matrix and Levers pages.

- **Data contract:** `app/data/marion_wc_catalog.v1.json` contains the current TwinWorks and
  BCA-ready work-center facts captured from IFS `WORK_CENTER_CFV`; building identity comes only
  from P1/P2/P3 description prefixes. `marion_floor_map.v1.json` holds reviewed coordinates, not
  scheduler inputs. The VAMA02/VAMA03 PNG assets live in `app/static/floorplans/`.
- **Read-only telemetry:** `app/services/capacity_metrics.py` derives scheduled WC labor and
  modeled capacity from the existing pooled simulation profile. `floor_map_service.py` turns that
  into display data; it does not write WIP, alter the program registry, or change capacity budgets.
- **Physical-location rules:** `P3 QA` is a mobile resource and appears outside the coordinate
  canvas. `PRNG` is cataloged but unplaced until a reviewed annotation is supplied. VAMA01 and
  Plant 4 are out of the initial visual scope.
- **Open follow-ons:** the map covers current TwinWorks programs plus BCA-ready WCs. #82-1a is the
  governed complete active P1/P2/P3 catalog refresh; #82-4 adds PRNG/VAMA01/Plant 4 only from
  reviewed annotations; #82-5 completes authenticated live-map and response-time acceptance.
