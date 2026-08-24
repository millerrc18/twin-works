"""FeatureBuilder — turns a unit's clocking signals + WI constraints into a feature vector
for the residual model. Locked feature set (validated in the signal-vetting spike):

  crew_at_op        : max effective crew (N_EMP) on the unit's swarm ops — strongest signal
  cleaned_dwell_days: total clock-span MINUS WI cure floor MINUS rework noise — the true
                      "unit sat stuck" signal (de-confounded from mandated cure by WI floors)
  wi_complexity     : WI hold-point / cure-mention density (from P2 extraction)
  milestone_phase   : ordinal position (0..3) — later phase = less remaining slip
  sharedwc_queue    : NaN until validated (P6) — carried, never load-bearing

Rework cleaning rule (DROP from dwell): op9/op50 admin buckets + any op with span>30d
(closeout re-clock, not real dwell). config.USE_CLEANED_DWELL falls back to raw.
"""
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path

from app.config import settings
from app.engines.router_registry import registry

BASE = Path(__file__).resolve().parent.parent.parent
SIGNALS_JSON = BASE / "wi_signals.json"

REWORK_OPS = {9, 50}          # admin/closeout re-clock buckets (drop)
REWORK_SPAN_DAYS = 30.0       # any op sitting >30d = re-clock noise, not dwell


@dataclass
class FeatureVector:
    serial: str
    so: str
    program: str
    crew_at_op: float
    raw_dwell_days: float
    cleaned_dwell_days: float
    wi_complexity_score: float
    milestone_phase: int
    sharedwc_queue: float  # NaN sentinel until P6

    def to_row(self) -> dict:
        return asdict(self)

    def model_features(self) -> list:
        """Ordered numeric vector for the trained model (P6). sharedwc dropped if NaN."""
        feats = [self.crew_at_op, self.cleaned_dwell_days, self.wi_complexity_score,
                 float(self.milestone_phase)]
        if not math.isnan(self.sharedwc_queue):
            feats.append(self.sharedwc_queue)
        return feats


class FeatureBuilder:
    def __init__(self, signals_path=None):
        p = signals_path or SIGNALS_JSON
        self.signals = json.load(open(p)) if Path(p).exists() else {}
        self._wi_complexity = {}

    def wi_complexity(self, program: str) -> float:
        """Density score from P2 WI extraction (hold_points + cure_mentions per 10k chars)."""
        if program not in self._wi_complexity:
            try:
                from ml.wi.wi_service import get_complexity_features
                c = get_complexity_features(program)
                chars = max(1, c.get("char_count", 1))
                score = 10000.0 * (c.get("hold_points", 0) + c.get("cure_mentions", 0)) / chars
                self._wi_complexity[program] = round(score, 2)
            except Exception:
                self._wi_complexity[program] = 0.0
        return self._wi_complexity[program]

    def _dwell(self, so: str, maxop: int | None, program: str):
        """Return (raw_dwell_days, cleaned_dwell_days, crew_at_op) from op signals."""
        ops = self.signals.get(so, {})
        raw = 0.0
        cleaned = 0.0
        crew = 1.0
        spec = registry.spec(program)
        for opno_s, s in ops.items():
            opno = int(opno_s)
            span = s.get("span_days") or 0.0
            n_emp = s.get("n_emp") or 1
            crew = max(crew, float(n_emp))
            raw += span
            # rework cleaning: drop admin buckets + long-span re-clocks
            if opno in REWORK_OPS or span > REWORK_SPAN_DAYS:
                continue
            cleaned += span
        # de-confound: subtract the WI-mandated cure floor already elapsed up to maxop.
        # (cures run wall-clock inside the span; they're mandated, not "stuck".)
        cure_floor_h = spec.cure_floor_hours(None) - spec.cure_floor_hours(maxop)
        cleaned = max(0.0, cleaned - cure_floor_h / 24.0)
        return round(raw, 2), round(cleaned, 2), crew

    def build(self, serial: str, so: str, program: str, maxop: int | None) -> FeatureVector:
        raw, cleaned, crew = self._dwell(so, maxop, program)
        spec = registry.spec(program)
        phase = [c for c, _ in spec.ceilings].index(spec.milestone_of(maxop))
        if not settings.use_cleaned_dwell:
            cleaned = raw
        return FeatureVector(serial=serial, so=so, program=program,
                             crew_at_op=crew, raw_dwell_days=raw,
                             cleaned_dwell_days=cleaned,
                             wi_complexity_score=self.wi_complexity(program),
                             milestone_phase=phase,
                             sharedwc_queue=float("nan"))
