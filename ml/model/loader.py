"""Load active trained models + real scored counts from the DB into the registry.
Called at app startup and after each retrain so predict() stays synchronous."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelVersion
from ml.model.registry import registry_model


async def refresh_registry(db: AsyncSession):
    # active trained versions
    rows = (await db.execute(
        select(ModelVersion).where(ModelVersion.active == True,  # noqa: E712
                                   ModelVersion.model_type == "TRAINED"))).scalars().all()
    versions = [(r.program, r.p50_blob, r.p80_blob, r.n_scored) for r in rows]
    # Gate counts FORWARD scored ships only (real prospective closes), not backtest training rows.
    # This keeps the EMPIRICAL->TRAINED flip honest: it happens once enough REAL ships accrue.
    from app.services.accuracy_forward import forward_counts
    counts = {}
    try:
        counts = dict(forward_counts() or {})
    except Exception:
        counts = {}
    registry_model.load_trained(versions, counts)
    return dict(trained_programs=[v[0] for v in versions], scored_counts=counts)
