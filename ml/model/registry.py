"""Model registry with the threshold gate.

EMPIRICAL path (n<threshold): residual = measured optimistic bias from accuracy_results.json.
TRAINED path (n>=threshold): quantile models loaded from the active ModelVersion row predict
P50/P80 residuals from the unit's feature vector.

Residual convention: residual_days = actual - sim (add to sim to de-bias). Backtest reports
bias = sim - actual (negative = optimistic), so empirical residual = -bias. P80 >= P50 always.

The trained models are loaded into a module cache at startup / after retrain (load_trained),
so predict() stays synchronous for the forecast hot path.
"""
import json
import pickle
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
ACCURACY_JSON = BASE / "accuracy_results.json"


@dataclass
class ResidualPrediction:
    p50_days: float
    p80_days: float
    mode: str          # EMPIRICAL | TRAINED
    n_scored: int


class ModelRegistry:
    def __init__(self, threshold: dict | int | None = None):
        from app.config import settings
        # per-program thresholds {ELEV:25, RAD:25, AEGIS:12} + a scalar default fallback.
        if isinstance(threshold, int):
            self._thresholds, self._threshold_default = {}, threshold
        else:
            self._thresholds = dict(threshold or settings.n_train_threshold)
            self._threshold_default = settings.n_train_threshold_default
        self._acc = None
        self._trained = {}     # program -> {"p50":model,"p80":model,"n":int}
        self._scored = {}      # program -> real scored-row count (from DB, set by load_trained)
        self._load_accuracy()

    def threshold_for(self, program: str) -> int:
        return self._thresholds.get(program, self._threshold_default)

    def _load_accuracy(self):
        if ACCURACY_JSON.exists():
            try:
                self._acc = json.load(open(ACCURACY_JSON))
            except Exception:
                self._acc = None

    def load_trained(self, versions: list, scored_counts: dict):
        """Called at startup / after retrain with the active ModelVersion rows + per-program
        scored counts. versions: list of (program, p50_blob, p80_blob, n_scored)."""
        self._trained = {}
        for (program, p50_blob, p80_blob, n) in versions:
            if p50_blob and p80_blob:
                self._trained[program] = dict(p50=pickle.loads(p50_blob),
                                              p80=pickle.loads(p80_blob), n=n)
        self._scored = dict(scored_counts or {})

    def _empirical_bias(self, program: str):
        if not self._acc:
            return 0.0, 0
        for row in self._acc.get("by_program_horizon", []):
            if row.get("program") == program and row.get("horizon") == "ALL":
                pk = row.get("pack", {})
                if pk.get("n"):
                    return pk.get("bias", 0.0) or 0.0, pk["n"]
        ov = self._acc.get("overall", {}).get("pack", {})
        return (ov.get("bias", 0.0) or 0.0), ov.get("n", 0)

    def scored_count(self, program: str) -> int:
        # real scored-ship count from the training DB (0 until load_trained runs / rows exist).
        # NOT the backtest horizon count — that would overstate how much real data we have.
        return self._scored.get(program, 0)

    def predict(self, program: str, features: list | None = None) -> ResidualPrediction:
        n = self.scored_count(program)
        # TRAINED path
        if program in self._trained and n >= self.threshold_for(program) and features is not None:
            m = self._trained[program]
            p50 = float(m["p50"].predict([features])[0])
            p80 = float(m["p80"].predict([features])[0])
            if p80 < p50:
                p80 = p50
            return ResidualPrediction(p50_days=p50, p80_days=p80, mode="TRAINED", n_scored=n)
        # EMPIRICAL fallback
        bias, _bn = self._empirical_bias(program)
        residual_p50 = -bias
        spread = abs(bias) * 0.5
        return ResidualPrediction(p50_days=residual_p50, p80_days=residual_p50 + spread,
                                  mode="EMPIRICAL", n_scored=n)

    @staticmethod
    def apply(sim_finish: date, pred: ResidualPrediction) -> tuple[date, date]:
        return (sim_finish + timedelta(days=round(pred.p50_days)),
                sim_finish + timedelta(days=round(pred.p80_days)))


registry_model = ModelRegistry()
