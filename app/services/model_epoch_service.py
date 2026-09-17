"""Append-only program lifecycle, model epoch, and publication governance."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.router_registry import registry
from app.models import (
    ModelEpoch,
    ModelEpochTransition,
    OperationResourceBinding,
    ProgramEpochActivation,
    ResourceCapacityVersion,
    ResourcePool,
)


LIFECYCLE_STATES = {
    "DRAFT", "OBSERVE", "PROVISIONAL", "COMMITMENT_READY", "PAUSED",
    "ARCHIVED", "DEPRECATED",
}
AUTHORITY_ROLES = {"DATA_ADMIN", "IE_FLOOR", "PROGRAM_SCHEDULING"}
EPOCH_KINDS = {"LEGACY_BASELINE", "CANDIDATE"}
RESOURCE_MODES = {"LEGACY", "DB_SHADOW", "DB_ACTIVE"}
RUNNABLE_STATES = {"OBSERVE", "PROVISIONAL", "COMMITMENT_READY"}
LEGACY_BASELINE_PROGRAMS = {"ELEV", "RAD", "AEGIS"}

ALLOWED_TRANSITIONS = {
    ("DRAFT", "OBSERVE"): "DATA_ADMIN",
    ("DRAFT", "ARCHIVED"): "DATA_ADMIN",
    ("OBSERVE", "PROVISIONAL"): "IE_FLOOR",
    ("OBSERVE", "PAUSED"): "IE_FLOOR",
    ("OBSERVE", "ARCHIVED"): "DATA_ADMIN",
    ("PROVISIONAL", "COMMITMENT_READY"): "PROGRAM_SCHEDULING",
    ("PROVISIONAL", "OBSERVE"): "IE_FLOOR",
    ("PROVISIONAL", "PAUSED"): "IE_FLOOR",
    ("COMMITMENT_READY", "PAUSED"): "PROGRAM_SCHEDULING",
    ("COMMITMENT_READY", "DEPRECATED"): "PROGRAM_SCHEDULING",
    ("PAUSED", "OBSERVE"): "IE_FLOOR",
    ("PAUSED", "ARCHIVED"): "DATA_ADMIN",
}

IMMUTABLE_AUDIT_TABLES = {
    "model_epoch", "model_epoch_transition", "program_epoch_activation",
    "accuracy_summary_log",
    "external_load_snapshot", "external_load_row", "simulation_snapshot",
    "observation_quarantine_event", "resource_availability_event",
    "simulation_snapshot_epoch", "forecast_constraint_event",
}


def expected_epoch_trigger_names() -> set[str]:
    names = {
        "trg_model_epoch_transition_validate",
        "trg_program_epoch_activation_validate",
        "trg_observation_quarantine_transition_validate",
        "trg_resource_availability_event_validate",
        "trg_resource_availability_capacity_validate",
        "trg_model_assumption_approved_immutable",
        "trg_model_assumption_evidence_immutable",
        "trg_resource_capacity_approved_immutable",
        "trg_assumption_review_resolution_immutable",
        "trg_assumption_review_delete_immutable",
    }
    for table in IMMUTABLE_AUDIT_TABLES:
        names.update({
            f"trg_{table}_append_only_insert",
            f"trg_{table}_append_only_update",
            f"trg_{table}_append_only_delete",
        })
    return names


async def assert_governance_integrity(db: AsyncSession, *, check_pragmas: bool = True) -> None:
    """Fail fast when SQLite lifecycle protections are missing from a connection/schema."""
    if db.bind.dialect.name != "sqlite":
        return
    if check_pragmas:
        foreign_keys = await db.scalar(text("PRAGMA foreign_keys"))
        recursive = await db.scalar(text("PRAGMA recursive_triggers"))
        if foreign_keys != 1 or recursive != 1:
            raise RuntimeError("SQLite governance pragmas are not enabled")
    installed = set((await db.execute(text(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ))).scalars().all())
    missing = expected_epoch_trigger_names() - installed
    if missing:
        raise RuntimeError(f"Missing governance triggers: {sorted(missing)}")


class ModelEpochError(ValueError):
    pass


class InvalidEpochTransition(ModelEpochError):
    pass


class EpochNotPublishable(ModelEpochError):
    pass


class EpochSelectionError(ModelEpochError):
    pass


@dataclass(frozen=True)
class EpochSelection:
    epoch: ModelEpoch
    transition: ModelEpochTransition

    @property
    def state(self) -> str:
        return self.transition.to_state


@dataclass(frozen=True)
class IncumbentParityReport:
    exact_match: bool
    programs: tuple[str, ...]
    unit_counts: dict[str, int]
    candidate_epoch_ids: dict[str, int]
    legacy_snapshot_id: int
    shadow_snapshot_id: int
    legacy_result_hash: str
    shadow_result_hash: str
    mismatched_serials: tuple[str, ...]
    open_review_debt: int
    review_debt_by_type: dict[str, int]


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported epoch JSON value: {type(value).__name__}")


def _canonical_json(value) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False, default=_json_default,
    )


def _required_text(value: str, field: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ModelEpochError(f"{field} is required")
    return value


def _definition_record(*, program: str, epoch_kind: str, resource_mode: str,
                       predecessor: ModelEpoch | None, definition) -> dict:
    return {
        "schema_version": 1,
        "program": program,
        "epoch_kind": epoch_kind,
        "resource_mode": resource_mode,
        "predecessor_epoch_key": predecessor.epoch_key if predecessor else None,
        "definition": definition,
    }


async def current_transition(db: AsyncSession, epoch_id: int) -> ModelEpochTransition:
    row = (await db.execute(
        select(ModelEpochTransition)
        .where(ModelEpochTransition.epoch_id == epoch_id)
        .order_by(ModelEpochTransition.sequence.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        raise ModelEpochError("Model epoch has no lifecycle transition")
    return row


async def create_epoch(db: AsyncSession, *, program: str, label: str,
                       epoch_kind: str, resource_mode: str, definition,
                       created_by: str, predecessor_epoch_id: int | None = None,
                       epoch_key: str | None = None) -> ModelEpoch:
    """Create an immutable epoch definition and its initial DRAFT transition."""
    program = _required_text(program, "program").upper()
    label = _required_text(label, "label")
    created_by = _required_text(created_by, "created_by")
    epoch_kind = epoch_kind.upper()
    resource_mode = resource_mode.upper().replace("-", "_")
    if epoch_kind not in EPOCH_KINDS:
        raise ModelEpochError(f"Invalid epoch kind: {epoch_kind}")
    if resource_mode not in RESOURCE_MODES:
        raise ModelEpochError(f"Invalid resource mode: {resource_mode}")
    if not isinstance(definition, Mapping):
        raise ModelEpochError("definition must be a JSON object")
    predecessor = None
    if predecessor_epoch_id is not None:
        predecessor = await db.get(ModelEpoch, predecessor_epoch_id)
        if predecessor is None or predecessor.program != program:
            raise ModelEpochError("Predecessor must belong to the same program")

    payload = _definition_record(
        program=program, epoch_kind=epoch_kind, resource_mode=resource_mode,
        predecessor=predecessor, definition=definition,
    )
    try:
        definition_json = _canonical_json(payload)
    except (TypeError, ValueError) as exc:
        raise ModelEpochError("definition must contain deterministic JSON values") from exc
    definition_hash = hashlib.sha256(definition_json.encode("utf-8")).hexdigest()
    existing = (await db.execute(
        select(ModelEpoch).where(
            ModelEpoch.program == program,
            ModelEpoch.definition_hash == definition_hash,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    key = epoch_key or f"{program}:{epoch_kind}:{uuid4().hex[:12]}"
    row = ModelEpoch(
        epoch_key=key, program=program, epoch_kind=epoch_kind,
        predecessor_epoch_id=predecessor_epoch_id, label=label,
        resource_mode=resource_mode, definition_json=definition_json,
        definition_hash=definition_hash, created_by=created_by,
    )
    db.add(row)
    await db.flush()
    db.add(ModelEpochTransition(
        epoch_id=row.id, sequence=1, from_state=None, to_state="DRAFT",
        authority_role="DATA_ADMIN", actor=created_by,
        rationale="Immutable model epoch created", evidence_json="{}",
    ))
    await db.flush()
    return row


async def transition_epoch(db: AsyncSession, epoch_id: int, *, to_state: str,
                           actor: str, authority_role: str, rationale: str,
                           evidence: dict | None = None) -> ModelEpochTransition:
    """Append one authorized lifecycle transition; never edits prior history."""
    epoch = await db.get(ModelEpoch, epoch_id)
    if epoch is None:
        raise InvalidEpochTransition("Model epoch not found")
    actor = _required_text(actor, "actor")
    rationale = _required_text(rationale, "rationale")
    to_state = to_state.upper()
    authority_role = authority_role.upper()
    if to_state not in LIFECYCLE_STATES:
        raise InvalidEpochTransition(f"Invalid lifecycle state: {to_state}")
    if authority_role not in AUTHORITY_ROLES:
        raise InvalidEpochTransition(f"Invalid authority role: {authority_role}")
    current = await current_transition(db, epoch_id)
    required_role = ALLOWED_TRANSITIONS.get((current.to_state, to_state))
    if required_role is None:
        raise InvalidEpochTransition(
            f"Transition {current.to_state} -> {to_state} is not allowed")
    if authority_role != required_role:
        raise InvalidEpochTransition(
            f"Transition {current.to_state} -> {to_state} requires {required_role}")
    row = ModelEpochTransition(
        epoch_id=epoch_id, sequence=current.sequence + 1,
        from_state=current.to_state, to_state=to_state,
        authority_role=authority_role, actor=actor, rationale=rationale,
        evidence_json=_canonical_json(evidence or {}),
    )
    db.add(row)
    await db.flush()
    return row


async def publish_epoch(db: AsyncSession, epoch_id: int, *, actor: str,
                        authority_role: str, rationale: str,
                        action: str = "PUBLISH") -> ProgramEpochActivation:
    """Append a publication selection for an already commitment-ready epoch."""
    epoch = await db.get(ModelEpoch, epoch_id)
    if epoch is None:
        raise EpochNotPublishable("Model epoch not found")
    actor = _required_text(actor, "actor")
    rationale = _required_text(rationale, "rationale")
    authority_role = authority_role.upper()
    action = action.upper()
    if authority_role != "PROGRAM_SCHEDULING":
        raise EpochNotPublishable("Publishing requires PROGRAM_SCHEDULING authority")
    if action not in {"PUBLISH", "ROLLBACK"}:
        raise EpochNotPublishable(f"Invalid publication action: {action}")
    transition = await current_transition(db, epoch_id)
    if transition.to_state != "COMMITMENT_READY":
        raise EpochNotPublishable("Only COMMITMENT_READY epochs can publish")
    latest = (await db.execute(
        select(ProgramEpochActivation)
        .where(ProgramEpochActivation.program == epoch.program)
        .order_by(ProgramEpochActivation.id.desc()).limit(1)
    )).scalar_one_or_none()
    if (latest is not None and latest.epoch_id == epoch.id
            and latest.transition_id == transition.id):
        return latest
    row = ProgramEpochActivation(
        program=epoch.program, epoch_id=epoch.id, transition_id=transition.id,
        action=action, authority_role=authority_role, actor=actor,
        rationale=rationale,
    )
    db.add(row)
    await db.flush()
    return row


async def published_epoch(db: AsyncSession, program: str) -> EpochSelection | None:
    """Return the effective publication only if its authorizing transition is still current."""
    program = program.upper()
    activation = (await db.execute(
        select(ProgramEpochActivation)
        .where(ProgramEpochActivation.program == program)
        .order_by(ProgramEpochActivation.id.desc()).limit(1)
    )).scalar_one_or_none()
    if activation is None:
        return None
    epoch = await db.get(ModelEpoch, activation.epoch_id)
    transition = await current_transition(db, activation.epoch_id)
    if (epoch is None or transition.id != activation.transition_id
            or transition.to_state != "COMMITMENT_READY"):
        return None
    return EpochSelection(epoch=epoch, transition=transition)


async def latest_epoch(db: AsyncSession, program: str) -> EpochSelection | None:
    """Return the newest epoch and its current state, regardless of publication."""
    epoch = (await db.execute(
        select(ModelEpoch).where(ModelEpoch.program == program.upper())
        .order_by(ModelEpoch.id.desc()).limit(1)
    )).scalar_one_or_none()
    if epoch is None:
        return None
    return EpochSelection(epoch=epoch, transition=await current_transition(db, epoch.id))


def _legacy_definition(program: str) -> dict:
    spec = registry.spec(program)
    try:
        from app.services import program_service
        metadata = program_service.load_specs().get(program, {})
    except Exception:
        metadata = {}
    return {
        "registry_schema": 1,
        "identity": {
            "program": program,
            "plant": metadata.get("plant", ""),
            "project_id": metadata.get("project_id", ""),
            "part_nos": metadata.get("part_nos", []),
        },
        "routing": {
            "ops": [list(row) for row in spec.ops],
            "cures": [list(row) for row in spec.cures],
            "milestones": [list(row) for row in spec.milestones],
            "ceilings": [list(row) for row in spec.ceilings],
            "pack_op": spec.pack_op,
            "ship_op": spec.ship_op,
            "floor_op": spec.floor_op,
            "crew_by_op": {str(k): v for k, v in sorted(spec.crew_by_op.items())},
            "dpas": spec.dpas,
        },
    }


async def _candidate_definition(db: AsyncSession, program: str,
                                *, include_physical_policies: bool = False) -> dict:
    """Freeze the one-to-one DB-shadow mapping used for incumbent parity."""
    legacy = _legacy_definition(program)
    bindings = (await db.execute(
        select(OperationResourceBinding).where(
            OperationResourceBinding.program == program,
            OperationResourceBinding.status == "APPROVED",
        ).order_by(OperationResourceBinding.acquire_op, OperationResourceBinding.id)
    )).scalars().all()
    pools = {}
    binding_rows = []
    for binding in bindings:
        pool = await db.get(ResourcePool, binding.pool_id)
        if pool is None:
            raise EpochSelectionError(
                f"Approved binding {binding.id} references a missing resource pool")
        versions = (await db.execute(
            select(ResourceCapacityVersion).where(
                ResourceCapacityVersion.pool_id == pool.id,
                ResourceCapacityVersion.status == "APPROVED",
            ).order_by(ResourceCapacityVersion.effective_from, ResourceCapacityVersion.id)
        )).scalars().all()
        pools[pool.code] = {
            "pool_id": pool.id,
            "site": pool.site,
            "name": pool.name,
            "resource_type": pool.resource_type,
            "capacity_unit": pool.capacity_unit,
            "work_center_no": pool.work_center_no,
            "active": pool.active,
            "capacity_versions": [
                ({
                    "id": version.id,
                    "effective_from": version.effective_from.isoformat(),
                    "effective_to": (version.effective_to.isoformat()
                                     if version.effective_to else None),
                    "capacity_scope": version.capacity_scope,
                    "capacity_schedule": (json.loads(version.capacity_schedule_json)
                                          if version.capacity_schedule_json else None),
                    "slot_count": version.slot_count,
                    "assumption_id": version.assumption_id,
                } | ({
                    "calendar_policy": json.loads(version.calendar_policy_json or "{}"),
                    "external_policy": json.loads(version.external_policy_json or "{}"),
                } if include_physical_policies else {}))
                for version in versions
            ],
        }
        binding_rows.append({
            "binding_id": binding.id,
            "pool_code": pool.code,
            "part_no": binding.part_no,
            "routing_revision": binding.routing_revision,
            "routing_alternative": binding.routing_alternative,
            "acquire_op": binding.acquire_op,
            "release_op": binding.release_op,
            "requirement_mode": binding.requirement_mode,
            "quantity": binding.quantity,
            "demand_source": binding.demand_source,
            "release_event": binding.release_event,
            "assumption_id": binding.assumption_id,
        })
    return {
        **legacy,
        "candidate_schema": 1,
        "purpose": "incumbent_legacy_parity",
        "resource_registry": {
            "strategy": "one_to_one_legacy",
            "pools": [pools[key] | {"code": key} for key in sorted(pools)],
            "bindings": binding_rows,
        },
    }


async def _physical_candidate_definition(db: AsyncSession, program: str) -> dict:
    definition = await _candidate_definition(
        db, program, include_physical_policies=True)
    definition["purpose"] = "physical_pool_shadow"
    definition["resource_registry"]["strategy"] = "physical_pools"
    return definition


async def assert_candidate_definition_current(
        db: AsyncSession, selections: Mapping[str, EpochSelection]) -> None:
    """Reject a shadow run when its frozen registry mapping has drifted."""
    for program, selection in selections.items():
        if selection.epoch.epoch_kind != "CANDIDATE":
            continue
        stored = json.loads(selection.epoch.definition_json)["definition"]
        purpose = stored.get("purpose")
        if purpose == "incumbent_legacy_parity":
            current = await _candidate_definition(db, program)
        elif purpose == "physical_pool_shadow":
            current = await _physical_candidate_definition(db, program)
        elif purpose in {
                "aeronose_op775_no_station_shadow",
                "aeronose_op775_accelerated_drdi_shadow"}:
            from app.services.aeronose_cure_candidate import current_cure_definition
            current = await current_cure_definition(db, stored)
        else:
            continue
        if _canonical_json(stored) != _canonical_json(current):
            raise EpochSelectionError(
                f"Candidate epoch {selection.epoch.epoch_key} no longer matches "
                "the live resource registry; create a successor epoch")


async def create_physical_shadow_epochs(
        db: AsyncSession, programs, *, actor: str = "TwinWorks resource migration",
        as_of: date | None = None) -> dict[str, EpochSelection]:
    """Freeze complete physical-pool definitions in OBSERVE without publication."""
    from app.services.resource_registry import resource_coverage

    as_of = as_of or date.today()
    programs = tuple(code.upper() for code in programs if code.upper() in registry.programs)
    await ensure_legacy_epochs(db, programs)
    candidates = {}
    for program in programs:
        published_before = await published_epoch(db, program)
        predecessor = published_before or await latest_epoch(db, program)
        if predecessor is None:
            raise EpochSelectionError(
                f"Physical shadow for {program} requires an existing model epoch")
        issues = await resource_coverage(db, program, as_of)
        missing = [issue for issue in issues if issue.severity == "MISSING"]
        if missing:
            detail = "; ".join(
                f"{issue.subject_key}:{issue.parameter}" for issue in missing)
            raise EpochSelectionError(
                f"Physical shadow for {program} has incomplete resources: {detail}")
        definition = await _physical_candidate_definition(db, program)
        pool_codes = {
            row["code"] for row in definition["resource_registry"]["pools"]
        }
        if not any(not code.startswith("LEGACY:") for code in pool_codes):
            raise EpochSelectionError(
                f"Physical shadow for {program} has no physical labor pool")
        epoch = await create_epoch(
            db, program=program, label="Physical labor-pool shadow",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition=definition, predecessor_epoch_id=predecessor.epoch.id,
            created_by=actor,
        )
        transition = await current_transition(db, epoch.id)
        if transition.to_state == "DRAFT":
            transition = await transition_epoch(
                db, epoch.id, to_state="OBSERVE", actor=actor,
                authority_role="DATA_ADMIN",
                rationale="Begin governed physical labor-pool shadow",
                evidence={"gate": "BCA-03b", "publication_change": False},
            )
        if transition.to_state != "OBSERVE":
            raise EpochSelectionError(
                f"Physical shadow for {program} is {transition.to_state}, not OBSERVE")
        published = await published_epoch(db, program)
        published_id = published.epoch.id if published else None
        published_before_id = published_before.epoch.id if published_before else None
        if published_id != published_before_id:
            raise EpochSelectionError(
                f"Creating the {program} physical shadow changed publication")
        candidates[program] = EpochSelection(epoch=epoch, transition=transition)
    return candidates


async def ensure_incumbent_shadow_epochs(
        db: AsyncSession, programs=("ELEV", "RAD", "AEGIS"),
        *, actor: str = "TwinWorks migration") -> dict[str, EpochSelection]:
    """Create idempotent OBSERVE candidates without changing publication."""
    from app.services.resource_profile import seed_legacy_resources

    programs = tuple(code.upper() for code in programs if code.upper() in registry.programs)
    await seed_legacy_resources(db)
    legacy = await ensure_legacy_epochs(db, programs)
    candidates = {}
    for program in programs:
        definition = await _candidate_definition(db, program)
        candidate = await create_epoch(
            db, program=program, label="Legacy-parity resource registry shadow",
            epoch_kind="CANDIDATE", resource_mode="DB_SHADOW",
            definition=definition, predecessor_epoch_id=legacy[program].epoch.id,
            created_by=actor,
        )
        transition = await current_transition(db, candidate.id)
        if transition.to_state == "DRAFT":
            transition = await transition_epoch(
                db, candidate.id, to_state="OBSERVE", actor=actor,
                authority_role="DATA_ADMIN",
                rationale="Begin exact-parity incumbent shadow evaluation",
                evidence={"gate": "PLAT-01c", "publication_change": False},
            )
        if transition.to_state != "OBSERVE":
            raise EpochSelectionError(
                f"Incumbent parity candidate for {program} is {transition.to_state}, not OBSERVE")
        prior_candidates = (await db.execute(select(ModelEpoch).where(
            ModelEpoch.program == program,
            ModelEpoch.epoch_kind == "CANDIDATE",
            ModelEpoch.id != candidate.id,
        ))).scalars().all()
        for prior_candidate in prior_candidates:
            prior_transition = await current_transition(db, prior_candidate.id)
            if (prior_transition.to_state == "OBSERVE"
                    and prior_candidate.label == "Legacy-parity resource registry shadow"):
                await transition_epoch(
                    db, prior_candidate.id, to_state="ARCHIVED", actor=actor,
                    authority_role="DATA_ADMIN",
                    rationale="Superseded by a newer immutable parity definition",
                    evidence={"successor_epoch_key": candidate.epoch_key},
                )
        published = await published_epoch(db, program)
        if published is None or published.epoch.id != legacy[program].epoch.id:
            raise EpochSelectionError(
                f"Creating the {program} shadow candidate changed publication")
        candidates[program] = EpochSelection(epoch=candidate, transition=transition)
    return candidates


async def verify_incumbent_shadow_parity(
        db: AsyncSession, *, data_source=None,
        programs=("ELEV", "RAD", "AEGIS")) -> IncumbentParityReport:
    """Run frozen legacy and DB-shadow profiles over identical incumbent WIP."""
    from app.data.snapshot_source import SnapshotDataSource
    from app.engines.rtg_wrapper import run_pooled
    from app.services.assumption_drift import build_drift_report
    from app.services.resource_profile import (
        _serialize_results,
        compile_profile,
        persist_replay_snapshot,
        replay_snapshot,
    )

    ds = data_source or SnapshotDataSource(use_position_state=False)
    programs = tuple(code.upper() for code in programs if code.upper() in registry.programs)
    candidates = await ensure_incumbent_shadow_epochs(db, programs)
    # Materialize review debt before compilation so readiness in the first
    # shadow snapshot already reflects stale or missing recertification data.
    review_report = await build_drift_report(db, ds.as_of().date())
    units = {
        program: [unit.as_sim_unit() for unit in ds.get_wip_units(program) if not unit.stalled]
        for program in programs
    }
    horizon = max(
        (item["commit"] for rows in units.values() for item in rows if item.get("commit")),
        default=ds.as_of().date(),
    )
    legacy_profile = await compile_profile(
        db, programs=programs, as_of=ds.as_of(), horizon_end=horizon, mode="LEGACY")
    shadow_profile = await compile_profile(
        db, programs=programs, as_of=ds.as_of(), horizon_end=horizon, mode="DB_SHADOW",
        epoch_ids={program: selection.epoch.id
                   for program, selection in candidates.items()},
    )
    legacy_result = run_pooled(units, ds.as_of(), profile=legacy_profile.scheduler_profile)
    shadow_result = run_pooled(units, ds.as_of(), profile=shadow_profile.scheduler_profile)
    legacy_serialized = _serialize_results(legacy_result)
    shadow_serialized = _serialize_results(shadow_result)
    mismatches = tuple(sorted(
        serial for serial in set(legacy_serialized) | set(shadow_serialized)
        if legacy_serialized.get(serial) != shadow_serialized.get(serial)
    ))
    legacy_replay = await persist_replay_snapshot(
        db, base_snapshot_id=legacy_profile.snapshot_id,
        units_by_program=units, results=legacy_result,
    )
    shadow_replay = await persist_replay_snapshot(
        db, base_snapshot_id=shadow_profile.snapshot_id,
        units_by_program=units, results=shadow_result,
    )
    legacy_verified = await replay_snapshot(db, legacy_replay.id)
    shadow_verified = await replay_snapshot(db, shadow_replay.id)
    if not legacy_verified.exact_match or not shadow_verified.exact_match:
        raise EpochSelectionError("Incumbent snapshot replay did not reproduce its stored result")
    return IncumbentParityReport(
        exact_match=not mismatches,
        programs=programs,
        unit_counts={program: len(rows) for program, rows in units.items()},
        candidate_epoch_ids={program: selection.epoch.id
                             for program, selection in candidates.items()},
        legacy_snapshot_id=legacy_replay.id,
        shadow_snapshot_id=shadow_replay.id,
        legacy_result_hash=legacy_verified.result_hash,
        shadow_result_hash=shadow_verified.result_hash,
        mismatched_serials=mismatches,
        open_review_debt=len({row.review_key for row in review_report.reviews}),
        review_debt_by_type={
            review_type: sum(1 for row in review_report.reviews
                             if row.review_type == review_type)
            for review_type in sorted({row.review_type for row in review_report.reviews})
        },
    )


async def ensure_legacy_epochs(db: AsyncSession, programs) -> dict[str, EpochSelection]:
    """Idempotently bootstrap the currently published legacy epoch for existing programs."""
    selections: dict[str, EpochSelection] = {}
    for code in [
        p.upper() for p in programs
        if p.upper() in registry.programs and p.upper() in LEGACY_BASELINE_PROGRAMS
    ]:
        key = f"{code}:LEGACY"
        epoch = (await db.execute(
            select(ModelEpoch).where(ModelEpoch.epoch_key == key)
        )).scalar_one_or_none()
        if epoch is None:
            epoch = await create_epoch(
                db, program=code, label="Published legacy baseline",
                epoch_kind="LEGACY_BASELINE", resource_mode="LEGACY",
                definition=_legacy_definition(code), created_by="TwinWorks migration",
                epoch_key=key,
            )
        expected_json = _canonical_json(_definition_record(
            program=code, epoch_kind="LEGACY_BASELINE", resource_mode="LEGACY",
            predecessor=None, definition=_legacy_definition(code),
        ))
        expected_hash = hashlib.sha256(expected_json.encode("utf-8")).hexdigest()
        if epoch.definition_hash != expected_hash:
            raise EpochSelectionError(
                f"Published legacy epoch for {code} no longer matches the runtime registry")
        transition = await current_transition(db, epoch.id)
        bootstrap_path = {
            "DRAFT": ("OBSERVE", "DATA_ADMIN"),
            "OBSERVE": ("PROVISIONAL", "IE_FLOOR"),
            "PROVISIONAL": ("COMMITMENT_READY", "PROGRAM_SCHEDULING"),
        }
        while transition.to_state in bootstrap_path:
            target, role = bootstrap_path[transition.to_state]
            transition = await transition_epoch(
                db, epoch.id, to_state=target, actor="TwinWorks migration",
                authority_role=role,
                rationale="Preserve the accepted pre-epoch production baseline",
                evidence={"migration": "PLAT-01a", "behavior_change": False},
            )
        activation_count = await db.scalar(select(func.count(ProgramEpochActivation.id)).where(
            ProgramEpochActivation.program == code))
        if not activation_count:
            await publish_epoch(
                db, epoch.id, actor="TwinWorks migration",
                authority_role="PROGRAM_SCHEDULING",
                rationale="Keep the existing production forecast authoritative",
            )
        selected = await published_epoch(db, code)
        if selected is None:
            raise EpochSelectionError(f"No published epoch is available for {code}")
        selections[code] = selected
    return selections


async def resolve_epochs_for_run(db: AsyncSession, programs,
                                 requested: Mapping[str, int] | None = None,
                                 mode: str | None = None,
                                 ) -> dict[str, EpochSelection]:
    """Resolve explicit shadow epochs or the current published epoch for every program."""
    programs = [program.upper() for program in programs]
    if requested is None:
        await ensure_legacy_epochs(db, programs)
        selected = {}
        for program in programs:
            row = await published_epoch(db, program)
            if row is not None:
                selected[program] = row
        if not selected:
            raise EpochSelectionError("No published epochs are available for this run")
        _validate_run_modes(selected, mode)
        return selected

    normalized = {program.upper(): epoch_id for program, epoch_id in requested.items()}
    if set(normalized) != set(programs):
        raise EpochSelectionError("Explicit epoch selection must cover exactly every run program")
    selected = {}
    for program in programs:
        epoch = await db.get(ModelEpoch, normalized[program])
        if epoch is None or epoch.program != program:
            raise EpochSelectionError(f"Epoch selection does not belong to {program}")
        transition = await current_transition(db, epoch.id)
        if transition.to_state not in RUNNABLE_STATES:
            raise EpochSelectionError(
                f"Epoch {epoch.epoch_key} is not runnable from {transition.to_state}")
        selected[program] = EpochSelection(epoch=epoch, transition=transition)
    _validate_run_modes(selected, mode)
    return selected


def _validate_run_modes(selections: Mapping[str, EpochSelection], mode: str | None) -> None:
    mode = mode.upper().replace("-", "_") if mode else None
    for program, selection in selections.items():
        epoch_mode = selection.epoch.resource_mode
        if mode == "LEGACY" and epoch_mode != "LEGACY":
            raise EpochSelectionError(
                f"LEGACY run for {program} requires a LEGACY epoch, not {epoch_mode}")
        if mode == "DB_ACTIVE" and epoch_mode != "DB_ACTIVE":
            raise EpochSelectionError(
                f"DB_ACTIVE run for {program} requires a DB_ACTIVE epoch, not {epoch_mode}")
