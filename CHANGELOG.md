# Changelog - TwinWorks

Human-readable history of the TwinWorks ship-date forecasting app. Newest first. Dates are when
work landed. Git is active for this repository; this file is the human-facing implementation record.
See MASTER.md for the full architecture reference and AGENTS.md for working rules and the current
handoff.

## 2026-09-01 - Portfolio operations console and adaptive program workspaces
- Completed UI-01b: replaced the hardcoded dashboard cards and static KPIs with a registry-driven
  portfolio command strip, dense operating table, separately labeled RTG-plan and contract-risk
  denominators, published-baseline shared-pressure signal, maturity/review ledger, and source
  freshness ledger. The route performs one pooled simulation and one resource aggregation.
- Completed UI-01c: added dynamic program navigation and URL-addressable Overview, Schedule, Flow,
  Units, Resources, Assumptions, and History workspaces. Published program schedules preserve the
  existing matrix/timeline behavior; OBSERVE workspaces expose position and evidence without dates
  or delivery KPIs, and Schedule remains visibly locked.
- Replaced the fixed mobile sidebar with an off-canvas drawer that is inert while closed and closes
  after navigation. Added a skip link, Lucide tool icons, shared program tabs, responsive tables,
  and explicit plan-source, epoch, readiness, and next-gate labels.
- Added route/read-model regression coverage proving one portfolio simulation/capacity pass,
  registry-driven navigation, BCA lifecycle suppression, and all workspace states. Desktop/mobile
  and light/dark visual checks passed; interactive mobile drawer checks passed; axe WCAG A/AA audits
  report zero violations. Five live portfolio requests averaged 3.29 seconds (2.84-4.63 seconds).
- Full suite: 62 passing tests; Ruff and the static golden forecast remain exact.

## 2026-08-31 - Planning basis, recertification, and incumbent shadow parity
- Completed BCA-05a observation registration from the app's authenticated IFS session. `BCAFIN`
  now tracks 73 live finishing orders with zero unresolved NOTE_TEXT serials under immutable
  revision-3 evidence. The candidate remains `OBSERVE`; contract intent is not in force, Schedule
  is locked, and no BCA forecast-log rows or leadership delivery KPIs are published.
- Preserved eight BCA resource-binding gaps as explicit incomplete readiness rather than supplying
  `DEFAULT_SHIFT`. Factory Map and Levers now simulate only published programs, while the map may
  still display BCA position evidence. Incumbent legacy forecasts and publication remained exact.
- Fixed the live Radome matrix serial/SO join. `LiveMcpDataSource` now uses the same canonical
  `SHOP_ORD_CFV.NOTE_TEXT` parser as position sync, then falls back to the last persisted mapping
  before the bootstrap table. New SOs `1462514`/`1462515` therefore render as S/N `524`/`525` and
  receive their RTG targets instead of appearing as raw-SO, missing-RTG columns.
- Reconciled RTG slot visibility with the current-WIP contract. Completed S/N `514` and `508`
  retain their assignment history in SQLite but no longer render as empty WIP slots. Added focused
  parser/live-source/slot tests; full suite now has 61 passing tests and no golden drift.
- Completed UI-01a with explicit `PLAN_SLOTS`, `CONTRACT_DATES`, and `NONE` semantics independent
  from model lifecycle. Forecast DTO/log records now separate contract, plan, and effective
  comparison targets; non-commitment-ready programs expose no forecast dates or delivery KPIs.
- Added migrations `b9d4e5f6a7b8`, `cad0e1f2a3b4`, and `dbe1f2a3b4c5` for planning metadata,
  versioned assumption evidence, idempotent review keys, resolution provenance, successor links,
  and SQLite-enforced review coherence/immutability.
- Added expiry, missing-date, migrated-evidence, missing-drift-policy, sparse-evidence, and measured-
  drift review generation. Recertification creates approved successor assumptions and capacity
  versions; it never edits the historical evidence/value in place. `/admin/resources` shows open
  review debt, and `/admin/resources/audit.json` exports permanent append-only audit history.
- Added schema-v3 simulation replay envelopes with canonical frozen WIP inputs, epoch routes,
  scheduler profiles, expected results, engine/serializer versions, and SHA-256 integrity checks.
  Existing schema-v2 profile snapshots remain verifiable but are explicitly non-replayable.
- Added migration `ecf2a3b4c5d6` and source-horizon validation for immutable external-load
  snapshots. Non-parity external demand cannot be trusted past its captured horizon without an
  explicit approved `BLOCK`, last-week, or trailing-mean policy; live CRP ingestion remains BCA-03c.
- Created ELEV/RAD/AEGIS DB-shadow candidates in `OBSERVE`, with frozen one-to-one resource
  mappings and live-definition drift rejection. The 29-unit acceptance run produced exact legacy/
  shadow parity and exact replay with result hash
  `c12de821f4b095bbe0a8e719de486ec21ce98943b47b5d41bb736a676968381a`.
- Materialized 70 review items: 24 missing review dates, 24 migrated-evidence attestations, and 22
  missing drift policies. These correctly keep candidate readiness provisional; published legacy
  epochs remain unchanged. Added `scripts/verify_incumbent_shadow.py` for repeatable dry-run or
  `--commit` verification.
- Populated upgrade and fresh-database upgrade/downgrade/upgrade passed. Full suite: 57 passing
  tests; static golden forecast remains exact.

## 2026-08-28 - Governed lifecycle and immutable model epochs (PLAT-01a)
- Added immutable `model_epoch` definitions, append-only lifecycle transitions, and append-only
  publication/rollback selections through migrations `e6a1b2c3d4e5` and `f7b2c3d4e5f6`.
- Enforced the lifecycle and authority graph at both service and SQLite-trigger layers. Direct
  updates/deletes of epoch governance rows, simulation snapshots, and constraint events are blocked.
- Added raw-SQL regression coverage for UPDATE, DELETE, and INSERT OR REPLACE across all six
  protected audit tables, deterministic JSON rejection for non-finite/unsupported values, stale
  activation race coverage, partial-bootstrap recovery, and exact snapshot-link verification.
- SQLite app/Alembic connections now verify foreign-key and recursive-trigger pragmas. Application
  startup audits the expected governance-trigger inventory and fails fast on schema drift.
- Bootstrapped ELEV, RAD, and AEGIS as published `COMMITMENT_READY` legacy epochs. Candidate epochs
  remain isolated until an authorized publication event, and pausing a published epoch invalidates
  that publication until it is explicitly republished.
- New program onboarding now creates a DRAFT candidate. Reconfiguring a published program stages
  its candidate definition without mutating the active registry, and authoritative daily forecast
  stamping skips programs without a valid publication.
- Materialized complete epoch definitions inside schema-v2 simulation snapshots and added queryable
  per-program epoch links. Runtime registry drift against a published legacy definition now fails
  loudly instead of producing a mislabeled snapshot.
- Created the pre-migration backup:
  `data/rtg_app_migrated.pre_model_epochs.bak`, SHA-256
  `1F63D0C88AD53DA0CAF0E0BE2852C68D0D7B656D4734EB52BCCA2FAF97D436FF`.
- Added migration `a8c3d4e5f6a7` after the clean-install audit found the historical
  `slot_assignment` migration was empty. Fresh Alembic installs and the live/create-all schema now
  converge on the same 24 application tables; the local DB is at this revision.
- Full suite: 48 passing tests; static golden forecast remains exact with no date drift. Uvicorn
  startup plus health, dashboard, and program-admin smoke checks passed with governance auditing on.

## 2026-08-27 - Resource and Assumption Registry foundation (BCA-03a)
- Added normalized physical resource, capacity-version, operation-binding, external-load,
  assumption, snapshot, constraint-event, and review tables through migrations `c7d9e2f4a6b8`
  and `d8ea03f5b7c9`.
- Added immutable assumption governance, effective-date overlap checks, evidence sufficiency rules,
  binding validation, and program resource-coverage reporting.
- Seeded 24 one-to-one legacy-equivalent labor/cure pools and compiled canonical immutable profile
  snapshots. DB-shadow results match the 40-unit golden forecast exactly.
- Added `/admin/resources`, provenance/readiness displays, forecast Why panels, and snapshot linkage
  on daily forecast logs. Legacy allocation remains authoritative; no capacity math changed.
- Reconciled historical Alembic stamps where `create_all` had previously materialized newer tables;
  verified the repair against a pre-migration backup before applying it locally.
- Approved assumptions and capacity versions are protected from direct ORM/Core SQL edits except
  the controlled supersession transition. Failed forecast stamps roll back their snapshots.
- Full suite: 41 passing tests. Next gate: BCA-03b physical shared-pool activation after owner
  approval of capacity assumptions.

## 2026-08-27 - BCA revision-aware routing discovery (BCA-01/02)
- Rebuilt IFS routing discovery around active shop-order revision usage. The onboarding API now
  defaults to a uniquely dominant active revision, returns all revision choices, and requires an
  explicit revision when active usage is tied.
- Preserved setup/run labor, setup/run machine time, crew, run-time code, parallel flag,
  reference-order operation status, NOWB, classification, and inclusion in the onboarding draft.
- Reworked `/admin/programs` into a revision/economics review surface with all-row and included
  totals. Administrative, waiting, and terminal rows remain visible but default excluded; unknown
  production WCs alone drive the capacity gate.
- Live IFS verification for project `521938`: both `3301ED0031-101A/C` use revision 3 / alternative
  `*` with 32 rows and 69.603 labor hours. Machine hours are 104.303 for A and 104.603 for C due to
  differences at ops 3000, 3100, and 4000. Exact revision/alternative ties require explicit
  selection. Full suite: 26 passing tests.

## 2026-08-26 - #82 Marion Virtual Factory Capacity Map
- Delivered the `GET /factory-map` decision surface: reviewed VAMA02 and VAMA03 Floor 01 drawings
  render as interactive operational canvases with work-center markers, modeled capacity pressure,
  WIP flow, forecast risk, and affected-unit drill-throughs.
- Added versioned Marion mapping data and floor-plan assets. Confirmed corrections include
  `AEROL` = P3 LAM AERO, `234` = P3 MM, `238` = P3 OVEN, and `32677` = P2 LAM G500. `P3 QA` is
  explicitly mobile; `PRNG` remains unplaced until its reviewed annotation arrives.
- Reused the simulation output through a read-only capacity-metrics seam. The map does not alter
  program configuration, WIP, work-center budgets, cure-station rules, or forecast inputs.
- Added five map validation/no-drift/endpoint tests, registry-driven capacity telemetry,
  URL-stateful floor and program filters, and forecast/lever deep-link highlighting. Full suite:
  19 passing tests.
- The separate #82-1a task to retain an all-active-P1/P2/P3 IFS catalog remains open. The delivered
  catalog covers current TwinWorks programs and BCA-ready work centers.
- Follow-ons #82-4 and #82-5 cover annotation-governed PRNG/VAMA01/Plant 4 expansion and the
  authenticated live-map acceptance/performance check.

## 2026-08-26 - TwinWorks cleanup and cure-station contention
- **#83 complete:** live application branding, dynamic IFS OAuth client identity, run scripts,
  current docs, and retained mockups now use TwinWorks. RTG stays as domain and compatibility
  terminology. Added `README.md`; removed and ignored the two committed WI extraction scratch files.
- **#32 allocator complete:** `capacity_engine` now reserves discrete cure slots through the
  profile contract. Elevator dry-to-handle and Cor Ban cures share two Plant 2 paint booths; the
  Radome op775 electrical-seal cure uses one conservative Plant 3 station. Ovens remain
  unconstrained, and the parallel topcoat tape-test does not reserve a booth.
- Added four focused cure-station tests and intentionally recaptured the static 40-unit golden
  baseline for the new physical-capacity behavior. Remaining #32 work is calibration of the
  Radome electrical-seal station count from one to two if floor/process validation supports it.
## 2026-08-25 - #81 safety gate completed
- Added `tests/test_program_onboarding.py`: an isolated SQLite fixture creates `TEST4`, proves
  Plant 2/WC 221 pooling, forecasts and stamps the program, and confirms ELEV/RAD/AEGIS forecasts
  do not drift.
- Fixed registry rebuild identity: `router_registry.rebuild()` refreshes the existing object so
  imports held by forecast, feature, matrix, and pooling code observe a newly onboarded program.
- `ForecastLog.stamp_build` now stamps the active program registry instead of a fixed seed tuple.
- Added the registry-driven scheduler profile: DB crew and DPAS metadata, dynamic shared WCs, and legacy shift budgets now reach `capacity_engine`. The profile intentionally corrects the ELEV/Aegis shared resource from the old `32678` assumption to actual WC `32687`; the 40-unit seed golden baseline was recaptured.
- Repaired the golden harness: it uses 40 static bootstrap WIP units, is scoped to ELEV/RAD/AEGIS,
  ignores mutable `PositionState` and additional configured programs, and was recaptured from that
  deterministic baseline. The suite is now 10 passing tests; existing `datetime.utcnow()` warnings
  remain for future Python 3.14 cleanup.
- Remaining #81 work is operational: a real OAuth-backed onboarding smoke test, followed by a
  2-4 week flag-gated fallback cutover. See AGENTS.md for the current handoff.

## 2026-08-24 - Add-new-program workflow (#81)
- Added the `program` table and migration `b4e2f7a1c8d9`, DB-or-routers config source,
  `program_service`, seed-the-3 behavior, active-program metadata, and program snapshots.
- Routed program order, names, IFS metadata, pack operations, thresholds, and all pooled-sim
  callers through the registry; DB and routers source forecasts remain byte-identical.
- Added plant-guarded, transitive shared-WC pooling, IFS routing discovery, unknown-WC gate, and
  the `/admin/programs` onboarding page. Initial pooling and parity coverage started with 6 tests.
- The 2026-08-25 safety gate completed the synthetic fourth-program coverage. The remaining live
  smoke test and staged fallback removal are documented in AGENTS.md.

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
