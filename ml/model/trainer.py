"""Trainer — fits quantile regressors on ml_training_row and writes a ModelVersion.

Target = residual_days (actual - sim). Two quantiles: P50 (alpha=0.5) and P80 (alpha=0.8),
so the app shows a de-biased median + a conservative upper bound. Trained per program when
that program has >= n_train_threshold scored rows; otherwise the registry stays EMPIRICAL.

Offline / admin-triggered only — never on the request hot path. Serialized with pickle
into the model_version blob columns (audit trail; never delete old versions).
"""
import pickle
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import MLTrainingRow, ModelVersion
from ml.model.features import FeatureVector


def _feature_matrix(rows):
    """Rows -> (X, y). X columns: crew, cleaned_dwell, wi_complexity, milestone_phase."""
    X, y = [], []
    for r in rows:
        X.append([r.crew_at_op or 1.0, r.cleaned_dwell_days or 0.0,
                  r.wi_complexity_score or 0.0, float(r.milestone_phase or 0)])
        y.append(r.residual_days if r.residual_days is not None else 0.0)
    return X, y


def _train_quantiles(X, y):
    """Fit P50 + P80 quantile models. Falls back to a constant (mean/quantile) if sklearn
    can't fit (tiny n). Returns (p50_model, p80_model)."""
    from sklearn.linear_model import QuantileRegressor
    p50 = QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs").fit(X, y)
    p80 = QuantileRegressor(quantile=0.8, alpha=0.0, solver="highs").fit(X, y)
    return p50, p80


def _threshold_for(program: str) -> int:
    return settings.n_train_threshold.get(program, settings.n_train_threshold_default)


async def train_program(db: AsyncSession, program: str) -> dict:
    rows = (await db.execute(
        select(MLTrainingRow).where(MLTrainingRow.program == program))).scalars().all()
    n = len(rows)
    thr = _threshold_for(program)
    if n < thr:
        return dict(program=program, trained=False, n=n,
                    reason=f"n={n} < threshold {thr} (stays EMPIRICAL)")
    X, y = _feature_matrix(rows)
    try:
        p50, p80 = _train_quantiles(X, y)
        p50_blob, p80_blob = pickle.dumps(p50), pickle.dumps(p80)
    except Exception as e:
        return dict(program=program, trained=False, n=n, reason=f"fit failed: {e}")
    # deactivate old versions, insert new active
    await db.execute(update(ModelVersion).where(ModelVersion.program == program)
                     .values(active=False))
    db.add(ModelVersion(program=program, model_type="TRAINED", n_scored=n,
                        p50_blob=p50_blob, p80_blob=p80_blob, active=True,
                        trained_at=datetime.now(timezone.utc)))
    await db.commit()
    return dict(program=program, trained=True, n=n)


async def train_all(db: AsyncSession) -> list:
    return [await train_program(db, p) for p in ("ELEV", "RAD", "AEGIS")]
