# AGENTS.md — guidance for AI agents working in this repo

Read this before editing. It captures the architecture, conventions, and the gotchas that
have actually bitten us. For the full human-facing reference see **MASTER.md**.

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
  `database.py` (async SQLAlchemy/aiosqlite), `models.py` (**8 tables**), `templating.py`.
  - `app/engines/` — `router_registry.py` (wraps routers.py → `ProgramRegistry`, the ONLY
    shim; routers.py stays untouched), `rtg_wrapper.py` (`run_pooled` adapter over simulate),
    `lever_engine.py` (counterfactuals).
  - `app/data/` — `source.py` (DataSource ABC), `snapshot_source.py`, `live_source.py`
    (OAuth IFS MCP), `ifs_mcp_client.py`, `token_store.py`, `wip_tables.py` (bootstrap WIP
    data — now the SEED for PositionState, not read directly once seeded), `rtg_targets.py`.
  - `app/services/` — `forecast_service`, `matrix_service`, `slot_service`, `lever_service`,
    `slip_service` (week-over-week from ForecastLog DB), **`position_state`** (mutable WIP layer),
    **`forecast_log_service`** (idempotent daily stamp + close backfill), **`sync_service`**
    (the IFS refresh loop — positions + ships), **`accuracy_forward`** (forward-only scoring),
    **`model_history`** (per-sync model-state trend).
  - `app/routers/` — `dashboard`, `levers`, `auth`, `admin` (admin now hosts the sync buttons).
  - `app/templates/` (Jinja) + `app/static/charts.js`. Backups in `app/templates_bak/`.
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
RTG_DATA_SOURCE=snapshot ./run.sh        # offline, safe for dev
RTG_DATA_SOURCE=live ./run.sh            # live IFS (browser Connect first)
```
run.sh sets RTG_APP_PORT to match --port (needed for the OAuth redirect URI). Alembic:
`.venv/Scripts/alembic.exe upgrade head`. Verify: walk every page light+dark, confirm
reassign + lever-run + view-toggle work, data matches prior state.
