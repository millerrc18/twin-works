"""Versioned Marion floor-map data loader and validation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parent
CATALOG_PATH = DATA_DIR / "marion_wc_catalog.v1.json"
MAP_PATH = DATA_DIR / "marion_floor_map.v1.json"
BUILDING_RE = re.compile(r"^\s*(P[123])(?:\s|$)", re.IGNORECASE)
VALID_RESOURCE_KINDS = {"fixed", "mobile", "unplaced"}


class FloorMapDataError(ValueError):
    """Raised when curated facility data cannot be safely rendered."""


@dataclass(frozen=True)
class FacilityMap:
    catalog: dict[str, dict[str, Any]]
    floors: dict[str, dict[str, Any]]
    placements: tuple[dict[str, Any], ...]
    resources: tuple[dict[str, Any], ...]


def classify_building(description: str | None) -> str | None:
    """Classify IFS work centers by the approved P1/P2/P3 description prefix."""
    match = BUILDING_RE.match(description or "")
    return match.group(1).upper() if match else None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FloorMapDataError(f"Could not load {path.name}: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FloorMapDataError(message)


def _validate_catalog(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    _require(raw.get("schema_version") == 1, "Unsupported work-center catalog schema")
    catalog: dict[str, dict[str, Any]] = {}
    for row in raw.get("work_centers", []):
        wc = str(row.get("wc") or "").strip()
        _require(wc, "Catalog work center is missing its code")
        _require(wc not in catalog, f"Duplicate catalog work center: {wc}")
        building = str(row.get("building") or "").upper()
        _require(building in {"P1", "P2", "P3", "P4"}, f"Invalid catalog building for {wc}")
        catalog[wc] = dict(row, wc=wc, building=building)
    return catalog


def _validate_map(raw: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    _require(raw.get("schema_version") == 1, "Unsupported floor-map schema")
    floors: dict[str, dict[str, Any]] = {}
    for floor in raw.get("floors", []):
        floor_id = str(floor.get("id") or "").strip()
        box = floor.get("view_box")
        _require(floor_id and floor_id not in floors, "Floor IDs must be unique")
        _require(isinstance(box, list) and len(box) == 4 and box[2] > box[0] and box[3] > box[1],
                 f"Invalid view box for {floor_id}")
        _require(bool(floor.get("asset")), f"Missing floor-plan asset for {floor_id}")
        floors[floor_id] = dict(floor, id=floor_id)

    seen: set[str] = set()
    placements: list[dict[str, Any]] = []
    for row in raw.get("placements", []):
        wc = str(row.get("wc") or "").strip()
        floor_id = str(row.get("floor_id") or "").strip()
        _require(wc and wc not in seen, f"Duplicate fixed placement: {wc}")
        _require(floor_id in floors, f"Unknown floor ID for {wc}")
        _require(row.get("resource_kind") == "fixed", f"Placement {wc} must be fixed")
        _require(bool(row.get("label")), f"Missing display label for {wc}")
        x, y = row.get("x"), row.get("y")
        box = floors[floor_id]["view_box"]
        _require(isinstance(x, (int, float)) and isinstance(y, (int, float)), f"Missing coordinates for {wc}")
        _require(box[0] <= x <= box[2] and box[1] <= y <= box[3], f"Out-of-bounds placement for {wc}")
        seen.add(wc)
        placements.append(dict(row, wc=wc, floor_id=floor_id))

    resources: list[dict[str, Any]] = []
    for row in raw.get("resources", []):
        wc = str(row.get("wc") or "").strip()
        kind = row.get("resource_kind")
        _require(wc and wc not in seen, f"Duplicate non-point resource: {wc}")
        _require(kind in VALID_RESOURCE_KINDS - {"fixed"}, f"Invalid resource kind for {wc}")
        _require(bool(row.get("label")), f"Missing display label for {wc}")
        seen.add(wc)
        resources.append(dict(row, wc=wc))
    return floors, tuple(placements), tuple(resources)


@lru_cache(maxsize=1)
def load_facility_map() -> FacilityMap:
    """Load the reviewed, display-only map model from versioned JSON files."""
    catalog = _validate_catalog(_read_json(CATALOG_PATH))
    floors, placements, resources = _validate_map(_read_json(MAP_PATH))
    return FacilityMap(catalog=catalog, floors=floors, placements=placements, resources=resources)


def clear_facility_map_cache() -> None:
    load_facility_map.cache_clear()
