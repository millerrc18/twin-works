# #82 Marion Virtual Factory Capacity Map

## Status

Phase 1 implemented 2026-08-26. VAMA02/VAMA03 map rendering, curated WC placements,
read-only telemetry, responsive UI, and drill-through are delivered. The full all-active-P1/P2/P3
IFS catalog refresh remains #82-1a. This plan remains the contract that the map cannot alter
forecast or scheduler behavior.

Scope update 2026-09-02: active telemetry and program filters cover ELEV/RAD/AEGIS only after
SCOPE-01. Deferred BCA work-center catalog facts may remain for audit/reference, but they do not
create active WIP, capacity pressure, navigation, or forecast context.

## Objective

Add a Marion factory view that lets a program manager see relevant work centers, modeled load and
WIP, affected units, and the existing capacity levers available. The view is a decision-support
overlay on TwinWorks data. It is not a shop-floor control system and it must not provide inputs to
`capacity_engine.simulate()`.

The first useful release covers the reviewed Floor 01 drawings for:

| Building | Floor-plan source | Initial treatment |
| --- | --- | --- |
| VAMA02 / Plant 2 | Annotated page 3 of `Marion-FloorPlan.pdf` | Full interactive floor map |
| VAMA03 / Plant 3 | Annotated page 5 of `Marion-FloorPlan.pdf` | Full interactive floor map |
| VAMA01 / Plant 1 | No reviewed coordinate overlay yet | Catalog-only, no false placement |

The source PDF remains at `C:\Users\ryan.c.miller\Downloads\Marion-FloorPlan.pdf`. The app uses
reviewed raster derivatives of the two Floor 01 pages, not the PDF at runtime.

## Fixed Decisions

- Display-only: map data, filters, and clicks never modify a program, work-center budget,
  cure-station rule, WIP, forecast, or lever scenario.
- IFS `WORK_CENTER_CFV.DESCRIPTION` prefixes `P1`, `P2`, and `P3` are the authoritative building
  classification. `CALENDAR_ID` is not a building key.
- IFS supplies building prefix, department, and production line, but not floor, room, or XY
  coordinates. Those remain a manually reviewed overlay.
- `P3 QA` is mobile. It has no fixed marker or coordinates and is rendered in a separate Plant 3
  Mobile resources area.
- `PRNG` / P3 RANGE is deferred and unplaced until Ryan supplies its annotation. It may be shown
  as unplaced when relevant, but the app must not guess a location.
- VAMA01 is deferred until its overlay is reviewed. No marker is placed there in Phase 1.
- The BCA pilot remains blocked by BCA-01 through BCA-07. The map may contain BCA WC records
  before BCA is active, but it must not invent BCA forecast telemetry.

## Curated Mapping Data

### Storage choice

Use versioned repository data, not a database table, for facility geometry and placements:

```text
app/data/marion_wc_catalog.v1.json
app/data/marion_floor_map.v1.json
app/static/floorplans/marion-vama02-floor01.png
app/static/floorplans/marion-vama03-floor01.png
```

This makes layout changes reviewable in a normal diff, keeps snapshot mode deterministic, and
allows BCA or future work-center additions without Python or schema changes. It keeps curated
display decisions separate from live IFS source data and the program registry.

No Alembic migration is planned for Phase 1. The `program` table remains the source of program
routings and scheduler configuration; the floor-map files provide visual metadata only.

### IFS catalog seed

`marion_wc_catalog.v1.json` currently contains the active WC facts needed by tracked TwinWorks
programs and BCA readiness, captured from Marion site 59. Each record retains WC code, IFS
description, P1/P2/P3 building classification, department, production line, source system, site,
and capture date. The repeatable full all-active-P1/P2/P3 refresh remains task #82-1a.

The delivered JSON loader normalizes and validates reviewed WC records while preserving rows that
have no map placement. The repeatable #82-1a refresh will classify new IFS rows from description
prefixes and surface additions, changes, inactive rows, and unclassified prefixes for review.

The catalog is intentionally broader than the placed map, but Phase 1 does not yet retain every
active P1/P2/P3 WC returned by IFS. Only reviewed locations are rendered as fixed markers.

### Floor-map overlay schema

`marion_floor_map.v1.json` is the reviewed placement layer. Coordinates use each floor asset's
`1224 x 792` view box so markers scale with the rendered image.

```text
schema_version: 1
facility: Marion
site: 59
floors:
  id: VAMA02-F01
  building: P2
  asset: /static/floorplans/marion-vama02-floor01.png
  view_box: [0, 0, 1224, 792]
placements:
  wc: 236
  floor_id: VAMA03-F01
  zone: paint
  x: 331
  y: 240
  label: P3 Paint
  resource_kind: fixed
  status: confirmed
  shared_resource_group: null
  annotation_source: Marion-FloorPlan.pdf 2026-08-26
resources:
  wc: P3 QA
  building: P3
  resource_kind: mobile
  label: P3 QA
  status: confirmed-mobile
  operating_area: [VAMA03-F01]
  wc: PRNG
  building: P3
  resource_kind: unplaced
  label: P3 RANGE
  status: deferred
```

`placements` holds only fixed resources. `resources` represents non-point resources such as mobile
and unplaced WCs. Every WC may have at most one fixed placement; aliases are normalized in the
catalog and never rendered as duplicate markers.

The loader validates schema version, referenced floor IDs, coordinate bounds, unique WCs, required
labels, and allowed resource kinds: `fixed`, `mobile`, and `unplaced`. Invalid map data fails
closed in development; production renders the rest of the page with a clear map-data warning.

### Confirmed annotation facts

| WC or label | Correct visual classification | Phase 1 behavior |
| --- | --- | --- |
| `AEROL` | P3 LAM AERO | Fixed P3 marker |
| `234` | P3 MM | Fixed P3 marker |
| `238` | P3 OVEN | Fixed P3 marker |
| `298` | P4 RANGE, not P3 OVEN | Catalog only until Plant 4 is in scope |
| `32677` | P2 LAM G500 | Fixed P2 marker; upstream Elevator component context |
| `P3 QA` | Mobile inspection | Mobile resource, no coordinate |
| `PRNG` | P3 RANGE | Deferred and unplaced |

Initial catalog coverage includes current Plant 2 and Plant 3 TwinWorks WCs plus BCA-ready entries:
`P3TRI`, `TRI A`, `P3NDI`, `PRNG`, `236`, `P3 QA`, `3FINL`, `235`, `TRI L`, and `ATUP`.

## Telemetry Contract

### Design principle

Every number on the map says whether it is modeled or measured. The current application has a
modeled finite-capacity schedule and IFS/snapshot WIP position data. It does not have real-time
machine telemetry or an authoritative shop-floor queue measurement.

### Service boundary

`app/services/floor_map_service.py` is the presentation adapter. Generic weekly WC load calculation
lives in the reusable, pure `capacity_metrics.py` helper, which the Levers page also consumes. The
helper iterates the active `ProgramRegistry` and performs no writes.

The map service accepts a `DataSource` and optional program filter. It runs the pooled scheduler
once per request, then shares that immutable result between WC metrics and per-program forecasts.
It does not query IFS directly and it does not mutate the scheduler, registry, WIP, or budgets.

```text
FloorMapPage
  site, generated_at, data_source, filter
  floors: id, building, label, asset, markers
  mobile_resources
  unplaced_resources

Marker
  wc, label, placement, catalog_metadata
  telemetry: active_unit_count, queued_unit_count, scheduled_labor_hours_7d
  telemetry: modeled_weekly_capacity_hours, peak_weekly_utilization_pct
  telemetry: weeks_over_capacity, late_unit_count, at_risk_unit_count, status
  affected_units: program, serial, so, current_operation, p50, p80, target, delta_days, stalled
```

| Field | Definition | Truth type |
| --- | --- | --- |
| Active units | First remaining routed operation is at the WC | Measured position plus modeled routing |
| Queued units | Distinct non-stalled WIP with a later remaining operation at the WC | Modeled route/WIP relationship |
| 7-day labor | Planned labor for operations scheduled in the next seven calendar days | Modeled schedule |
| Weekly capacity | Capacity from the active TwinWorks shift-budget profile | Modeled configuration |
| Peak utilization | Maximum weekly labor divided by modeled weekly capacity | Modeled schedule |
| Weeks over capacity | Scheduled weeks with demand above modeled capacity | Modeled schedule |
| Late units | P50 is after the RTG target or contract fallback | Forecast risk |
| At-risk units | P80 is late while P50 is on/before target | Forecast risk |

Each metric carries a short source label. No value is labelled actual capacity, actual queue, or
machine availability unless a later approved integration supplies it. Mobile and unplaced resources
may show routing/WIP and risk data, but never a fake coordinate heat state.

## Web Experience

### Route and navigation

- `app/routers/factory_map.py` is included from `app/main.py`.
- `GET /factory-map?program=all|<active-code>&floor=<floor-id>` renders the full page.
- `Factory map` appears under Tools in `app/templates/base.html`.
- Program options are registry-driven, so BCA appears only after it is active in the registry.
- `GET /factory-map/wc/{wc}?program=...` returns the HTMX-loaded details inspector and
  only the selected WC presentation model.

The map defaults to all active programs and the first reviewed floor. Selected floor and program
are URL-stateful so a filtered operational view can be shared or revisited.

### Visual layout

- The reviewed drawing renders in a stable `1224 x 792` coordinate container with the PNG as a
  non-interactive background. Markers are accessible HTML buttons over that image.
- Use compact colored WC markers with labels and a redundant state icon/text. Color communicates
  load/risk, while label and accessible description communicate the same state.
- Use existing light/dark variables for chrome and markers. The engineering drawing stays neutral
  on a white canvas in both themes; do not invert it for dark mode.
- The right-side inspector gives resource label, catalog facts, a modeled-versus-measured legend,
  capacity/WIP metrics, and affected units. It is an operational panel, not a decorative card stack.
- Provide Mobile resources for `P3 QA` and Unplaced resources for deferred mappings such as `PRNG`.
  Both remain filter-aware.
- A marker with no tracked WIP is neutral, not green. A marker without configured modeled capacity
  presents WIP/route data but explicitly states Capacity not configured.

### Drill-through

The inspector links affected units to `/forecast/{program}?view=matrix&serial={serial}` and
links capacity context to `/levers?wc={wc}`. Add matching shallow enhancements:

- `serial` focuses and visually highlights the unit without filtering other units out.
- `wc` highlights the bottleneck row and preselects matching lever context when one exists.
- The deep links never run a scenario, write state, or change a forecast.

## Delivery Evidence

- Reviewed VAMA02/VAMA03 raster assets, catalog, placements, and mobile/unplaced rules are versioned.
- The loader validates schema versions, unique resources, floor references, coordinate bounds, and labels.
- Registry-driven capacity metrics are shared by the Factory Map and Levers page.
- Full-page and HTMX routes, filters, responsive navigation, inspector, and drill-through are delivered.
- Desktop and 390px narrow-viewport captures were visually reviewed in light theme; existing color
  tokens provide the dark-theme treatment.
- The final suite has 19 passing tests, including five #82 validation/no-drift/endpoint tests.
- Snapshot HTTP smoke checks cover the map, filtered P3 view, mobile P3 QA inspector, forecast
  serial highlight, and WC-focused Levers page. The authenticated live check remains #82-5.

## Test Strategy

Automated coverage must include:

- JSON validation: duplicates, bad coordinates, missing floors, mobile, and unplaced resources.
- IFS catalog classification from P1/P2/P3 description prefixes, deliberately ignoring `CALENDAR_ID`.
- Snapshot telemetry for known P2/P3 WCs plus neutral state for a mapped WC with no WIP.
- Program filtering and registry-driven inclusion of a synthetic fourth program.
- `P3 QA` without coordinates and `PRNG` without a fixed marker.
- Route responses plus map, forecast, and levers deep-link parameters.
- Proof that map requests do not mutate registry/program rows, `PositionState`, scheduler profile,
  or golden forecast output.

Manual acceptance checks:

- VAMA02 and VAMA03 render with reviewed assets and correct confirmed-marker placement.
- Program filters change markers and affected units consistently.
- The inspector distinguishes modeled values from measured WIP position data.
- Mobile/unplaced resources are visible but never drawn as fixed point locations.
- Both themes and common desktop/narrow window sizes remain legible.

## Explicit Exclusions

- No scheduler inputs from map coordinates, zones, marker state, or map filters.
- No automatic capacity update, work-center reassignment, dispatch, or resequencing.
- No claim that modeled workload is real-time shop-floor availability.
- No VAMA01 or Plant 4 map until reviewed overlays exist.
- No `PRNG` placement until reviewed annotation is supplied.
- No BCA forecast, capacity budget, or active-program configuration before BCA-01 through BCA-07.

## Follow-On Gates

- #82-1a: complete the repeatable all-active-P1/P2/P3 IFS catalog refresh and change report.
- #82-4: add PRNG, VAMA01, or Plant 4 coordinates only from reviewed annotations.
- #82-5: complete the authenticated live-map acceptance and response-time check.
