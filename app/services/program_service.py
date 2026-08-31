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
PLANNING_BASES = {"PLAN_SLOTS", "CONTRACT_DATES", "NONE"}
_SEED_PLANNING = {
    "ELEV": ("PLAN_SLOTS", "RTG", "2026"),
    "RAD": ("PLAN_SLOTS", "RTG", "2026"),
    "AEGIS": ("CONTRACT_DATES", "Contract", None),
}


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
                code=r["code"], name=r["name"],
                plant=(r["plant"] if "plant" in r.keys() else ""),
                project_id=r["project_id"],
                part_nos=json.loads(r["part_nos"]),
                pack_op=r["pack_op"], ship_op=r["ship_op"], floor_op=r["floor_op"],
                ops=json.loads(r["ops_json"]), cures=json.loads(r["cures_json"]),
                milestones=json.loads(r["milestones_json"]),
                ceilings=json.loads(r["ceilings_json"]),
                crew_by_op={int(k): v for k, v in json.loads(r["crew_by_op_json"]).items()},
                dpas=bool(r["dpas"]), train_threshold=r["train_threshold"],
                rtg_source=r["rtg_source"], hand_split=bool(r["hand_split"]),
                hand_map=json.loads(r["hand_map_json"]),
                configured_planning_basis=(
                    r["configured_planning_basis"]
                    if "configured_planning_basis" in r.keys()
                    else _SEED_PLANNING.get(r["code"], ("NONE", None, None))[0]),
                plan_label=(
                    r["plan_label"] if "plan_label" in r.keys()
                    else _SEED_PLANNING.get(r["code"], ("NONE", None, None))[1]),
                plan_version=(
                    r["plan_version"] if "plan_version" in r.keys()
                    else _SEED_PLANNING.get(r["code"], ("NONE", None, None))[2]))
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


def planning_meta(code: str) -> dict:
    """Configured delivery-target semantics; lifecycle effectiveness is resolved separately."""
    code = code.upper()
    specs = load_specs()
    if specs and code in specs:
        row = specs[code]
        return {
            "configured_planning_basis": row.get("configured_planning_basis", "NONE"),
            "plan_label": row.get("plan_label"),
            "plan_source": row.get("rtg_source"),
            "plan_version": row.get("plan_version"),
        }
    basis, label, version = _SEED_PLANNING.get(code, ("NONE", None, None))
    return {
        "configured_planning_basis": basis,
        "plan_label": label,
        "plan_source": None,
        "plan_version": version,
    }


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
    # plant is the pooling boundary: ELEV+AEGIS = Plant 2 (share paint/autoclave), RAD = Plant 3
    plants = {"ELEV": "Plant 2", "AEGIS": "Plant 2", "RAD": "Plant 3"}
    thresholds = settings.n_train_threshold
    n = 0
    for code in _SEED_ORDER:
        proj, parts = _SEED_IFS[code]
        db.add(Program(
            code=code, name=names[code], plant=plants.get(code, ""),
            project_id=proj, part_nos=json.dumps(parts),
            pack_op=PACK_OP[code], ship_op=SHIP_OP[code], floor_op=FLOOR_OP[code],
            ops_json=json.dumps(ops_by[code]), cures_json=json.dumps(cures_by[code]),
            milestones_json=json.dumps(ms_by[code]),
            ceilings_json=json.dumps(MILESTONE_CEILINGS[code]),
            crew_by_op_json=json.dumps(R.CREW_BY_OP),
            dpas=(code in R.DPAS_PROGRAMS),
            train_threshold=thresholds.get(code, settings.n_train_threshold_default),
            rtg_source=("rtg_targets.json" if code in {"ELEV", "RAD"} else None),
            configured_planning_basis=_SEED_PLANNING[code][0],
            plan_label=_SEED_PLANNING[code][1], plan_version=_SEED_PLANNING[code][2],
            hand_split=(code == "ELEV"), hand_map_json="{}",
            active=True, created_at=datetime.utcnow(), updated_at=datetime.utcnow()))
        n += 1
    await db.commit()
    invalidate_cache()
    _export_snapshot_all()
    return dict(seeded=True, rows=n)


async def create_program(db: AsyncSession, *, code, name, plant, project_id, part_nos,
                         ops, cures=None, milestones=None, ceilings=None, crew_by_op=None,
                         pack_op=None, ship_op=None, floor_op=0, dpas=False,
                         train_threshold=25, hand_split=False, hand_map=None,
                         rtg_source=None,
                         configured_planning_basis="NONE", plan_label=None,
                         plan_version=None,
                         epoch_metadata=None,
                         created_by="TwinWorks program onboarding") -> dict:
    """Create a program or stage an immutable candidate for a published program.

    A new/unpublished program updates the registry so observation can start. Reconfiguring a
    published program stores only a candidate epoch; publication is a separate governed action.
    """
    from app.engines import router_registry as RR
    from app.services import model_epoch_service as EPOCHS
    code = code.strip().upper()
    ops = [list(o) for o in ops]
    if not code or not ops:
        raise ValueError("code and at least one op are required")
    maxop = max(int(o[0]) for o in ops)
    ship_op = ship_op or maxop
    pack_op = pack_op or ship_op
    milestones = milestones or [["ALL", "All Ops"]]
    ceilings = ceilings or [[milestones[0][0], maxop]]
    configured_planning_basis = (configured_planning_basis or "NONE").upper()
    if configured_planning_basis not in PLANNING_BASES:
        raise ValueError(f"invalid planning basis: {configured_planning_basis}")
    if configured_planning_basis == "PLAN_SLOTS" and not (plan_label or "").strip():
        raise ValueError("PLAN_SLOTS requires a plan label")
    config = dict(
        code=code, name=name or code, plant=plant or "", project_id=project_id or "",
        part_nos=list(part_nos or []),
        pack_op=pack_op, ship_op=ship_op, floor_op=floor_op or 0,
        ops=ops, cures=list(cures or []), milestones=milestones, ceilings=ceilings,
        crew_by_op={str(k): v for k, v in (crew_by_op or {}).items()},
        dpas=bool(dpas), train_threshold=int(train_threshold or 25),
        rtg_source=rtg_source, hand_split=bool(hand_split),
        configured_planning_basis=configured_planning_basis,
        plan_label=((plan_label or "").strip() or None),
        plan_version=((plan_version or "").strip() or None),
        hand_map=dict(hand_map or {}), active=True,
    )
    row = dict(
        code=config["code"], name=config["name"], plant=config["plant"],
        project_id=config["project_id"], part_nos=json.dumps(config["part_nos"]),
        pack_op=config["pack_op"], ship_op=config["ship_op"], floor_op=config["floor_op"],
        ops_json=json.dumps(config["ops"]), cures_json=json.dumps(config["cures"]),
        milestones_json=json.dumps(config["milestones"]),
        ceilings_json=json.dumps(config["ceilings"]),
        crew_by_op_json=json.dumps(config["crew_by_op"]), dpas=config["dpas"],
        train_threshold=config["train_threshold"], rtg_source=config["rtg_source"],
        configured_planning_basis=config["configured_planning_basis"],
        plan_label=config["plan_label"], plan_version=config["plan_version"],
        hand_split=config["hand_split"], hand_map_json=json.dumps(config["hand_map"]), active=True,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    existing = (await db.execute(select(Program).where(Program.code == code))).scalar_one_or_none()
    await EPOCHS.ensure_legacy_epochs(db, RR.registry.programs)
    published = await EPOCHS.published_epoch(db, code)
    staged_update = existing is not None and published is not None
    if existing and not staged_update:
        for k, v in row.items():
            if k != "created_at":
                setattr(existing, k, v)
    elif existing is None:
        db.add(Program(**row))
    await db.flush()
    epoch = await EPOCHS.create_epoch(
        db, program=code, label=f"{name or code} candidate",
        epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
        definition={
            "program_config": config,
            "source_metadata": dict(epoch_metadata or {}),
        }, created_by=created_by,
        predecessor_epoch_id=(published.epoch.id if published else None),
    )
    await db.commit()
    if not staged_update:
        invalidate_cache()
        RR.rebuild()
        _export_snapshot_all()
    return dict(
        created=(existing is None), staged=True, active_registry_changed=not staged_update,
        code=code, ops=len(ops), epoch_id=epoch.id, epoch_key=epoch.epoch_key,
        lifecycle_state=(await EPOCHS.current_transition(db, epoch.id)).to_state,
    )


def _export_snapshot_all():
    """Export every active program to a timestamped JSON snapshot (diffable history; export-only)."""
    specs = load_specs()
    if not specs:
        return
    SNAP_DIR.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    for code, s in specs.items():
        (SNAP_DIR / f"{code}_{ts}.json").write_text(json.dumps(s, indent=2, default=str))
