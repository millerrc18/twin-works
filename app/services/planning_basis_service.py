"""Resolve configured target intent against the effective model lifecycle."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import model_epoch_service as EPOCHS
from app.services import program_service as PROGRAMS


PLANNING_BASES = {"PLAN_SLOTS", "CONTRACT_DATES", "NONE"}


@dataclass(frozen=True)
class PlanningContext:
    program: str
    configured_planning_basis: str
    plan_label: str | None
    plan_source: str | None
    plan_version: str | None
    lifecycle_state: str
    epoch_key: str | None
    basis_effective: bool
    forecast_visibility: str

    @property
    def target_label(self) -> str:
        if self.configured_planning_basis == "PLAN_SLOTS":
            return self.plan_label or "Plan"
        if self.configured_planning_basis == "CONTRACT_DATES":
            return self.plan_label or "Contract"
        return "No approved target"


def configured_context(program: str, *, lifecycle_state: str = "COMMITMENT_READY",
                       epoch_key: str | None = None) -> PlanningContext:
    """Resolve metadata synchronously for deterministic engine/test callers."""
    program = program.upper()
    meta = PROGRAMS.planning_meta(program)
    basis = meta["configured_planning_basis"]
    effective = lifecycle_state == "COMMITMENT_READY" and basis != "NONE"
    return PlanningContext(
        program=program, configured_planning_basis=basis,
        plan_label=meta.get("plan_label"), plan_source=meta.get("plan_source"),
        plan_version=meta.get("plan_version"), lifecycle_state=lifecycle_state,
        epoch_key=epoch_key, basis_effective=effective,
        forecast_visibility=("PUBLISHED" if effective else "SUPPRESSED"),
    )


async def context_for_program(db: AsyncSession, program: str) -> PlanningContext:
    """Use the published epoch when present; otherwise expose the latest candidate state."""
    program = program.upper()
    published = await EPOCHS.published_epoch(db, program)
    selected = published or await EPOCHS.latest_epoch(db, program)
    state = selected.state if selected else "DRAFT"
    key = selected.epoch.epoch_key if selected else None
    meta = PROGRAMS.planning_meta(program)
    basis = meta["configured_planning_basis"]
    effective = published is not None and state == "COMMITMENT_READY" and basis != "NONE"
    return PlanningContext(
        program=program, configured_planning_basis=basis,
        plan_label=meta.get("plan_label"), plan_source=meta.get("plan_source"),
        plan_version=meta.get("plan_version"), lifecycle_state=state,
        epoch_key=key, basis_effective=effective,
        forecast_visibility=("PUBLISHED" if effective else "SUPPRESSED"),
    )


async def published_programs(db: AsyncSession, programs) -> list[str]:
    """Programs whose current activation is still commitment-ready."""
    active = []
    for program in programs:
        if await EPOCHS.published_epoch(db, program):
            active.append(program.upper())
    return active


def comparison_target(context: PlanningContext, *, contract_date: date | None,
                      plan_target_date: date | None) -> date | None:
    if not context.basis_effective:
        return None
    if context.configured_planning_basis == "PLAN_SLOTS":
        return plan_target_date
    if context.configured_planning_basis == "CONTRACT_DATES":
        return contract_date
    return None
