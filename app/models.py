"""ORM models — the 5 persisted tables. Reference JSON files stay on disk (read-only)."""
from datetime import datetime, timezone, date
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, Boolean, Text, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    actual_close: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    error_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    model_status: Mapped[str] = mapped_column(String(12), default="EMPIRICAL")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


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
    slot_id = '{program}:{hand}:{target_iso}' (hand='' for radome/aegis)."""
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
    pack: Mapped[Optional[date]] = mapped_column(Date, nullable=True)        # physical pack-op clock
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


class Program(Base):
    """A tracked program's full config — the DB-backed replacement for the hardcoded routers.py /
    PROG_IFS / PACK_OP / threshold spread. Ops/cures/milestones/crew stored as JSON. When a row
    exists for a code, the registry uses it; otherwise it falls back to routers.py (migration).
    Big structural data lives in JSON columns (single source of truth); a timestamped snapshot is
    also exported to program_snapshots/ on save for diffable history (this app has no git)."""
    __tablename__ = "program"
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
    hand_split: Mapped[bool] = mapped_column(Boolean, default=False)
    hand_map_json: Mapped[str] = mapped_column(Text, default="{}")   # JSON {part_no: 'LH'|'RH'}
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


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
