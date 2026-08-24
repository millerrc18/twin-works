"""Program config service — the DB-backed source for program definitions.

When the `program` table has a row for a code, it is authoritative; otherwise the app falls back
to the hardcoded routers.py constants (migration safety, flag `RTG_PROGRAM_SOURCE=db|routers`).
This module owns: seed-the-3-from-routers, load specs (sync, cached), IFS metadata (project/parts),
and the snapshot export on save. `router_registry` consumes `load_specs()` to build ProgramSpecs.
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Program

BASE = Path(__file__).resolve().parent.parent.parent
SNAP_DIR = BASE / "program_snapshots"

# IFS metadata for the 3 seed programs (was live_source.PROG_IFS)
_SEED_IFS = {
    "ELEV": ("531335", ["72P5520501-029P01", "72P5520502-029P01"]),
    "RAD": ("C48178", ["3700ED0001-101"]),
    "AEGIS": ("530349", ["00999000563"]),
}
_SEED_ORDER = ["ELEV", "RAD", "AEGIS"]


def _db_path() -> str:
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


# ---------- sync read (hot path; router_registry + live_source use this) ----------
_cache = {"mtime": None, "rows": None}


def _source() -> str:
    return getattr(settings, "program_source", "db")


def load_specs() -> dict:
    """Return {code: dict(...)} from the program table, or {} if empty/absent/flag=routers.
    Cached on DB mtime. {} means 'fall back to routers.py'."""
    if _source() == "routers":
        return {}
    path = _db_path()
    p = Path(path)
    if not p.exists():
        return {}
    mt = p.stat().st_mtime
    if _cache["mtime"] == mt and _cache["rows"] is not None:
        return _cache["rows"]
    out = {}
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        for r in con.execute("SELECT * FROM program WHERE active=1"):
            out[r["code"]] = dict(
                code=r["code"], name=r["name"], project_id=r["project_id"],
                part_nos=json.loads(r["part_nos"]),
                pack_op=r["pack_op"], ship_op=r["ship_op"], floor_op=r["floor_op"],
                ops=json.loads(r["ops_json"]), cures=json.loads(r["cures_json"]),
                milestones=json.loads(r["milestones_json"]),
                ceilings=json.loads(r["ceilings_json"]),
                crew_by_op={int(k): v for k, v in json.loads(r["crew_by_op_json"]).items()},
                dpas=bool(r["dpas"]), train_threshold=r["train_threshold"],
                rtg_source=r["rtg_source"], hand_split=bool(r["hand_split"]),
                hand_map=json.loads(r["hand_map_json"]))
        con.close()
    except sqlite3.OperationalError:
        return {}
    _cache["mtime"], _cache["rows"] = mt, out
    return out


def invalidate_cache():
    _cache["mtime"], _cache["rows"] = None, None


def ifs_meta() -> dict:
    """{code: (project_id, [part_nos])} from DB rows, else the seed defaults."""
    specs = load_specs()
    if specs:
        return {c: (s["project_id"], s["part_nos"]) for c, s in specs.items()}
    return dict(_SEED_IFS)


_SEED_NAMES = {"ELEV": "G500 Elevator", "RAD": "Aeronose Radome", "AEGIS": "Aegis Reflector"}


def program_order() -> list:
    specs = load_specs()
    if specs:
        # seed order first, then any new programs alphabetically
        extra = sorted(c for c in specs if c not in _SEED_ORDER)
        return [c for c in _SEED_ORDER if c in specs] + extra
    return list(_SEED_ORDER)


def names() -> dict:
    """{code: display name} from DB rows, else the seed defaults."""
    specs = load_specs()
    if specs:
        return {c: s["name"] for c, s in specs.items()}
    return dict(_SEED_NAMES)


def name(code: str) -> str:
    return names().get(code, code)


def threshold(code: str) -> int:
    specs = load_specs()
    if specs and code in specs:
        return specs[code]["train_threshold"]
    return settings.n_train_threshold.get(code, settings.n_train_threshold_default)


# ---------- async writes ----------
async def is_seeded(db: AsyncSession) -> bool:
    return (await db.execute(select(Program.code).limit(1))).first() is not None


async def seed_from_routers(db: AsyncSession, force: bool = False) -> dict:
    """Copy the 3 hardcoded programs from routers.py into the program table (one-time).
    Behavior stays identical because the same constants are used. No-op if seeded unless force."""
    if not force and await is_seeded(db):
        return dict(seeded=False, reason="already populated")
    import routers as R
    from app.engines.router_registry import MILESTONE_CEILINGS, PACK_OP, SHIP_OP, FLOOR_OP
    ops_by = {"ELEV": R.ELEVATOR_OPS, "RAD": R.RADOME_OPS, "AEGIS": R.AEGIS_OPS}
    cures_by = {"ELEV": R.ELEVATOR_CURES, "RAD": R.RADOME_CURES, "AEGIS": R.AEGIS_CURES}
    ms_by = {"ELEV": R.ELEV_MILESTONES, "RAD": R.RAD_MILESTONES, "AEGIS": R.AEGIS_MILESTONES}
    names = {"ELEV": "G500 Elevator", "RAD": "Aeronose Radome", "AEGIS": "Aegis Reflector"}
    thresholds = settings.n_train_threshold
    n = 0
    for code in _SEED_ORDER:
        proj, parts = _SEED_IFS[code]
        db.add(Program(
            code=code, name=names[code], project_id=proj, part_nos=json.dumps(parts),
            pack_op=PACK_OP[code], ship_op=SHIP_OP[code], floor_op=FLOOR_OP[code],
            ops_json=json.dumps(ops_by[code]), cures_json=json.dumps(cures_by[code]),
            milestones_json=json.dumps(ms_by[code]),
            ceilings_json=json.dumps(MILESTONE_CEILINGS[code]),
            crew_by_op_json=json.dumps(R.CREW_BY_OP),
            dpas=(code in R.DPAS_PROGRAMS),
            train_threshold=thresholds.get(code, settings.n_train_threshold_default),
            rtg_source=None, hand_split=(code == "ELEV"), hand_map_json="{}",
            active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        n += 1
    await db.commit()
    invalidate_cache()
    _export_snapshot_all()
    return dict(seeded=True, rows=n)


def _export_snapshot_all():
    """Export every active program to a timestamped JSON snapshot (diffable history; export-only)."""
    specs = load_specs()
    if not specs:
        return
    SNAP_DIR.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    for code, s in specs.items():
        (SNAP_DIR / f"{code}_{ts}.json").write_text(json.dumps(s, indent=2, default=str))
