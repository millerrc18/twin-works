"""Pure timing-summary coverage for the read-only Aeronose IFS audit."""
from datetime import datetime, timedelta

from scripts.audit_aeronose_tooling import _summarize_intervals


def _row(so: str, start_hour: int, finish_hour: int) -> dict:
    anchor = datetime(2026, 9, 1)
    return {
        "so": so,
        "started": anchor + timedelta(hours=start_hour),
        "finished": anchor + timedelta(hours=finish_hour),
        "elapsed_hours": finish_hour - start_hour,
    }


def test_timing_summary_reports_valid_reuse_gaps_only_when_clock_spans_fit():
    summary = _summarize_intervals([
        _row("1", 0, 4),
        _row("2", 5, 8),
        _row("3", 9, 12),
    ], capacity=1)

    assert summary["max_concurrent"] == 1
    assert summary["clock_span_fits_owner_count"] is True
    assert summary["reuse_gaps_hours"] == {
        "valid": True,
        "count": 2,
        "minimum": 1.0,
        "median": 1.0,
    }


def test_timing_summary_invalidates_reuse_when_clock_spans_exceed_count():
    summary = _summarize_intervals([
        _row("1", 0, 6),
        _row("2", 2, 8),
    ], capacity=1)

    assert summary["max_concurrent"] == 2
    assert summary["clock_span_fits_owner_count"] is False
    assert summary["reuse_gaps_hours"]["valid"] is False
    assert summary["reuse_gaps_hours"]["count"] == 0


def test_timing_summary_can_measure_unconstrained_parallel_labor():
    summary = _summarize_intervals([
        _row("1", 0, 6),
        _row("2", 2, 8),
        _row("3", 4, 10),
    ], capacity=None)

    assert summary["configured_slots"] is None
    assert summary["max_concurrent"] == 3
    assert "reuse_gaps_hours" not in summary
