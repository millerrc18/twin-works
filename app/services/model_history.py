"""ModelHistory — append a per-program snapshot of model state on each sync, and read it back
for the admin trend chart. Purely observability; distinct from ModelVersion (loadable blobs)."""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelHistory
from ml.model.registry import registry_model
from app.services import program_service as PSVC


async def append_all(db: AsyncSession, source: str = "sync") -> int:
    """Write one ModelHistory row per program capturing current mode/n/bias, plus forward MAE
    if a forward score exists. Returns rows written."""
    from app.services import accuracy_forward as AF
    fwd = {}
    try:
        fwd = AF.compute_forward_accuracy().get("by_program", {})
    except Exception:
        fwd = {}
    n = 0
    for p in PSVC.program_order():
        pred = registry_model.predict(p)
        mae = (fwd.get(p) or {}).get("mae")
        db.add(ModelHistory(at=datetime.utcnow(), program=p, mode=pred.mode,
                            n_scored=pred.n_scored, threshold=registry_model.threshold_for(p),
                            bias=round(-pred.p50_days, 2), mae=mae, source=source))
        n += 1
    await db.commit()
    return n


async def history(db: AsyncSession, program: str | None = None, limit: int = 60) -> list[dict]:
    q = select(ModelHistory).order_by(ModelHistory.at.asc())
    if program:
        q = q.where(ModelHistory.program == program)
    rows = (await db.execute(q)).scalars().all()
    rows = rows[-limit:]
    return [dict(at=r.at.isoformat(), program=r.program, mode=r.mode, n_scored=r.n_scored,
                 threshold=r.threshold, bias=r.bias, mae=r.mae, source=r.source) for r in rows]
