# Changelog — RTG Tracker

Human-readable history of the RTG ship-date forecasting app. Newest first. Dates are when the
work landed. (No git for this app yet — this file is the record of record. See MASTER.md for the
full architecture reference and AGENTS.md for working rules.)

## 2026-08-24 (in progress) — Add-new-program workflow (#81)
Config-driven program registry so new programs onboard via UI, not code. Plan critic-hardened
(Gemini + Claude Opus). Progress so far:
- **`program` table + migration** (`b4e2f7a1c8d9`) — full program config as JSON columns
  (ops/cures/milestones/ceilings/crew/hand-map + IFS project/parts + pack/ship/floor + threshold).
- **`program_service.py`** — DB-or-routers.py source (flag `RTG_PROGRAM_SOURCE=db|routers`),
  `seed_from_routers` (one-time copy of the 3), sync cached `load_specs`, `ifs_meta`,
  `program_order`, snapshot export to `program_snapshots/`.
- **`router_registry.build_registry`** now prefers DB specs, falls back to routers.py; `rebuild()`
  for cache invalidation. **Verified BYTE-IDENTICAL**: DB-source vs routers-source forecasts match
  exactly on the same data (regression gate passed).
- **Regression test harness added** (`tests/`, pytest + pytest-asyncio) — golden-master forecast
  snapshot (`tests/golden.py capture|check`, 42 units) + `test_regression.py`:
  `test_forecast_matches_golden_master` (fails on any date drift) and
  `test_db_and_routers_sources_agree` (DB vs routers config identical). Run: `pytest`. Re-capture
  the golden master only when a forecast change is INTENTIONAL. This is the safety net for the rest
  of #81 and all future engine work.
- STILL TODO (next session): swap PROG_NAME/ORDER/IFS/PACK_OP reads to registry; transitive
  shared-WC pooling refactor of run_pooled (4 callers: forecast_service, matrix_service,
  lever_engine, dataset.py); IFS routing discovery + unknown-WC gate; /admin/programs UI;
  synthetic-4th-program test; then flag-gated cutover. Gate every step with `pytest`.

## 2026-08-24
- **ELEV + AEGIS WI ingestion completed** — head serials/cures were mined but never extracted
  into caches. Produced `wis/extractions/ELEV_4401.json` (11 cures, 100% match to router) and
  `AEGIS_00999000563.json` (4 WI cures + 3 IFS-autoclave set aside); wired both into
  `PROGRAM_WIS`. All 3 programs now ingest WIs.
- **Head serials now parse from IFS NOTE_TEXT** ('S/N nnn', leading zeros stripped) + PART_NO for
  elevator hand (501=LH/502=RH). Fixes wrong baseline SNs/hands (SO 1451270 was 'LH 1270', really
  RH 226). Applied in `sync_service` for WIP + ships; wip_tables SHIPPED elevators corrected.
- **Ship detection now pack-op-driven** — a unit is "shipped" when its pack op is clocked OR the
  SO is closed (CLOSE_DATE often lags days behind physical ship). Fixes S/N 0515 being invisible
  (packed 8/21, SO still Started). `ship` date = pack date preferred, else close.
- **Process-ships date floor** — `SQL_CLOSED` floors on `>= 2026-08-01` (was pulling 131 historical).
- **Admin: "Units in the model" panel** — two side-by-side tables showing exactly which
  program / SN / SO# feed each track: Backtest (retrospective, 8 units, empirical bias seed) and
  Forward (real scored ships, counts toward the train gate). Color-coded error days.
  New `app/services/model_units.py`; admin route + `admin.html`.
- **Admin polish** — connection banner reads real tokens (not boot mode); collapsible per-program
  WI-constraint tables (default collapsed, click to expand); tooltips on every admin button;
  preview "already-recorded skipped" note; `[x-cloak]` rule in base.html.
- **Process-ships date floor** — `SQL_CLOSED` now floors on `CLOSE_DATE >= 2026-08-01`
  (`SHIP_SINCE`) so the preview pulls only in-window closes, not the entire history (was 131).
- **Preview clarity note** — the ship preview now states that units already recorded as shipped
  (baseline / previously processed) are intentionally skipped, so "only 2 new" isn't confusing.
- **Admin connection banner fix** — "Connected to IFS" now reflects REAL stored OAuth tokens
  (`ifs_connected` from token_store), not the boot-time `RTG_DATA_SOURCE`. Buttons always worked;
  only the banner text was wrong.

## 2026-08-22 — Refresh loop + model observability (PM self-service)
Goal: the PM refreshes data himself after ships instead of asking the assistant. Plan hardened
via a Claude-Opus critic pass (materialize-baseline, keep forward/backtest separate, idempotent
daily log, fast/slow split).
- **PositionState** — mutable WIP/shipped layer, materialized once from the `wip_tables` baseline
  then updated by IFS syncs. SnapshotDataSource reads it when populated (else baseline). `reset`
  reverts. Never rewrites `wip_tables.py`. (`app/services/position_state.py`, new `position_state`
  table + `model_history` + `sync_run` tables, migration `a3f1c9d4e5b6`.)
- **Per-program train gate** — `n_train_threshold` is now a dict `{ELEV:25, RAD:25, AEGIS:12}`
  (Aegis is ~5 units; 25 unreachable). `registry.threshold_for(program)` / `trainer._threshold_for`.
- **Button 1 — Refresh positions** — pull current op position + last-clock + due from IFS, upsert
  PositionState, stamp today's idempotent ForecastLog build (makes the matrix slip arrows work).
- **Button 2 — Process new ships** — preview→confirm; FAST (record closes + backfill accuracy) +
  SLOW background (rescore forward accuracy, rebuild training rows, retrain if eligible, reload).
  Single-run lock via `sync_run`; IFS reads off the event loop, never inside a DB tx.
- **Forward vs backtest kept separate** — real forward closes score into `accuracy_forward.json`
  (gate counts forward-only); retrospective backtest stays in `accuracy_results.json`. No blending.
- **ForecastLog now DB-authoritative** — idempotent daily upsert (build_date, serial); `slip_service`
  reads the DB table so week-over-week slip arrows light up at >=2 builds.
- **Model history + bias trend** — every sync appends a `model_history` point; admin shows a table
  + a Plotly bias-over-time line (`renderBiasTrend`) — watch bias -> 0 and the EMPIRICAL->TRAINED flip.

## 2026-08-22 — Summary chart redesign
- Replaced the unreadable 4-marker scatter timeline with a **bullet/range chart**
  (`renderForecastBullet`): one row per unit, x=ship date, P50->P80 bar colored by status
  (green/amber/red), sim-floor whisker, target tick, +Nd slip label, sorted worst-first.
  (Fixed a Plotly trap: numeric shape coords collapse a categorical axis — target is a scatter now.)

## 2026-08-22 — Matrix readability (Tiers 1-3)
- **T1** today-week tint + column hover highlight.
- **T2** collapse-completed milestone bands (default collapsed) + two-line op labels (no wrap) +
  slimmer cure/gate rows + quiet milestone dividers; dropped the redundant "Earliest" metric row.
- **T3** behind/active filter (URL-stated) + Print/PDF + compact legend + Delta tooltip +
  week-over-week slip arrows; widened op column to 290px (wrap fix).

## Earlier (pre-changelog) — see MASTER.md 12 for detail
- **Design overhaul** — "Refined Ops Console" (calm canvas, loud signal); light default + dark
  toggle; WCAG-AA; 3 plan iterations + 2 AI-critic passes.
- **Slot-anchored matrix** — RTG delivery slots <-> serial, inline atomic-swap reassign;
  matrix/summary view toggle; RTG target dates integrated (Delta vs RTG, not just contract).
- **Radome SN<->SO correction** (2026-08-21, from DPM/statusline; old due-date-order guess wrong).
- **P0-P6 build** — FastAPI foundation; sim + snapshot dashboard; WI extraction pipeline; ML
  feature pipeline + training rows; lever/what-if engine; OAuth live IFS-MCP source; trained ML +
  tactical levers (data-gated).
- **Backtest engine** — 8 recent closes x 7/14/21d horizons -> accuracy_results.json (MAE ~7d,
  systematically optimistic, PRELIMINARY n=8).

## Conventions for this file
- One dated section per landing; newest on top. Group related changes.
- Note *why* when non-obvious. Reference new files/services so future-you can find them.
- This is the code-history record until/unless a dedicated git repo is set up for the app.
