"""Compile immutable scheduler profiles from the resource registry."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import routers as R
from app.engines import rtg_wrapper as WRAPPER
from app.engines.router_registry import registry
from app.models import (
    OperationResourceBinding,
    ResourceCapacityVersion,
    ResourcePool,
    SimulationSnapshot,
    SimulationSnapshotEpoch,
)
from app.services.resource_registry import (
    CoverageIssue,
    add_assumption,
    add_binding,
    add_capacity_version,
    create_pool,
    resource_coverage,
)


REPLAY_SERIALIZER_VERSION = 1
REPLAY_ENGINE_VERSION = "capacity_engine.v1"


@dataclass(frozen=True)
class CompiledResourceProfile:
    mode: str
    pools: dict
    wc_to_pool: dict[str, str]
    requirements: dict[str, tuple]
    external_load: dict
    assumptions: tuple[int, ...]
    readiness: str
    unresolved: tuple[CoverageIssue, ...]
    snapshot_hash: str
    snapshot_id: int
    epoch_ids: dict[str, int]
    scheduler_profile: dict


@dataclass(frozen=True)
class ReplayVerification:
    snapshot_id: int
    content_hash: str
    input_hash: str
    result_hash: str
    exact_match: bool


def _as_date(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def _legacy_programs() -> list[str]:
    return [code for code in ("ELEV", "RAD", "AEGIS") if code in registry.programs]


async def seed_legacy_resources(db: AsyncSession) -> dict:
    """Copy current router capacity into one-to-one DB shadow pools.

    Idempotency is keyed by the exact ``LEGACY:{program}:{wc}`` or cure-station pool code. Existing
    approved seeds are never updated in place; a renamed program/WC produces a distinct draftable
    identity and corrected capacity must be introduced through assumption/version supersession.
    """
    existing_codes = set((await db.execute(select(ResourcePool.code))).scalars().all())
    created_pools = created_bindings = 0
    effective_from = date(2026, 8, 19)
    for program in _legacy_programs():
        operations = list(registry.ops(program))
        valid_ops = {int(op[0]) for op in operations}
        for wc in sorted({op[2] for op in operations}):
            code = f"LEGACY:{program}:{wc}"
            if code in existing_codes:
                continue
            pool = await create_pool(
                db, code=code, site="59", name=f"Legacy {program} {wc}",
                resource_type="LABOR", capacity_unit="HOURS", work_center_no=wc,
            )
            schedule = dict(R.WC_SHIFT.get((program, wc), R.DEFAULT_SHIFT))
            assumption = await add_assumption(
                db, subject_type="POOL", subject_key=code, parameter="shift_capacity",
                value=schedule, unit="HOURS_PER_SHIFT", basis="MEASURED_ACTUAL",
                approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
                effective_from=effective_from, evidence_source="routers.WC_SHIFT legacy seed",
                evidence_count=11, minimum_evidence_count=1,
                owner="TwinWorks legacy model", approver="TwinWorks migration",
            )
            await add_capacity_version(
                db, pool_id=pool.id, effective_from=effective_from, status="APPROVED",
                capacity_scope="GROSS_SITE", capacity_schedule=schedule,
                assumption_id=assumption.id,
            )
            for op in operations:
                if op[2] != wc:
                    continue
                await add_binding(
                    db, program=program, pool_id=pool.id, acquire_op=int(op[0]),
                    requirement_mode="EFFORT", quantity=1.0, demand_source="LABOR",
                    release_event="OP_COMPLETE", status="APPROVED",
                    valid_operations=valid_ops,
                )
                created_bindings += 1
            existing_codes.add(code)
            created_pools += 1

    for station, slots in sorted(R.CURE_STATION_CAPACITIES.items()):
        code = f"LEGACY:CURE:{station}"
        if code in existing_codes:
            continue
        pool = await create_pool(
            db, code=code, site="59", name=f"Legacy {station}",
            resource_type="CURE_STATION", capacity_unit="SLOTS",
        )
        assumption = await add_assumption(
            db, subject_type="POOL", subject_key=code, parameter="slot_count",
            value=int(slots), unit="SLOTS", basis="OWNER_CONFIRMED",
            approval_status="APPROVED", commitment_grade="COMMITMENT_READY",
            effective_from=effective_from, evidence_source="routers.CURE_STATION_CAPACITIES",
            owner="TwinWorks legacy model", approver="TwinWorks migration",
        )
        await add_capacity_version(
            db, pool_id=pool.id, effective_from=effective_from, status="APPROVED",
            capacity_scope="GROSS_SITE", slot_count=int(slots),
            assumption_id=assumption.id,
        )
        existing_codes.add(code)
        created_pools += 1
    await db.flush()
    return {"created_pools": created_pools, "created_bindings": created_bindings}


def _scheduler_profile_base(programs: list[str]) -> dict:
    return {
        "crew_by_program": {code: dict(registry.spec(code).crew_by_op) for code in programs},
        "dpas_programs": {code for code in programs if registry.spec(code).dpas},
        "shift_budgets": {},
        "budget_programs": list(programs),
        "shared_wcs": WRAPPER.shared_wcs(),
        "cure_station_capacities": dict(R.CURE_STATION_CAPACITIES),
        "cure_station_rules": dict(R.CURE_STATION_RULES),
        "parallel_cure_gates": dict(R.PARALLEL_CURE_GATES),
    }


def _jsonable_scheduler(profile: dict) -> dict:
    return {
        "crew_by_program": {
            code: {str(op): value for op, value in sorted(rows.items())}
            for code, rows in sorted(profile["crew_by_program"].items())
        },
        "dpas_programs": sorted(profile["dpas_programs"]),
        "shift_budgets": {
            f"{program}|{wc}": {str(shift): value for shift, value in sorted(shifts.items())}
            for (program, wc), shifts in sorted(profile["shift_budgets"].items())
        },
        "budget_programs": list(profile["budget_programs"]),
        "shared_wcs": sorted(profile["shared_wcs"]),
        "cure_station_capacities": dict(sorted(profile["cure_station_capacities"].items())),
        "cure_station_rules": [
            [program, opno, label, station]
            for (program, opno, label), station in sorted(profile["cure_station_rules"].items())
        ],
        "parallel_cure_gates": dict(sorted(profile["parallel_cure_gates"].items())),
    }


def _scheduler_from_jsonable(profile: dict) -> dict:
    return {
        "crew_by_program": {
            code: {int(op): value for op, value in rows.items()}
            for code, rows in profile["crew_by_program"].items()
        },
        "dpas_programs": set(profile["dpas_programs"]),
        "shift_budgets": {
            tuple(key.split("|", 1)): {int(shift): value for shift, value in rows.items()}
            for key, rows in profile["shift_budgets"].items()
        },
        "budget_programs": list(profile["budget_programs"]),
        "shared_wcs": set(profile["shared_wcs"]),
        "cure_station_capacities": dict(profile["cure_station_capacities"]),
        "cure_station_rules": {
            (program, int(opno), label): station
            for program, opno, label, station in profile["cure_station_rules"]
        },
        "parallel_cure_gates": dict(profile["parallel_cure_gates"]),
    }


def _canonical_json(value) -> str:
    def convert(item):
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        raise TypeError(f"Unsupported replay value: {type(item).__name__}")

    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False, default=convert,
    )


def _hash_json(value) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _serialize_units(units_by_program: dict) -> dict:
    return {
        program: [
            {
                "serial": unit["serial"], "so": unit["so"],
                "maxop": unit.get("maxop"),
                "commit": (unit["commit"].isoformat() if unit.get("commit") else None),
                "program": unit["program"],
            }
            for unit in sorted(units, key=lambda item: (item["serial"], item["so"]))
        ]
        for program, units in sorted(units_by_program.items())
    }


def _serialize_results(results: dict) -> dict:
    return {
        serial: {
            "finish": row["finish"].isoformat(),
            "op_dt": {str(key): value.isoformat()
                      for key, value in sorted(row.get("op_dt", {}).items())},
            "cure_dt": {str(key): value.isoformat()
                        for key, value in sorted(row.get("cure_dt", {}).items())},
        }
        for serial, row in sorted(results.items())
    }


async def verify_snapshot_integrity(db: AsyncSession, snapshot_id: int) -> dict:
    """Re-hash a stored snapshot and verify every materialized epoch reference."""
    snapshot = await db.get(SimulationSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("Simulation snapshot not found")
    payload = json.loads(snapshot.profile_json)
    actual_hash = hashlib.sha256(snapshot.profile_json.encode("utf-8")).hexdigest()
    if actual_hash != snapshot.content_hash:
        raise RuntimeError("Simulation snapshot content hash does not match stored payload")
    profile = payload["profile"] if payload.get("schema_version") == 3 else payload
    epoch_payload = profile.get("epochs", {})
    refs = (await db.execute(select(SimulationSnapshotEpoch).where(
        SimulationSnapshotEpoch.simulation_snapshot_id == snapshot_id))).scalars().all()
    if set(epoch_payload) != {row.program for row in refs}:
        raise RuntimeError("Simulation snapshot epoch references do not match payload")
    from app.models import ModelEpoch
    for ref in refs:
        epoch = await db.get(ModelEpoch, ref.model_epoch_id)
        expected = epoch_payload[ref.program]
        if (epoch is None or epoch.epoch_key != expected["epoch_key"]
                or epoch.definition_hash != expected["definition_hash"]):
            raise RuntimeError("Simulation snapshot epoch definition does not match payload")
    return {
        "snapshot_id": snapshot.id,
        "content_hash": actual_hash,
        "schema_version": payload.get("schema_version"),
        "replayable": payload.get("schema_version") == 3,
    }


async def persist_replay_snapshot(db: AsyncSession, *, base_snapshot_id: int,
                                  units_by_program: dict, results: dict,
                                  engine_version: str = REPLAY_ENGINE_VERSION) -> SimulationSnapshot:
    """Wrap an immutable profile with the exact run inputs and expected result."""
    base = await db.get(SimulationSnapshot, base_snapshot_id)
    if base is None:
        raise ValueError("Base simulation snapshot not found")
    await verify_snapshot_integrity(db, base.id)
    profile = json.loads(base.profile_json)
    if profile.get("schema_version") == 3:
        raise ValueError("Replay snapshots cannot be nested")
    inputs = _serialize_units(units_by_program)
    expected_result = _serialize_results(results)
    replay = {
        "engine_version": engine_version,
        "serializer_version": REPLAY_SERIALIZER_VERSION,
        "hash_algorithm": "sha256",
        "inputs": inputs,
        "input_hash": _hash_json(inputs),
        "expected_result": expected_result,
        "result_hash": _hash_json(expected_result),
    }
    payload = {"schema_version": 3, "profile": profile, "replay": replay}
    profile_json = _canonical_json(payload)
    content_hash = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()
    existing = await db.scalar(select(SimulationSnapshot).where(
        SimulationSnapshot.content_hash == content_hash))
    if existing is not None:
        await verify_snapshot_integrity(db, existing.id)
        return existing
    row = SimulationSnapshot(
        as_of=base.as_of, horizon_end=base.horizon_end, mode=base.mode,
        profile_json=profile_json, assumption_ids_json=base.assumption_ids_json,
        external_snapshot_id=base.external_snapshot_id, readiness=base.readiness,
        unresolved_json=base.unresolved_json, content_hash=content_hash,
    )
    db.add(row)
    await db.flush()
    refs = (await db.execute(select(SimulationSnapshotEpoch).where(
        SimulationSnapshotEpoch.simulation_snapshot_id == base.id))).scalars().all()
    for ref in refs:
        db.add(SimulationSnapshotEpoch(
            simulation_snapshot_id=row.id, program=ref.program,
            model_epoch_id=ref.model_epoch_id,
        ))
    await db.flush()
    await verify_snapshot_integrity(db, row.id)
    return row


def _frozen_pool_groups(programs: list[str], profile: dict) -> list[list[str]]:
    epoch_defs = profile["epochs"]
    route_by_program = {
        program: epoch_defs[program]["definition"]["definition"]["routing"]
        for program in programs
    }
    wc_sets = {
        program: {row[2] for row in route_by_program[program]["ops"] if row[2]}
        for program in programs
    }
    plants = {
        program: epoch_defs[program]["definition"]["definition"].get("identity", {}).get(
            "plant", "")
        for program in programs
    }
    parent = {program: program for program in programs}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for index, left in enumerate(programs):
        for right in programs[index + 1:]:
            if wc_sets[left] & wc_sets[right] and plants[left] == plants[right]:
                parent[find(left)] = find(right)
    groups = {}
    for program in programs:
        groups.setdefault(find(program), []).append(program)
    return [sorted(group) for group in groups.values()]


async def replay_snapshot(db: AsyncSession, snapshot_id: int) -> ReplayVerification:
    """Re-run a schema-v3 snapshot solely from its frozen routing/profile/input payload."""
    snapshot = await db.get(SimulationSnapshot, snapshot_id)
    if snapshot is None:
        raise ValueError("Simulation snapshot not found")
    await verify_snapshot_integrity(db, snapshot_id)
    payload = json.loads(snapshot.profile_json)
    if payload.get("schema_version") != 3:
        raise ValueError("Simulation snapshot has no replay input/result envelope")
    profile = payload["profile"]
    replay = payload["replay"]
    if replay.get("engine_version") != REPLAY_ENGINE_VERSION:
        raise RuntimeError("Simulation replay engine version is not supported")
    if replay.get("serializer_version") != REPLAY_SERIALIZER_VERSION:
        raise RuntimeError("Simulation replay serializer version is not supported")
    if replay.get("hash_algorithm") != "sha256":
        raise RuntimeError("Simulation replay hash algorithm is not supported")
    if _hash_json(replay["inputs"]) != replay["input_hash"]:
        raise RuntimeError("Simulation replay input hash does not match")
    if _hash_json(replay["expected_result"]) != replay["result_hash"]:
        raise RuntimeError("Simulation replay result hash does not match")
    scheduler = _scheduler_from_jsonable(profile["scheduler_profile"])
    epoch_defs = profile["epochs"]
    ops_map = {}
    cures_map = {}
    units_by_program = {}
    for program, rows in replay["inputs"].items():
        route = epoch_defs[program]["definition"]["definition"]["routing"]
        ops_map[program] = [tuple(item) for item in route["ops"]]
        cures_map[program] = [tuple(item) for item in route["cures"]]
        units_by_program[program] = [
            {**item, "commit": date.fromisoformat(item["commit"])
             if item.get("commit") else None}
            for item in rows
        ]
    from app.engines.rtg_wrapper import run_sim
    actual = {}
    for group in _frozen_pool_groups(list(units_by_program), profile):
        units = [item for program in group for item in units_by_program[program]]
        if units:
            actual.update(run_sim(
                units, datetime.fromisoformat(profile["as_of"]),
                ops_map=ops_map, cures_map=cures_map, profile=scheduler,
            ))
    serialized = _serialize_results(actual)
    actual_hash = _hash_json(serialized)
    return ReplayVerification(
        snapshot_id=snapshot_id, content_hash=snapshot.content_hash,
        input_hash=replay["input_hash"], result_hash=actual_hash,
        exact_match=(actual_hash == replay["result_hash"]
                     and serialized == replay["expected_result"]),
    )


async def _persist_snapshot(db: AsyncSession, *, as_of: datetime, horizon_end: date,
                            mode: str, pools: dict, wc_to_pool: dict,
                            requirements: dict, assumptions: tuple[int, ...],
                            readiness: str, unresolved: tuple[CoverageIssue, ...],
                            scheduler_profile: dict, epoch_selections,
                            external_load: dict | None = None,
                            external_snapshot_id: int | None = None) -> tuple[str, int]:
    epochs = {
        program: {
            "epoch_key": selection.epoch.epoch_key,
            "definition_hash": selection.epoch.definition_hash,
            "definition": json.loads(selection.epoch.definition_json),
            "lifecycle_state": selection.state,
            "resource_mode": selection.epoch.resource_mode,
        }
        for program, selection in sorted(epoch_selections.items())
    }
    payload = {
        "schema_version": 2,
        "mode": mode,
        "as_of": as_of.isoformat(),
        "horizon_end": horizon_end.isoformat(),
        "epochs": epochs,
        "pools": pools,
        "wc_to_pool": wc_to_pool,
        "requirements": {key: list(value) for key, value in sorted(requirements.items())},
        "external_load": external_load or {},
        "assumptions": list(assumptions),
        "readiness": readiness,
        "unresolved": [issue.__dict__ for issue in unresolved],
        "scheduler_profile": _jsonable_scheduler(scheduler_profile),
    }
    profile_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(profile_json.encode("utf-8")).hexdigest()
    existing = (await db.execute(
        select(SimulationSnapshot).where(SimulationSnapshot.content_hash == content_hash)
    )).scalar_one_or_none()
    if existing is not None:
        await _verify_snapshot_epoch_links(db, existing.id, epoch_selections)
        return content_hash, existing.id
    row = SimulationSnapshot(
        as_of=as_of, horizon_end=horizon_end, mode=mode,
        profile_json=profile_json, assumption_ids_json=json.dumps(list(assumptions)),
        external_snapshot_id=external_snapshot_id,
        readiness=readiness,
        unresolved_json=json.dumps([issue.__dict__ for issue in unresolved], sort_keys=True),
        content_hash=content_hash,
    )
    db.add(row)
    await db.flush()
    for program, selection in sorted(epoch_selections.items()):
        db.add(SimulationSnapshotEpoch(
            simulation_snapshot_id=row.id, program=program,
            model_epoch_id=selection.epoch.id,
        ))
    await db.flush()
    await _verify_snapshot_epoch_links(db, row.id, epoch_selections)
    return content_hash, row.id


async def _verify_snapshot_epoch_links(db: AsyncSession, snapshot_id: int,
                                       epoch_selections) -> None:
    refs = (await db.execute(
        select(SimulationSnapshotEpoch).where(
            SimulationSnapshotEpoch.simulation_snapshot_id == snapshot_id)
    )).scalars().all()
    actual = {ref.program: ref.model_epoch_id for ref in refs}
    expected = {
        program: selection.epoch.id for program, selection in epoch_selections.items()
    }
    if actual != expected:
        raise RuntimeError(
            f"Simulation snapshot epoch references are incomplete: {actual} != {expected}")


async def compile_profile(db: AsyncSession, programs, as_of: datetime,
                          horizon_end: date, mode: str,
                          epoch_ids: dict[str, int] | None = None,
                          external_snapshot_id: int | None = None) -> CompiledResourceProfile:
    """Resolve legacy or DB-shadow inputs into one immutable scheduler snapshot."""
    programs = [code for code in programs if code in registry.programs]
    mode = mode.upper().replace("-", "_")
    if mode not in {"LEGACY", "DB_SHADOW", "DB_ACTIVE"}:
        raise ValueError(f"Unknown resource mode: {mode}")
    from app.services.model_epoch_service import resolve_epochs_for_run
    epoch_selections = await resolve_epochs_for_run(
        db, programs, requested=epoch_ids, mode=mode)
    if mode in {"DB_SHADOW", "DB_ACTIVE"}:
        from app.services.model_epoch_service import assert_candidate_definition_current
        await assert_candidate_definition_current(db, epoch_selections)
    programs = list(epoch_selections)
    pools: dict = {}
    wc_to_pool: dict[str, str] = {}
    requirements: dict[str, tuple] = {}
    assumptions: set[int] = set()
    unresolved: list[CoverageIssue] = []
    external_load = {}
    if mode == "LEGACY":
        scheduler_profile = WRAPPER.simulation_profile()
    else:
        scheduler_profile = _scheduler_profile_base(programs)
        pool_rows = (await db.execute(
            select(ResourcePool).where(ResourcePool.active.is_(True))
        )).scalars().all()
        pool_by_id = {row.id: row for row in pool_rows}
        bindings = (await db.execute(
            select(OperationResourceBinding).where(
                OperationResourceBinding.program.in_(programs),
                OperationResourceBinding.status == "APPROVED",
            )
        )).scalars().all()
        for binding in bindings:
            pool = pool_by_id.get(binding.pool_id)
            if pool is None:
                continue
            key = f"{binding.program}:{binding.acquire_op}"
            requirements.setdefault(key, tuple())
            requirements[key] += (pool.code,)
            if pool.work_center_no:
                wc_to_pool[f"{binding.program}:{pool.work_center_no}"] = pool.code
        used_pool_ids = {binding.pool_id for binding in bindings}
        for pool_id in sorted(used_pool_ids):
            pool = pool_by_id[pool_id]
            versions = (await db.execute(
                select(ResourceCapacityVersion).where(
                    ResourceCapacityVersion.pool_id == pool_id,
                    ResourceCapacityVersion.status == "APPROVED",
                    ResourceCapacityVersion.effective_from <= _as_date(as_of),
                )
            )).scalars().all()
            version = next((row for row in versions
                            if row.effective_to is None or row.effective_to >= _as_date(as_of)), None)
            if version is None:
                continue
            if version.assumption_id:
                assumptions.add(version.assumption_id)
            schedule = (json.loads(version.capacity_schedule_json)
                        if version.capacity_schedule_json else None)
            pools[pool.code] = {
                "site": pool.site, "name": pool.name, "resource_type": pool.resource_type,
                "capacity_unit": pool.capacity_unit, "work_center_no": pool.work_center_no,
                "effective_from": version.effective_from.isoformat(),
                "effective_to": version.effective_to.isoformat() if version.effective_to else None,
                "capacity_scope": version.capacity_scope,
                "capacity_schedule": schedule, "slot_count": version.slot_count,
                "assumption_id": version.assumption_id,
            }
            if pool.capacity_unit == "HOURS" and pool.work_center_no and schedule:
                for binding in (item for item in bindings if item.pool_id == pool_id):
                    scheduler_profile["shift_budgets"][(binding.program, pool.work_center_no)] = {
                        int(shift): float(value) for shift, value in schedule.items()
                    }
        for program in programs:
            unresolved.extend(await resource_coverage(db, program, _as_date(as_of)))
        if external_snapshot_id is not None:
            from app.services.external_load_governance import assess_external_snapshot
            assessment = await assess_external_snapshot(
                db, external_snapshot_id, as_of=_as_date(as_of), horizon_end=horizon_end)
            external_load = assessment.payload
            assumptions.update(assessment.assumption_ids)
            unresolved.extend(assessment.issues)
    readiness = ("INCOMPLETE" if any(item.severity == "MISSING" for item in unresolved)
                 else "PROVISIONAL" if unresolved else "COMPLETE")
    snapshot_hash, snapshot_id = await _persist_snapshot(
        db, as_of=as_of, horizon_end=horizon_end, mode=mode, pools=pools,
        wc_to_pool=wc_to_pool, requirements=requirements,
        assumptions=tuple(sorted(assumptions)), readiness=readiness,
        unresolved=tuple(unresolved), scheduler_profile=scheduler_profile,
        epoch_selections=epoch_selections, external_load=external_load,
        external_snapshot_id=external_snapshot_id,
    )
    return CompiledResourceProfile(
        mode=mode, pools=pools, wc_to_pool=wc_to_pool, requirements=requirements,
        external_load=external_load, assumptions=tuple(sorted(assumptions)), readiness=readiness,
        unresolved=tuple(unresolved), snapshot_hash=snapshot_hash,
        snapshot_id=snapshot_id,
        epoch_ids={program: selection.epoch.id
                   for program, selection in epoch_selections.items()},
        scheduler_profile=scheduler_profile,
    )
