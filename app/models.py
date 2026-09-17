"""ORM models for TwinWorks persistence and append-only governance."""
from datetime import datetime, timezone, date
from typing import Optional
from sqlalchemy import (
    String, Integer, Float, Date, DateTime, Boolean, Text, LargeBinary,
    ForeignKey, UniqueConstraint, CheckConstraint, DDL, event, inspect as sa_inspect,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApprovedRecordImmutable(ValueError):
    """Approved governance records may only be closed through supersession."""


class ImmutableEpochRecord(ValueError):
    """Model epoch definitions and their audit events are append-only."""


class ForecastLog(Base):
    """One row per (build_date, serial). Sim + ML forecast stamped each build;
    actual_close/error_days backfilled when the unit ships. Accuracy truth."""
    __tablename__ = "forecast_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    build_date: Mapped[str] = mapped_column(String(10), index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    serial: Mapped[str] = mapped_column(String(32), index=True)
    so: Mapped[str] = mapped_column(String(12), index=True)
    maxop_at_log: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sim_finish_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    p50_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    p80_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    plan_target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    comparison_target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planning_basis: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    plan_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_epoch_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actual_close: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    error_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_status: Mapped[str] = mapped_column(String(12), default="EMPIRICAL")
    simulation_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("simulation_snapshot.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class AccuracySummaryLog(Base):
    """Immutable per-program, fixed-horizon forward-accuracy snapshot."""
    __tablename__ = "accuracy_summary_log"
    __table_args__ = (
        CheckConstraint("horizon_days IN (7,14,21)"),
        CheckConstraint(
            "confidence IN ('INSUFFICIENT','PRELIMINARY','DEVELOPING','ESTABLISHED')"),
        CheckConstraint("sample_size >= 0"),
        CheckConstraint("observed_unit_count >= sample_size"),
        CheckConstraint("missing_window_count >= 0"),
        CheckConstraint("post_ship_record_count >= 0"),
        CheckConstraint("p80_sample_size >= 0 AND p80_sample_size <= sample_size"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    formula_version: Mapped[str] = mapped_column(String(24))
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[str] = mapped_column(String(16))
    sample_size: Mapped[int] = mapped_column(Integer)
    observed_unit_count: Mapped[int] = mapped_column(Integer)
    missing_window_count: Mapped[int] = mapped_column(Integer)
    post_ship_record_count: Mapped[int] = mapped_column(Integer)
    mae_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bias_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hit3_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hit7_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p80_sample_size: Mapped[int] = mapped_column(Integer, default=0)
    p80_coverage_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p80_wilson_low_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p80_wilson_high_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_forecast_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    cohort_json: Mapped[str] = mapped_column(Text, default="[]")
    cohort_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class MLTrainingRow(Base):
    """One row per closed unit per snapshot: features + residual target."""
    __tablename__ = "ml_training_row"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    serial: Mapped[str] = mapped_column(String(32), index=True)
    so: Mapped[str] = mapped_column(String(12), index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    milestone_phase: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crew_at_op: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_dwell_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cleaned_dwell_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wi_complexity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sharedwc_queue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sim_forecast_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    actual_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    residual_days: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ModelVersion(Base):
    """Audit trail of trained/empirical models. active flag selects current. Never delete."""
    __tablename__ = "model_version"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    model_type: Mapped[str] = mapped_column(String(12))  # EMPIRICAL | TRAINED
    n_scored: Mapped[int] = mapped_column(Integer, default=0)
    p50_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    p80_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    bias_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class WIConstraint(Base):
    """LLM-extracted WI constraint (cure/gate). Diffable across providers; validated flag."""
    __tablename__ = "wi_constraint"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    source_file: Mapped[str] = mapped_column(String(255))
    mtime: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    after_op: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    label: Mapped[str] = mapped_column(String(255))
    dwell_hr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    constraint_type: Mapped[str] = mapped_column(String(8))  # CURE | GATE
    llm_provider: Mapped[str] = mapped_column(String(16))
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_quote: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class SlotAssignment(Base):
    """RTG delivery slot -> currently-assigned serial. Seeded from the RTG plan; edited
    inline on the matrix when a swap happens (a stalled unit gets passed by another).
    slot_id = '{program}:{hand}:{original_serial}' (hand='' for radome)."""
    __tablename__ = "slot_assignment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_id: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    hand: Mapped[str] = mapped_column(String(4), default="")   # LH | RH | ''
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    serial: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # None = empty slot
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class PositionState(Base):
    """Mutable WIP/shipped state, materialized from the wip_tables baseline then updated by
    IFS syncs. One row per SO. SnapshotDataSource reads this when populated (else falls back to
    the wip_tables module baseline). closed != None => the unit shipped (drops out of WIP)."""
    __tablename__ = "position_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    so: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    serial: Mapped[str] = mapped_column(String(32))
    maxop: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_clock: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closed: Mapped[Optional[date]] = mapped_column(Date, nullable=True)      # ship/close date
    pack: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # terminal-op completion
    source: Mapped[str] = mapped_column(String(12), default="baseline")      # baseline | ifs-sync
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ModelHistory(Base):
    """Append-only trend of model state, written on every sync so the admin page can chart how
    bias/MAE/n evolve and when a program flips EMPIRICAL->TRAINED. Distinct from ModelVersion
    (which stores loadable model blobs); this is purely the observability trail."""
    __tablename__ = "model_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    mode: Mapped[str] = mapped_column(String(12))            # EMPIRICAL | TRAINED
    n_scored: Mapped[int] = mapped_column(Integer, default=0)
    threshold: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bias: Mapped[Optional[float]] = mapped_column(Float, nullable=True)   # measured optimism (days)
    mae: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # forward MAE if scored
    source: Mapped[str] = mapped_column(String(16), default="sync")       # positions | ships | manual


class SyncRun(Base):
    """One row per sync attempt: single-run lock + status/audit. active=True while running so a
    concurrent click is refused; flipped False (with result/error) when the run finishes."""
    __tablename__ = "sync_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))            # positions | ships
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    stage: Mapped[str] = mapped_column(String(24), default="starting")
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ObservationQuarantineEvent(Base):
    """Append-only quarantine lifecycle for source records excluded from modeling conclusions."""
    __tablename__ = "observation_quarantine_event"
    __table_args__ = (
        UniqueConstraint("quarantine_key", "sequence"),
        CheckConstraint("event_type IN ('OPEN','RESOLVE','REOPEN')"),
        CheckConstraint("reason_code IN ('TERMINAL_COMPLETE_STATE_OPEN')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    quarantine_key: Mapped[str] = mapped_column(String(160), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    stream_key: Mapped[str] = mapped_column(String(32), index=True)
    project_id: Mapped[str] = mapped_column(String(40))
    part_no: Mapped[str] = mapped_column(String(100))
    order_no: Mapped[str] = mapped_column(String(40), index=True)
    serial: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(40))
    event_type: Mapped[str] = mapped_column(String(16), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    evidence_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Program(Base):
    """A tracked program's full config — the DB-backed replacement for the hardcoded routers.py /
    PROG_IFS / PACK_OP / threshold spread. Ops/cures/milestones/crew stored as JSON. When a row
    exists for a code, the registry uses it; otherwise it falls back to routers.py (migration).
    Big structural data lives in JSON columns (single source of truth); a timestamped snapshot is
    also exported to program_snapshots/ on save for diffable history (this app has no git)."""
    __tablename__ = "program"
    __table_args__ = (
        CheckConstraint(
            "configured_planning_basis IN ('PLAN_SLOTS','CONTRACT_DATES','NONE')"),
    )
    code: Mapped[str] = mapped_column(String(8), primary_key=True)   # ELEV | RAD | AEGIS | new
    name: Mapped[str] = mapped_column(String(64))
    plant: Mapped[str] = mapped_column(String(16), default="")       # physical plant (pooling boundary)
    project_id: Mapped[str] = mapped_column(String(16))              # IFS PROJECT_ID
    part_nos: Mapped[str] = mapped_column(Text)                      # JSON list of PART_NO
    pack_op: Mapped[int] = mapped_column(Integer)
    ship_op: Mapped[int] = mapped_column(Integer)
    floor_op: Mapped[int] = mapped_column(Integer, default=0)
    ops_json: Mapped[str] = mapped_column(Text)                      # JSON [[opno,desc,wc,hr,ms],...]
    cures_json: Mapped[str] = mapped_column(Text, default="[]")      # JSON [[after_op,label,dwell_hr,note],...]
    milestones_json: Mapped[str] = mapped_column(Text)              # JSON [[code,name],...]
    ceilings_json: Mapped[str] = mapped_column(Text)               # JSON [[ms_code,max_op],...]
    crew_by_op_json: Mapped[str] = mapped_column(Text, default="{}")  # JSON {opno: crew_size}
    dpas: Mapped[bool] = mapped_column(Boolean, default=False)
    train_threshold: Mapped[int] = mapped_column(Integer, default=25)
    rtg_source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    configured_planning_basis: Mapped[str] = mapped_column(String(24), default="NONE")
    plan_label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    plan_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hand_split: Mapped[bool] = mapped_column(Boolean, default=False)
    hand_map_json: Mapped[str] = mapped_column(Text, default="{}")   # JSON {part_no: 'LH'|'RH'}
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ModelEpoch(Base):
    """Immutable definition of one program model generation."""
    __tablename__ = "model_epoch"
    __table_args__ = (
        UniqueConstraint("program", "definition_hash"),
        CheckConstraint("epoch_kind IN ('LEGACY_BASELINE','CANDIDATE')"),
        CheckConstraint("resource_mode IN ('LEGACY','DB_SHADOW','DB_ACTIVE')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epoch_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    epoch_kind: Mapped[str] = mapped_column(String(24))
    predecessor_epoch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_epoch.id"), nullable=True)
    label: Mapped[str] = mapped_column(String(128))
    resource_mode: Mapped[str] = mapped_column(String(16))
    definition_json: Mapped[str] = mapped_column(Text)
    definition_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ModelEpochTransition(Base):
    """Append-only lifecycle decision for a model epoch."""
    __tablename__ = "model_epoch_transition"
    __table_args__ = (
        UniqueConstraint("epoch_id", "sequence"),
        CheckConstraint(
            "to_state IN ('DRAFT','OBSERVE','PROVISIONAL','COMMITMENT_READY',"
            "'PAUSED','ARCHIVED','DEPRECATED')"),
        CheckConstraint(
            "from_state IS NULL OR from_state IN ('DRAFT','OBSERVE','PROVISIONAL',"
            "'COMMITMENT_READY','PAUSED','ARCHIVED','DEPRECATED')"),
        CheckConstraint(
            "authority_role IN ('DATA_ADMIN','IE_FLOOR','PROGRAM_SCHEDULING')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    epoch_id: Mapped[int] = mapped_column(ForeignKey("model_epoch.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    from_state: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    to_state: Mapped[str] = mapped_column(String(24), index=True)
    authority_role: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    transitioned_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ProgramEpochActivation(Base):
    """Append-only selection of the epoch allowed to publish for a program."""
    __tablename__ = "program_epoch_activation"
    __table_args__ = (
        CheckConstraint("action IN ('PUBLISH','ROLLBACK')"),
        CheckConstraint("authority_role = 'PROGRAM_SCHEDULING'"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    epoch_id: Mapped[int] = mapped_column(ForeignKey("model_epoch.id"), index=True)
    transition_id: Mapped[int] = mapped_column(
        ForeignKey("model_epoch_transition.id"), index=True)
    action: Mapped[str] = mapped_column(String(16))
    authority_role: Mapped[str] = mapped_column(String(24))
    actor: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str] = mapped_column(Text)
    activated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ResourcePool(Base):
    """Stable identity of one physical labor, machine, tooling, cure, or space resource."""
    __tablename__ = "resource_pool"
    __table_args__ = (
        CheckConstraint("resource_type IN ('LABOR','MACHINE','TOOL','CURE_STATION','SPACE')"),
        CheckConstraint("capacity_unit IN ('HOURS','SLOTS')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    site: Mapped[str] = mapped_column(String(8), index=True)
    name: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(16))
    capacity_unit: Mapped[str] = mapped_column(String(8))
    work_center_no: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ResourceInstance(Base):
    """Optional named instance for a non-fungible discrete resource."""
    __tablename__ = "resource_instance"
    __table_args__ = (UniqueConstraint("pool_id", "instance_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    instance_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ModelAssumption(Base):
    """Immutable, effective-dated model input with evidence and approval provenance."""
    __tablename__ = "model_assumption"
    __table_args__ = (
        CheckConstraint("basis IN ('IFS_FACT','MEASURED_ACTUAL','DERIVED_ESTIMATE','OWNER_CONFIRMED','PROVISIONAL_GUESS')"),
        CheckConstraint("approval_status IN ('DRAFT','APPROVED','UNDER_REVIEW','SUPERSEDED')"),
        CheckConstraint("commitment_grade IN ('COMMITMENT_READY','INTERNAL_ONLY')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_type: Mapped[str] = mapped_column(String(24), index=True)
    subject_key: Mapped[str] = mapped_column(String(128), index=True)
    parameter: Mapped[str] = mapped_column(String(64), index=True)
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    basis: Mapped[str] = mapped_column(String(24))
    approval_status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    commitment_grade: Mapped[str] = mapped_column(String(24), default="INTERNAL_ONLY")
    evidence_source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_schema_version: Mapped[int] = mapped_column(Integer, default=1)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    evidence_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    calculation_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    minimum_evidence_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approver: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_due_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    supersedes_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_assumption.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ResourceCapacityVersion(Base):
    """Append-only effective capacity or slot-count version for a physical pool."""
    __tablename__ = "resource_capacity_version"
    __table_args__ = (
        UniqueConstraint("pool_id", "effective_from"),
        CheckConstraint("status IN ('DRAFT','APPROVED','SUPERSEDED')"),
        CheckConstraint("capacity_scope IN ('GROSS_SITE','NET_TRACKED')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    capacity_scope: Mapped[str] = mapped_column(String(16))
    capacity_schedule_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    slot_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    calendar_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    external_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    assumption_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_assumption.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ResourceAvailabilityEvent(Base):
    """Append-only lifecycle event for a finite resource outage."""
    __tablename__ = "resource_availability_event"
    __table_args__ = (
        UniqueConstraint("outage_key", "sequence"),
        CheckConstraint(
            "event_type IN ('OUTAGE_OPEN','RETURN_TO_SERVICE','EXTEND','CANCEL','VOID')"),
        CheckConstraint(
            "reason_code IN ('TOOL_SHOP','MAINTENANCE','REPAIR','CALIBRATION','OTHER')"),
        CheckConstraint("authority_role IN ('DATA_ADMIN','PROGRAM_OWNER')"),
        CheckConstraint("unavailable_quantity > 0"),
        CheckConstraint("length(trim(reason)) > 0"),
        CheckConstraint("length(trim(actor)) > 0"),
        CheckConstraint("json_valid(evidence_json)"),
        CheckConstraint(
            "(event_type = 'OUTAGE_OPEN' AND sequence = 1 "
            "AND effective_at IS NOT NULL AND expected_end_at IS NOT NULL "
            "AND expected_end_at > effective_at) OR "
            "(event_type = 'EXTEND' AND sequence > 1 "
            "AND effective_at IS NULL AND expected_end_at IS NOT NULL) OR "
            "(event_type = 'RETURN_TO_SERVICE' AND sequence > 1 "
            "AND effective_at IS NOT NULL AND expected_end_at IS NULL) OR "
            "(event_type IN ('CANCEL','VOID') AND sequence > 1 "
            "AND effective_at IS NULL AND expected_end_at IS NULL)"
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    outage_key: Mapped[str] = mapped_column(String(160), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    instance_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    unavailable_quantity: Mapped[int] = mapped_column(Integer)
    effective_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    expected_end_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(128))
    authority_role: Mapped[str] = mapped_column(String(24))
    evidence_json: Mapped[str] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow)


class OperationResourceBinding(Base):
    """Effort or occupancy requirement on a program routing operation/span."""
    __tablename__ = "operation_resource_binding"
    __table_args__ = (
        CheckConstraint("requirement_mode IN ('EFFORT','OCCUPANCY')"),
        CheckConstraint("demand_source IN ('LABOR','MACHINE','FIXED')"),
        CheckConstraint("release_event IN ('OP_START','OP_COMPLETE','CURE_COMPLETE','ROUTE_COMPLETE')"),
        CheckConstraint("status IN ('DRAFT','APPROVED','SUPERSEDED')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    part_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    routing_revision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    routing_alternative: Mapped[str] = mapped_column(String(16), default="*")
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    acquire_op: Mapped[int] = mapped_column(Integer)
    release_op: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requirement_mode: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    demand_source: Mapped[str] = mapped_column(String(16))
    release_event: Mapped[str] = mapped_column(String(20))
    min_hold_hours: Mapped[float] = mapped_column(Float, default=0.0)
    lag_hours: Mapped[float] = mapped_column(Float, default=0.0)
    instance_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    assumption_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_assumption.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class ExternalLoadSnapshot(Base):
    __tablename__ = "external_load_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    source: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(16))
    coverage_start: Mapped[date] = mapped_column(Date)
    coverage_end: Mapped[date] = mapped_column(Date)
    tracked_programs_json: Mapped[str] = mapped_column(Text)
    quality_policy_json: Mapped[str] = mapped_column(Text)
    assumption_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class ExternalLoadRow(Base):
    __tablename__ = "external_load_row"
    __table_args__ = (
        CheckConstraint("quality IN ('OK','SUSPECT','EXCLUDED')"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("external_load_snapshot.id"), index=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    shift: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    order_no: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    part_no: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32))
    load_type: Mapped[str] = mapped_column(String(16))
    hours: Mapped[float] = mapped_column(Float, default=0.0)
    units: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    quality: Mapped[str] = mapped_column(String(12))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    exclusion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SimulationSnapshot(Base):
    """Immutable inputs observed for one run, not a global publication lock."""
    __tablename__ = "simulation_snapshot"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    as_of: Mapped[datetime] = mapped_column(DateTime)
    horizon_end: Mapped[date] = mapped_column(Date)
    mode: Mapped[str] = mapped_column(String(16))
    profile_json: Mapped[str] = mapped_column(Text)
    assumption_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    external_snapshot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("external_load_snapshot.id"), nullable=True)
    readiness: Mapped[str] = mapped_column(String(16))
    unresolved_json: Mapped[str] = mapped_column(Text, default="[]")
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)


class SimulationSnapshotEpoch(Base):
    """Queryable epoch references materialized inside a simulation snapshot."""
    __tablename__ = "simulation_snapshot_epoch"
    simulation_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_snapshot.id"), primary_key=True)
    program: Mapped[str] = mapped_column(String(8), primary_key=True)
    model_epoch_id: Mapped[int] = mapped_column(ForeignKey("model_epoch.id"), index=True)


class ForecastConstraintEvent(Base):
    __tablename__ = "forecast_constraint_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("simulation_snapshot.id"), index=True)
    serial: Mapped[str] = mapped_column(String(32), index=True)
    program: Mapped[str] = mapped_column(String(8), index=True)
    pool_id: Mapped[int] = mapped_column(ForeignKey("resource_pool.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32))
    wait_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    wait_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    wait_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    gross_capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    external_load: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    schedulable_capacity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    assumption_ids_json: Mapped[str] = mapped_column(Text, default="[]")


class AssumptionReview(Base):
    __tablename__ = "assumption_review"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED','DISMISSED')"),
        CheckConstraint(
            "review_type IN ('EXPIRY','MISSING_REVIEW_DATE','MISSING_DRIFT_POLICY',"
            "'BACKFILL_ATTESTATION','DRIFT','SPARSE_EVIDENCE','MANUAL')"),
        CheckConstraint(
            "(status = 'OPEN' AND resolution IS NULL AND successor_assumption_id IS NULL) OR "
            "(status = 'DISMISSED' AND resolution = 'DISMISSED' "
            "AND successor_assumption_id IS NULL) OR "
            "(status = 'RESOLVED' AND resolution IN ('RECERTIFIED','SUPERSEDED') "
            "AND successor_assumption_id IS NOT NULL)"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assumption_id: Mapped[int] = mapped_column(ForeignKey("model_assumption.id"), index=True)
    review_key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    review_type: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    reason: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    owner: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    opened_by: Mapped[str] = mapped_column(String(128), default="TwinWorks")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    successor_assumption_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("model_assumption.id"), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


APPROVED_ASSUMPTION_EVIDENCE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_model_assumption_evidence_immutable
BEFORE UPDATE ON model_assumption
WHEN OLD.approval_status = 'APPROVED' AND (
    NEW.evidence_schema_version IS NOT OLD.evidence_schema_version
    OR NEW.evidence_json IS NOT OLD.evidence_json
)
BEGIN
    SELECT RAISE(ABORT, 'approved assumption evidence immutable');
END
"""

ASSUMPTION_REVIEW_RESOLUTION_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_assumption_review_resolution_immutable
BEFORE UPDATE ON assumption_review
WHEN OLD.status != 'OPEN' OR NOT (
    NEW.status IN ('RESOLVED','DISMISSED')
    AND NEW.resolved_at IS NOT NULL
    AND NEW.resolved_by IS NOT NULL
    AND (
        (NEW.status = 'DISMISSED' AND NEW.resolution = 'DISMISSED'
            AND NEW.successor_assumption_id IS NULL)
        OR (NEW.status = 'RESOLVED'
            AND NEW.resolution IN ('RECERTIFIED','SUPERSEDED')
            AND NEW.successor_assumption_id IS NOT NULL)
    )
    AND NEW.assumption_id IS OLD.assumption_id
    AND NEW.review_key IS OLD.review_key
    AND NEW.review_type IS OLD.review_type
    AND NEW.reason IS OLD.reason
    AND NEW.evidence_json IS OLD.evidence_json
    AND NEW.owner IS OLD.owner
    AND NEW.opened_by IS OLD.opened_by
    AND NEW.opened_at IS OLD.opened_at
)
BEGIN
    SELECT RAISE(ABORT, 'assumption review resolution immutable');
END
"""

ASSUMPTION_REVIEW_DELETE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_assumption_review_delete_immutable
BEFORE DELETE ON assumption_review
BEGIN
    SELECT RAISE(ABORT, 'assumption reviews cannot be deleted');
END
"""

QUARANTINE_EVENT_VALIDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_observation_quarantine_transition_validate
BEFORE INSERT ON observation_quarantine_event
WHEN
    NEW.sequence != COALESCE((
        SELECT MAX(sequence) + 1 FROM observation_quarantine_event
        WHERE quarantine_key = NEW.quarantine_key
    ), 1)
    OR (NEW.sequence = 1 AND NEW.event_type != 'OPEN')
    OR (NEW.sequence > 1 AND NOT EXISTS (
        SELECT 1 FROM observation_quarantine_event first
        WHERE first.quarantine_key = NEW.quarantine_key AND first.sequence = 1
          AND first.stream_key = NEW.stream_key
          AND first.project_id = NEW.project_id
          AND first.part_no = NEW.part_no
          AND first.order_no = NEW.order_no
          AND first.reason_code = NEW.reason_code
    ))
    OR (NEW.sequence > 1 AND NOT (
        (NEW.event_type = 'RESOLVE' AND (
            SELECT event_type FROM observation_quarantine_event
            WHERE quarantine_key = NEW.quarantine_key ORDER BY sequence DESC LIMIT 1
        ) IN ('OPEN','REOPEN'))
        OR (NEW.event_type = 'REOPEN' AND (
            SELECT event_type FROM observation_quarantine_event
            WHERE quarantine_key = NEW.quarantine_key ORDER BY sequence DESC LIMIT 1
        ) = 'RESOLVE')
    ))
BEGIN
    SELECT RAISE(ABORT, 'invalid observation quarantine transition');
END
"""

RESOURCE_AVAILABILITY_EVENT_VALIDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_resource_availability_event_validate
BEFORE INSERT ON resource_availability_event
WHEN
    NEW.sequence != COALESCE((
        SELECT MAX(sequence) + 1 FROM resource_availability_event
        WHERE outage_key = NEW.outage_key
    ), 1)
    OR NOT EXISTS (
        SELECT 1 FROM resource_pool
        WHERE id = NEW.pool_id AND resource_type = 'TOOL' AND capacity_unit = 'SLOTS'
    )
    OR length(trim(NEW.outage_key)) = 0
    OR length(trim(NEW.event_key)) = 0
    OR length(trim(NEW.reason)) = 0
    OR length(trim(NEW.actor)) = 0
    OR NOT EXISTS (SELECT 1 FROM json_each(NEW.evidence_json))
    OR NEW.unavailable_quantity < 1
    OR (NEW.instance_code IS NOT NULL AND (
        NEW.unavailable_quantity != 1
        OR NOT EXISTS (
            SELECT 1 FROM resource_instance
            WHERE pool_id = NEW.pool_id
              AND instance_code = NEW.instance_code
              AND active = 1
        )
    ))
    OR (NEW.sequence = 1 AND (
        NEW.event_type != 'OUTAGE_OPEN'
        OR NEW.effective_at IS NULL OR NEW.expected_end_at IS NULL
        OR NEW.expected_end_at <= NEW.effective_at
        OR NEW.unavailable_quantity > COALESCE((
            SELECT slot_count FROM resource_capacity_version
            WHERE pool_id = NEW.pool_id
              AND effective_from <= date(NEW.effective_at)
            ORDER BY effective_from DESC, id DESC LIMIT 1
        ), 0)
    ))
    OR (NEW.sequence > 1 AND NOT EXISTS (
        SELECT 1 FROM resource_availability_event first
        WHERE first.outage_key = NEW.outage_key AND first.sequence = 1
          AND first.pool_id = NEW.pool_id
          AND first.instance_code IS NEW.instance_code
          AND first.unavailable_quantity = NEW.unavailable_quantity
    ))
    OR (NEW.sequence > 1 AND (
        SELECT event_type FROM resource_availability_event
        WHERE outage_key = NEW.outage_key ORDER BY sequence DESC LIMIT 1
    ) NOT IN ('OUTAGE_OPEN','EXTEND'))
    OR (NEW.event_type = 'EXTEND' AND (
        NEW.expected_end_at IS NULL OR NEW.effective_at IS NOT NULL
        OR NEW.expected_end_at <= (
            SELECT expected_end_at FROM resource_availability_event
            WHERE outage_key = NEW.outage_key AND expected_end_at IS NOT NULL
            ORDER BY sequence DESC LIMIT 1
        )
    ))
    OR (NEW.event_type = 'RETURN_TO_SERVICE' AND (
        NEW.effective_at IS NULL OR NEW.expected_end_at IS NOT NULL
        OR NEW.effective_at <= (
            SELECT effective_at FROM resource_availability_event
            WHERE outage_key = NEW.outage_key AND sequence = 1
        )
    ))
    OR (NEW.event_type = 'CANCEL' AND (
        NEW.effective_at IS NOT NULL OR NEW.expected_end_at IS NOT NULL
        OR NEW.occurred_at > (
            SELECT effective_at FROM resource_availability_event
            WHERE outage_key = NEW.outage_key AND sequence = 1
        )
    ))
    OR (NEW.event_type = 'VOID' AND (
        NEW.effective_at IS NOT NULL OR NEW.expected_end_at IS NOT NULL
    ))
BEGIN
    SELECT RAISE(ABORT, 'invalid resource availability transition');
END
"""

RESOURCE_AVAILABILITY_CAPACITY_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_resource_availability_capacity_validate
BEFORE INSERT ON resource_availability_event
WHEN NEW.event_type IN ('OUTAGE_OPEN','EXTEND','RETURN_TO_SERVICE')
BEGIN
    SELECT CASE WHEN EXISTS (
        WITH latest AS (
            SELECT event.outage_key, event.event_type, event.effective_at
            FROM resource_availability_event event
            WHERE event.sequence = (
                SELECT MAX(candidate.sequence)
                FROM resource_availability_event candidate
                WHERE candidate.outage_key = event.outage_key
            )
        ), intervals AS (
            SELECT first.outage_key,
                   first.unavailable_quantity,
                   first.effective_at AS start_at,
                   CASE
                       WHEN latest.event_type = 'RETURN_TO_SERVICE' THEN latest.effective_at
                       ELSE (
                           SELECT prior.expected_end_at
                           FROM resource_availability_event prior
                           WHERE prior.outage_key = first.outage_key
                             AND prior.expected_end_at IS NOT NULL
                           ORDER BY prior.sequence DESC LIMIT 1
                       )
                   END AS end_at
            FROM resource_availability_event first
            JOIN latest ON latest.outage_key = first.outage_key
            WHERE first.sequence = 1
              AND first.pool_id = NEW.pool_id
              AND first.outage_key != NEW.outage_key
              AND latest.event_type NOT IN ('CANCEL','VOID')
        ), proposed AS (
            SELECT
                CASE WHEN NEW.event_type = 'OUTAGE_OPEN' THEN NEW.effective_at
                     ELSE (
                         SELECT prior.expected_end_at
                         FROM resource_availability_event prior
                         WHERE prior.outage_key = NEW.outage_key
                           AND prior.expected_end_at IS NOT NULL
                         ORDER BY prior.sequence DESC LIMIT 1
                     )
                END AS start_at,
                CASE WHEN NEW.event_type = 'RETURN_TO_SERVICE' THEN NEW.effective_at
                     ELSE NEW.expected_end_at
                END AS end_at,
                NEW.unavailable_quantity AS quantity
        ), points AS (
            SELECT start_at AS point_at FROM proposed
            UNION
            SELECT intervals.start_at
            FROM intervals, proposed
            WHERE intervals.start_at >= proposed.start_at
              AND intervals.start_at < proposed.end_at
        )
        SELECT 1
        FROM points, proposed
        WHERE points.point_at < proposed.end_at
          AND proposed.quantity + COALESCE((
              SELECT SUM(intervals.unavailable_quantity)
              FROM intervals
              WHERE intervals.start_at <= points.point_at
                AND intervals.end_at > points.point_at
          ), 0) > COALESCE((
              SELECT version.slot_count
              FROM resource_capacity_version version
              WHERE version.pool_id = NEW.pool_id
                AND version.effective_from <= date(points.point_at)
                AND (version.effective_to IS NULL
                     OR version.effective_to >= date(points.point_at))
              ORDER BY version.effective_from DESC, version.id DESC LIMIT 1
          ), 0)
    ) THEN RAISE(ABORT, 'resource availability exceeds effective baseline') END;
END
"""


def _guard_approved_update(target, status_field: str) -> None:
    state = sa_inspect(target)
    status_attr = state.attrs[status_field]
    was_approved = (getattr(target, status_field) == "APPROVED" or
                    "APPROVED" in status_attr.history.deleted)
    if not was_approved:
        return
    changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
    allowed = {status_field, "effective_to"}
    if not (changed <= allowed and getattr(target, status_field) == "SUPERSEDED"
            and getattr(target, "effective_to", None) is not None):
        raise ApprovedRecordImmutable("Approved records must be superseded, not edited")


@event.listens_for(ModelAssumption, "before_update")
def _protect_approved_assumption(_mapper, _connection, target) -> None:
    _guard_approved_update(target, "approval_status")


@event.listens_for(ResourceCapacityVersion, "before_update")
def _protect_approved_capacity(_mapper, _connection, target) -> None:
    _guard_approved_update(target, "status")


@event.listens_for(AssumptionReview, "before_update")
def _protect_resolved_review(_mapper, _connection, target) -> None:
    state = sa_inspect(target)
    if target.status == "OPEN" and "OPEN" not in state.attrs.status.history.deleted:
        return
    if "OPEN" not in state.attrs.status.history.deleted:
        raise ApprovedRecordImmutable("Resolved assumption reviews are immutable")
    changed = {attr.key for attr in state.attrs if attr.history.has_changes()}
    allowed = {
        "status", "resolved_at", "resolved_by", "resolution",
        "successor_assumption_id", "resolution_notes",
    }
    if not changed <= allowed or target.status not in {"RESOLVED", "DISMISSED"}:
        raise ApprovedRecordImmutable("Assumption reviews may only be resolved once")


@event.listens_for(AssumptionReview, "before_delete")
def _protect_review_delete(_mapper, _connection, _target) -> None:
    raise ApprovedRecordImmutable("Assumption reviews cannot be deleted")


APPROVED_ASSUMPTION_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_model_assumption_approved_immutable
BEFORE UPDATE ON model_assumption
WHEN OLD.approval_status = 'APPROVED' AND NOT (
    NEW.approval_status = 'SUPERSEDED' AND NEW.effective_to IS NOT NULL
    AND NEW.subject_type IS OLD.subject_type AND NEW.subject_key IS OLD.subject_key
    AND NEW.parameter IS OLD.parameter AND NEW.value_json IS OLD.value_json
    AND NEW.unit IS OLD.unit AND NEW.basis IS OLD.basis
    AND NEW.commitment_grade IS OLD.commitment_grade
    AND NEW.evidence_source IS OLD.evidence_source
    AND NEW.evidence_start IS OLD.evidence_start AND NEW.evidence_end IS OLD.evidence_end
    AND NEW.calculation_method IS OLD.calculation_method
    AND NEW.evidence_count IS OLD.evidence_count
    AND NEW.minimum_evidence_count IS OLD.minimum_evidence_count
    AND NEW.owner IS OLD.owner AND NEW.approver IS OLD.approver
    AND NEW.approved_at IS OLD.approved_at AND NEW.review_due_at IS OLD.review_due_at
    AND NEW.effective_from IS OLD.effective_from
    AND NEW.supersedes_id IS OLD.supersedes_id AND NEW.created_at IS OLD.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'approved assumption immutable');
END
"""

APPROVED_CAPACITY_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_resource_capacity_approved_immutable
BEFORE UPDATE ON resource_capacity_version
WHEN OLD.status = 'APPROVED' AND NOT (
    NEW.status = 'SUPERSEDED' AND NEW.effective_to IS NOT NULL
    AND NEW.pool_id IS OLD.pool_id AND NEW.effective_from IS OLD.effective_from
    AND NEW.capacity_scope IS OLD.capacity_scope
    AND NEW.capacity_schedule_json IS OLD.capacity_schedule_json
    AND NEW.slot_count IS OLD.slot_count
    AND NEW.calendar_policy_json IS OLD.calendar_policy_json
    AND NEW.external_policy_json IS OLD.external_policy_json
    AND NEW.assumption_id IS OLD.assumption_id AND NEW.created_at IS OLD.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'approved capacity immutable');
END
"""

event.listen(ModelAssumption.__table__, "after_create", DDL(APPROVED_ASSUMPTION_TRIGGER))
event.listen(ModelAssumption.__table__, "after_create",
             DDL(APPROVED_ASSUMPTION_EVIDENCE_TRIGGER))
event.listen(ResourceCapacityVersion.__table__, "after_create", DDL(APPROVED_CAPACITY_TRIGGER))
event.listen(AssumptionReview.__table__, "after_create",
             DDL(ASSUMPTION_REVIEW_RESOLUTION_TRIGGER))
event.listen(AssumptionReview.__table__, "after_create",
             DDL(ASSUMPTION_REVIEW_DELETE_TRIGGER))


MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_model_epoch_transition_validate
BEFORE INSERT ON model_epoch_transition
WHEN
    NOT EXISTS (SELECT 1 FROM model_epoch WHERE id = NEW.epoch_id)
    OR NEW.sequence != COALESCE((
        SELECT MAX(sequence) + 1 FROM model_epoch_transition WHERE epoch_id = NEW.epoch_id
    ), 1)
    OR (
        NEW.sequence = 1 AND NOT (
            NEW.from_state IS NULL AND NEW.to_state = 'DRAFT'
            AND NEW.authority_role = 'DATA_ADMIN'
        )
    )
    OR (
        NEW.sequence > 1 AND NOT (
            NEW.from_state = (
                SELECT to_state FROM model_epoch_transition
                WHERE epoch_id = NEW.epoch_id ORDER BY sequence DESC LIMIT 1
            )
            AND (
                (NEW.from_state = 'DRAFT' AND NEW.to_state = 'OBSERVE'
                    AND NEW.authority_role = 'DATA_ADMIN')
                OR (NEW.from_state = 'DRAFT' AND NEW.to_state = 'ARCHIVED'
                    AND NEW.authority_role = 'DATA_ADMIN')
                OR (NEW.from_state = 'OBSERVE' AND NEW.to_state = 'PROVISIONAL'
                    AND NEW.authority_role = 'IE_FLOOR')
                OR (NEW.from_state = 'OBSERVE' AND NEW.to_state = 'PAUSED'
                    AND NEW.authority_role = 'IE_FLOOR')
                OR (NEW.from_state = 'OBSERVE' AND NEW.to_state = 'ARCHIVED'
                    AND NEW.authority_role = 'DATA_ADMIN')
                OR (NEW.from_state = 'PROVISIONAL' AND NEW.to_state = 'COMMITMENT_READY'
                    AND NEW.authority_role = 'PROGRAM_SCHEDULING')
                OR (NEW.from_state = 'PROVISIONAL' AND NEW.to_state = 'OBSERVE'
                    AND NEW.authority_role = 'IE_FLOOR')
                OR (NEW.from_state = 'PROVISIONAL' AND NEW.to_state = 'PAUSED'
                    AND NEW.authority_role = 'IE_FLOOR')
                OR (NEW.from_state = 'COMMITMENT_READY' AND NEW.to_state = 'PAUSED'
                    AND NEW.authority_role = 'PROGRAM_SCHEDULING')
                OR (NEW.from_state = 'COMMITMENT_READY' AND NEW.to_state = 'DEPRECATED'
                    AND NEW.authority_role = 'PROGRAM_SCHEDULING')
                OR (NEW.from_state = 'PAUSED' AND NEW.to_state = 'OBSERVE'
                    AND NEW.authority_role = 'IE_FLOOR')
                OR (NEW.from_state = 'PAUSED' AND NEW.to_state = 'ARCHIVED'
                    AND NEW.authority_role = 'DATA_ADMIN')
            )
        )
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid model epoch transition');
END
"""

MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS trg_program_epoch_activation_validate
BEFORE INSERT ON program_epoch_activation
WHEN
    NEW.authority_role != 'PROGRAM_SCHEDULING'
    OR NOT EXISTS (
        SELECT 1 FROM model_epoch
        WHERE id = NEW.epoch_id AND program = NEW.program
    )
    OR NOT EXISTS (
        SELECT 1 FROM model_epoch_transition
        WHERE id = NEW.transition_id AND epoch_id = NEW.epoch_id
            AND to_state = 'COMMITMENT_READY'
    )
    OR NEW.transition_id != (
        SELECT id FROM model_epoch_transition
        WHERE epoch_id = NEW.epoch_id ORDER BY sequence DESC LIMIT 1
    )
BEGIN
    SELECT RAISE(ABORT, 'invalid model epoch activation');
END
"""


def _append_only_update(_mapper, _connection, _target) -> None:
    raise ImmutableEpochRecord("Model epoch governance records are append-only")


def _append_only_delete(_mapper, _connection, _target) -> None:
    raise ImmutableEpochRecord("Model epoch governance records cannot be deleted")


_EPOCH_RECORDS = (
    ModelEpoch,
    ModelEpochTransition,
    AccuracySummaryLog,
    ProgramEpochActivation,
    ExternalLoadSnapshot,
    ExternalLoadRow,
    ObservationQuarantineEvent,
    ResourceAvailabilityEvent,
    SimulationSnapshot,
    SimulationSnapshotEpoch,
    ForecastConstraintEvent,
)
for _epoch_record in _EPOCH_RECORDS:
    event.listen(_epoch_record, "before_update", _append_only_update)
    event.listen(_epoch_record, "before_delete", _append_only_delete)


def _append_only_triggers(table_name: str) -> tuple[str, str]:
    return (
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_{table_name}_append_only_update
        BEFORE UPDATE ON {table_name}
        BEGIN
            SELECT RAISE(ABORT, 'append-only epoch record');
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_{table_name}_append_only_delete
        BEFORE DELETE ON {table_name}
        BEGIN
            SELECT RAISE(ABORT, 'append-only epoch record');
        END
        """,
    )


def _append_only_insert_guard(table_name: str, identity_predicate: str) -> str:
    return f"""
    CREATE TRIGGER IF NOT EXISTS trg_{table_name}_append_only_insert
    BEFORE INSERT ON {table_name}
    WHEN EXISTS (SELECT 1 FROM {table_name} WHERE {identity_predicate})
    BEGIN
        SELECT RAISE(ABORT, 'append-only epoch record');
    END
    """


event.listen(ModelEpochTransition.__table__, "after_create",
             DDL(MODEL_EPOCH_TRANSITION_VALIDATE_TRIGGER))
event.listen(ProgramEpochActivation.__table__, "after_create",
             DDL(MODEL_EPOCH_ACTIVATION_VALIDATE_TRIGGER))
for _epoch_table in (
    ModelEpoch.__table__,
    ModelEpochTransition.__table__,
    AccuracySummaryLog.__table__,
    ProgramEpochActivation.__table__,
    ExternalLoadSnapshot.__table__,
    ExternalLoadRow.__table__,
    ObservationQuarantineEvent.__table__,
    ResourceAvailabilityEvent.__table__,
    SimulationSnapshot.__table__,
    SimulationSnapshotEpoch.__table__,
    ForecastConstraintEvent.__table__,
):
    for _trigger_sql in _append_only_triggers(_epoch_table.name):
        event.listen(_epoch_table, "after_create", DDL(_trigger_sql))

_EPOCH_INSERT_IDENTITIES = {
    ModelEpoch.__table__: (
        "id = NEW.id OR epoch_key = NEW.epoch_key "
        "OR (program = NEW.program AND definition_hash = NEW.definition_hash)"),
    ModelEpochTransition.__table__: (
        "id = NEW.id OR (epoch_id = NEW.epoch_id AND sequence = NEW.sequence)"),
    AccuracySummaryLog.__table__: "id = NEW.id OR content_hash = NEW.content_hash",
    ProgramEpochActivation.__table__: "id = NEW.id",
    ExternalLoadSnapshot.__table__: "id = NEW.id OR content_hash = NEW.content_hash",
    ExternalLoadRow.__table__: "id = NEW.id",
    ObservationQuarantineEvent.__table__: (
        "id = NEW.id OR event_key = NEW.event_key OR "
        "(quarantine_key = NEW.quarantine_key AND sequence = NEW.sequence)"),
    ResourceAvailabilityEvent.__table__: (
        "id = NEW.id OR event_key = NEW.event_key OR "
        "(outage_key = NEW.outage_key AND sequence = NEW.sequence)"),
    SimulationSnapshot.__table__: "id = NEW.id OR content_hash = NEW.content_hash",
    SimulationSnapshotEpoch.__table__: (
        "simulation_snapshot_id = NEW.simulation_snapshot_id AND program = NEW.program"),
    ForecastConstraintEvent.__table__: "id = NEW.id",
}
for _epoch_table, _identity_predicate in _EPOCH_INSERT_IDENTITIES.items():
    event.listen(
        _epoch_table, "after_create",
        DDL(_append_only_insert_guard(_epoch_table.name, _identity_predicate)),
    )

event.listen(
    ObservationQuarantineEvent.__table__, "after_create",
    DDL(QUARANTINE_EVENT_VALIDATE_TRIGGER),
)
event.listen(
    ResourceAvailabilityEvent.__table__, "after_create",
    DDL(RESOURCE_AVAILABILITY_EVENT_VALIDATE_TRIGGER),
)
event.listen(
    ResourceAvailabilityEvent.__table__, "after_create",
    DDL(RESOURCE_AVAILABILITY_CAPACITY_TRIGGER),
)


class OAuthToken(Base):
    """Encrypted IFS OAuth tokens. Single row per service."""
    __tablename__ = "oauth_token"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(16), unique=True, default="ifs")
    access_token_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    refresh_token_enc: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
