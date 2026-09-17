"""Governed Aeronose op-775 cure successor definitions."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_epoch_service import (
    _candidate_definition,
    _legacy_definition,
    create_epoch,
    current_transition,
    ensure_legacy_epochs,
    published_epoch,
    transition_epoch,
)


PROGRAM = "RAD"
OPERATION = 775
BASELINE_HOURS = 40
FLASHOFF_HOURS = 2
ACCELERATED_CURE_HOURS = 8


class DrdiApprovalRequired(ValueError):
    """The accelerated cure cannot enter OBSERVE without complete approval evidence."""


@dataclass(frozen=True)
class CureSuccessors:
    no_station_epoch_id: int
    accelerated_epoch_id: int


@dataclass(frozen=True)
class CureUnitDelta:
    serial: str
    baseline_finish: datetime
    candidate_finish: datetime
    delta_hours: float


@dataclass(frozen=True)
class CureComparison:
    epoch_id: int
    baseline_snapshot_id: int
    candidate_snapshot_id: int
    replay_exact: bool
    changed_units: int
    units: tuple[CureUnitDelta, ...]


def _replace_op775_cure(definition: dict, rows: list[list]) -> None:
    cures = [row for row in definition["routing"]["cures"] if int(row[0]) != OPERATION]
    definition["routing"]["cures"] = cures + rows


def _normalized_drdi(drdi: dict | None) -> dict | None:
    if drdi is None:
        return None
    return {
        "status": str(drdi.get("status") or "PENDING").upper(),
        "identifiers": sorted({
            str(item).strip() for item in (drdi.get("identifiers") or [])
            if str(item).strip()
        }),
        "approved_by": (str(drdi.get("approved_by")).strip()
                        if drdi.get("approved_by") else None),
        "approved_at": (str(drdi.get("approved_at")).strip()
                        if drdi.get("approved_at") else None),
        "effective_from": (str(drdi.get("effective_from")).strip()
                           if drdi.get("effective_from") else None),
    }


def build_cure_definition(*, drdi: dict | None = None, base: dict | None = None) -> dict:
    """Build a deterministic no-station or accelerated op-775 route definition."""
    definition = deepcopy(base or _legacy_definition(PROGRAM))
    normalized = _normalized_drdi(drdi)
    if normalized is None:
        _replace_op775_cure(definition, [[
            OPERATION,
            "GATE - Electrical Sealing 40hr (Shore A)",
            BASELINE_HOURS,
            "op775 polysulfide 00200054000: WI MIN 40hr cure, Shore A>=35 gate "
            "(IFS mach 11.6hr understates) - dominant radome dwell",
        ]])
        definition["process_change"] = {
            "change_type": "OP775_NO_FIXED_STATION",
            "operation": OPERATION,
            "station_constraint": "NONE",
            "flashoff_hours": 0,
            "cure_hours": BASELINE_HOURS,
            "total_elapsed_hours": BASELINE_HOURS,
            "approval_status": "APPROVED_PHYSICAL_FACT",
            "evidence": [
                "owner://ryan-miller/aeronose-op775/no-fixed-station/2026-09-03",
                "docs/validation/tool-01c-aeronose-wi-review.md",
            ],
        }
        return definition

    _replace_op775_cure(definition, [
        [
            OPERATION,
            "GATE - Electrical Sealing DRDI Flashoff",
            FLASHOFF_HOURS,
            "DRDI-controlled two-hour flashoff; not production-authorized while pending",
        ],
        [
            OPERATION,
            "GATE - Electrical Sealing DRDI Accelerated Cure",
            ACCELERATED_CURE_HOURS,
            "DRDI-controlled eight-hour cure; Shore A acceptance remains required",
        ],
    ])
    definition["process_change"] = {
        "change_type": "OP775_ACCELERATED_DRDI_CURE",
        "operation": OPERATION,
        "station_constraint": "NONE",
        "flashoff_hours": FLASHOFF_HOURS,
        "cure_hours": ACCELERATED_CURE_HOURS,
        "total_elapsed_hours": FLASHOFF_HOURS + ACCELERATED_CURE_HOURS,
        "approval_status": normalized["status"],
        "drdi": normalized,
    }
    return definition


def validate_observe_eligibility(definition: dict) -> None:
    """Reject an accelerated route unless its DRDI approval evidence is complete."""
    change = definition.get("process_change") or {}
    if change.get("change_type") != "OP775_ACCELERATED_DRDI_CURE":
        return
    drdi = change.get("drdi") or {}
    if drdi.get("status") != "APPROVED":
        raise DrdiApprovalRequired("Accelerated cure requires approved DRDI evidence")
    if not drdi.get("identifiers"):
        raise DrdiApprovalRequired("Approved DRDI evidence requires identifiers")
    if not drdi.get("approved_by"):
        raise DrdiApprovalRequired("Approved DRDI evidence requires approved_by")
    try:
        datetime.fromisoformat(str(drdi.get("approved_at")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise DrdiApprovalRequired(
            "Approved DRDI evidence requires approved_at") from None
    try:
        date.fromisoformat(str(drdi.get("effective_from")))
    except (TypeError, ValueError):
        raise DrdiApprovalRequired(
            "Approved DRDI evidence requires effective_from") from None


async def _advance_to_observe(db: AsyncSession, epoch_id: int, actor: str, evidence: dict):
    transition = await current_transition(db, epoch_id)
    if transition.to_state == "DRAFT":
        transition = await transition_epoch(
            db,
            epoch_id,
            to_state="OBSERVE",
            actor=actor,
            authority_role="DATA_ADMIN",
            rationale="Begin governed Aeronose op-775 cure shadow",
            evidence=evidence,
        )
    return transition


async def ensure_cure_successors(
        db: AsyncSession, *, actor: str, drdi: dict | None = None) -> CureSuccessors:
    """Create the physical correction and a separately gated accelerated successor."""
    from app.services.resource_profile import seed_legacy_resources

    await seed_legacy_resources(db)
    published_before = (await ensure_legacy_epochs(db, [PROGRAM]))[PROGRAM]
    resource_definition = await _candidate_definition(db, PROGRAM)

    no_station = build_cure_definition(base=resource_definition)
    no_station["purpose"] = "aeronose_op775_no_station_shadow"
    no_station_epoch = await create_epoch(
        db,
        program=PROGRAM,
        label="Aeronose op-775 no-station 40-hour cure",
        epoch_kind="CANDIDATE",
        resource_mode="DB_SHADOW",
        definition=no_station,
        predecessor_epoch_id=published_before.epoch.id,
        created_by=actor,
    )
    no_station_transition = await _advance_to_observe(
        db,
        no_station_epoch.id,
        actor,
        {"gate": "#32c", "publication_change": False, "cure_hours": 40},
    )
    if no_station_transition.to_state != "OBSERVE":
        raise DrdiApprovalRequired("No-station cure successor is not in OBSERVE")

    accelerated = build_cure_definition(drdi=drdi or {"status": "PENDING"},
                                        base=resource_definition)
    accelerated["purpose"] = "aeronose_op775_accelerated_drdi_shadow"
    accelerated_epoch = await create_epoch(
        db,
        program=PROGRAM,
        label="Aeronose op-775 DRDI accelerated cure",
        epoch_kind="CANDIDATE",
        resource_mode="DB_SHADOW",
        definition=accelerated,
        predecessor_epoch_id=no_station_epoch.id,
        created_by=actor,
    )
    try:
        validate_observe_eligibility(accelerated)
    except DrdiApprovalRequired:
        pass
    else:
        transition = await _advance_to_observe(
            db,
            accelerated_epoch.id,
            actor,
            {
                "gate": "#32c-DRDI",
                "publication_change": False,
                "drdi": accelerated["process_change"]["drdi"],
            },
        )
        if transition.to_state != "OBSERVE":
            raise DrdiApprovalRequired("Accelerated cure successor is not in OBSERVE")

    published_after = await published_epoch(db, PROGRAM)
    if (published_after is None
            or published_after.epoch.id != published_before.epoch.id):
        raise DrdiApprovalRequired("Creating cure successors changed publication")
    return CureSuccessors(
        no_station_epoch_id=no_station_epoch.id,
        accelerated_epoch_id=accelerated_epoch.id,
    )


async def current_cure_definition(db: AsyncSession, stored: dict) -> dict:
    """Rebuild a cure successor against the current governed resource registry."""
    base = await _candidate_definition(db, PROGRAM)
    purpose = stored.get("purpose")
    if purpose == "aeronose_op775_no_station_shadow":
        current = build_cure_definition(base=base)
    elif purpose == "aeronose_op775_accelerated_drdi_shadow":
        current = build_cure_definition(
            base=base, drdi=(stored.get("process_change") or {}).get("drdi"))
    else:
        raise ValueError(f"Unsupported Aeronose cure purpose: {purpose}")
    current["purpose"] = purpose
    return current


async def compare_cure_successor(
        db: AsyncSession, *, epoch_id: int, units_by_program: dict,
        as_of: datetime, horizon_end: date) -> CureComparison:
    """Compare and persist replayable legacy/cure-successor results."""
    from app.engines.rtg_wrapper import run_pooled
    from app.services.resource_profile import (
        compile_profile,
        persist_replay_snapshot,
        replay_snapshot,
    )

    baseline_profile = await compile_profile(
        db, programs=[PROGRAM], as_of=as_of, horizon_end=horizon_end, mode="LEGACY")
    candidate_profile = await compile_profile(
        db, programs=[PROGRAM], as_of=as_of, horizon_end=horizon_end,
        mode="DB_SHADOW", epoch_ids={PROGRAM: epoch_id})
    baseline = run_pooled(
        deepcopy(units_by_program), as_of,
        profile=baseline_profile.scheduler_profile, trace_constraints=True)
    candidate = run_pooled(
        deepcopy(units_by_program), as_of,
        profile=candidate_profile.scheduler_profile, trace_constraints=True)
    baseline_snapshot = await persist_replay_snapshot(
        db, base_snapshot_id=baseline_profile.snapshot_id,
        units_by_program=units_by_program, results=baseline)
    candidate_snapshot = await persist_replay_snapshot(
        db, base_snapshot_id=candidate_profile.snapshot_id,
        units_by_program=units_by_program, results=candidate)
    baseline_replay = await replay_snapshot(db, baseline_snapshot.id)
    candidate_replay = await replay_snapshot(db, candidate_snapshot.id)
    deltas = []
    for serial in sorted(set(baseline) & set(candidate)):
        before = baseline[serial].get("finish")
        after = candidate[serial].get("finish")
        if before is None or after is None or before == after:
            continue
        deltas.append(CureUnitDelta(
            serial=serial,
            baseline_finish=before,
            candidate_finish=after,
            delta_hours=round((after - before).total_seconds() / 3600.0, 3),
        ))
    return CureComparison(
        epoch_id=epoch_id,
        baseline_snapshot_id=baseline_snapshot.id,
        candidate_snapshot_id=candidate_snapshot.id,
        replay_exact=baseline_replay.exact_match and candidate_replay.exact_match,
        changed_units=len(deltas),
        units=tuple(deltas),
    )
