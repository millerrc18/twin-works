"""RATE-01c historical throughput and labor calibration contracts."""
import json
from datetime import date, datetime
from decimal import Decimal


def test_program_calibration_metrics_and_tooling_independent_readiness():
    from app.services.rate_calibration import (
        CalibrationOrder,
        CalibrationPeriod,
        CalibrationThresholds,
        calibrate_program,
    )

    report = calibrate_program(
        program="RAD",
        orders=(
            CalibrationOrder(
                order_no="A", program="RAD",
                actual_start=datetime(2026, 1, 1, 6),
                actual_completion=datetime(2026, 1, 11, 6),
                modeled_completion=datetime(2026, 1, 13, 6),
                planned_labor_hours=Decimal("90"),
                actual_labor_hours=Decimal("100"),
                routing_revision="17"),
            CalibrationOrder(
                order_no="B", program="RAD",
                actual_start=datetime(2026, 1, 1, 6),
                actual_completion=datetime(2026, 1, 21, 6),
                modeled_completion=datetime(2026, 1, 18, 6),
                planned_labor_hours=Decimal("220"),
                actual_labor_hours=Decimal("200"),
                routing_revision="17"),
        ),
        periods=(CalibrationPeriod(
            month=date(2026, 1, 1), actual_releases=2,
            actual_completions=2, modeled_completions=2,
            actual_average_wip=Decimal("1.2"),
            modeled_average_wip=Decimal("1.3")),),
        thresholds=CalibrationThresholds(
            minimum_orders=2,
            cycle_mae_days_max=Decimal("3"),
            completion_wape_max=Decimal("0.10"),
            wip_wape_max=Decimal("0.20"),
            labor_wape_max=Decimal("0.15")),
        staffing_readiness="PROVISIONAL",
        tooling_readiness="UNRESOLVED",
        thresholds_approved=True,
    )

    assert report.metrics.sample_orders == 2
    assert report.metrics.cycle_mae_days == Decimal("2.5")
    assert report.metrics.cycle_bias_days == Decimal("-0.5")
    assert report.metrics.completion_wape == Decimal("0")
    assert report.metrics.wip_wape == Decimal("0.0833")
    assert report.metrics.labor_wape == Decimal("0.1000")
    assert report.labor_calibration_status == "READY"
    assert report.overall_readiness == "PARTIAL"
    assert not report.full_rate_recommendations_enabled
    assert "TOOLING_UNRESOLVED" in report.blockers
    assert "STAFFING_PROVISIONAL" in report.blockers


def test_failed_thresholds_block_labor_solver_even_when_tooling_ready():
    from app.services.rate_calibration import (
        CalibrationOrder,
        CalibrationPeriod,
        CalibrationThresholds,
        calibrate_program,
    )

    report = calibrate_program(
        program="ELEV",
        orders=(CalibrationOrder(
            order_no="E1", program="ELEV",
            actual_start=datetime(2026, 1, 1),
            actual_completion=datetime(2026, 1, 11),
            modeled_completion=datetime(2026, 1, 21),
            planned_labor_hours=Decimal("100"),
            actual_labor_hours=Decimal("200"), routing_revision="3"),),
        periods=(CalibrationPeriod(
            month=date(2026, 1, 1), actual_releases=1,
            actual_completions=1, modeled_completions=0,
            actual_average_wip=Decimal("1"), modeled_average_wip=Decimal("2")),),
        thresholds=CalibrationThresholds(
            minimum_orders=1, cycle_mae_days_max=Decimal("3"),
            completion_wape_max=Decimal("0.2"), wip_wape_max=Decimal("0.2"),
            labor_wape_max=Decimal("0.2")),
        staffing_readiness="READY", tooling_readiness="READY")

    assert report.labor_calibration_status == "FAILED"
    assert report.overall_readiness == "FAILED"
    assert "CYCLE_MAE" in report.blockers
    assert "COMPLETION_WAPE" in report.blockers
    assert "WIP_WAPE" in report.blockers
    assert "LABOR_WAPE" in report.blockers


def test_insufficient_sample_is_provisional_not_failed():
    from app.services.rate_calibration import (
        CalibrationOrder,
        CalibrationPeriod,
        CalibrationThresholds,
        calibrate_program,
    )

    report = calibrate_program(
        program="RAD",
        orders=(CalibrationOrder(
            order_no="R1", program="RAD",
            actual_start=datetime(2026, 1, 1),
            actual_completion=datetime(2026, 1, 2),
            modeled_completion=datetime(2026, 1, 2),
            planned_labor_hours=Decimal("10"),
            actual_labor_hours=Decimal("10"), routing_revision="17"),),
        periods=(CalibrationPeriod(
            month=date(2026, 1, 1), actual_releases=1,
            actual_completions=1, modeled_completions=1,
            actual_average_wip=Decimal("1"), modeled_average_wip=Decimal("1")),),
        thresholds=CalibrationThresholds(
            minimum_orders=5, cycle_mae_days_max=Decimal("1"),
            completion_wape_max=Decimal("0.1"), wip_wape_max=Decimal("0.1"),
            labor_wape_max=Decimal("0.1")),
        staffing_readiness="UNRESOLVED", tooling_readiness="UNRESOLVED")

    assert report.labor_calibration_status == "PROVISIONAL"
    assert "INSUFFICIENT_SAMPLE" in report.blockers


def test_monthly_periods_reconstruct_actual_and_modeled_wip_half_open():
    from app.services.rate_calibration import CalibrationOrder, build_monthly_periods

    periods = build_monthly_periods(
        orders=(CalibrationOrder(
            order_no="R1", program="RAD",
            actual_start=datetime(2026, 1, 1),
            actual_completion=datetime(2026, 1, 31),
            modeled_completion=datetime(2026, 2, 11),
            planned_labor_hours=Decimal("10"),
            actual_labor_hours=Decimal("10"), routing_revision="17"),),
        measurement_start=date(2026, 1, 1),
        measurement_end=date(2026, 2, 28),
    )

    assert [(row.month, row.actual_releases, row.actual_completions,
             row.modeled_completions) for row in periods] == [
        (date(2026, 1, 1), 1, 1, 0),
        (date(2026, 2, 1), 0, 0, 1),
    ]
    assert periods[0].actual_average_wip == Decimal("0.9677")
    assert periods[0].modeled_average_wip == Decimal("1.0000")
    assert periods[1].actual_average_wip == Decimal("0.0000")
    assert periods[1].modeled_average_wip == Decimal("0.3571")


def test_monthly_wip_includes_units_still_open_at_measurement_end():
    from app.services.rate_calibration import CalibrationFlowUnit, build_monthly_periods

    periods = build_monthly_periods(
        orders=(),
        flow_units=(CalibrationFlowUnit(
            order_no="OPEN", program="RAD",
            actual_start=datetime(2026, 1, 15), actual_completion=None,
            modeled_completion=datetime(2026, 3, 15)),),
        measurement_start=date(2026, 1, 1),
        measurement_end=date(2026, 2, 28))

    assert periods[0].actual_average_wip == Decimal("0.5484")
    assert periods[1].actual_average_wip == Decimal("1.0000")
    assert periods[0].actual_completions == 0
    assert periods[1].actual_completions == 0


def test_monthly_periods_clip_final_partial_month_at_measurement_end():
    from app.services.rate_calibration import CalibrationFlowUnit, build_monthly_periods

    periods = build_monthly_periods(
        orders=(),
        flow_units=(CalibrationFlowUnit(
            order_no='LATE', program='RAD',
            actual_start=datetime(2026, 9, 1),
            actual_completion=datetime(2026, 9, 18),
            modeled_completion=datetime(2026, 9, 20)),),
        measurement_start=date(2026, 9, 1),
        measurement_end=date(2026, 9, 17),
    )

    assert periods[0].actual_releases == 1
    assert periods[0].actual_completions == 0
    assert periods[0].modeled_completions == 0
    assert periods[0].actual_average_wip == Decimal('1.0000')
    assert periods[0].modeled_average_wip == Decimal('1.0000')


def test_work_center_labor_rollup_keeps_program_and_wc_separate():
    from app.services.rate_calibration import WorkCenterLabor, rollup_work_center_labor

    result = rollup_work_center_labor((
        WorkCenterLabor("RAD", "AEROA", Decimal("10"), Decimal("12")),
        WorkCenterLabor("RAD", "AEROA", Decimal("5"), Decimal("4")),
        WorkCenterLabor("ELEV", "32684", Decimal("20"), Decimal("25")),
    ))

    assert result[("RAD", "AEROA")].planned_hours == Decimal("15")
    assert result[("RAD", "AEROA")].actual_hours == Decimal("16")
    assert result[("RAD", "AEROA")].labor_wape == Decimal("0.0625")
    assert result[("ELEV", "32684")].labor_wape == Decimal("0.2000")


def test_runner_serializes_work_center_rollups_with_string_keys():
    from app.services.rate_calibration import WorkCenterLabor
    from scripts.calibrate_rate_history import (
        _json_default,
        _work_center_labor_payload,
    )

    payload = _work_center_labor_payload((
        WorkCenterLabor('RAD', 'AEROA', Decimal('10'), Decimal('12')),
    ))
    encoded = json.dumps(payload, default=_json_default)

    assert list(payload) == ['AEROA']
    assert 'AEROA' in encoded


def test_order_validation_rejects_completion_before_start_and_program_mismatch():
    from app.services.rate_calibration import (
        CalibrationError,
        CalibrationOrder,
        CalibrationThresholds,
        calibrate_program,
    )

    invalid = CalibrationOrder(
        order_no="BAD", program="ELEV",
        actual_start=datetime(2026, 1, 2),
        actual_completion=datetime(2026, 1, 1),
        modeled_completion=datetime(2026, 1, 3),
        planned_labor_hours=Decimal("1"), actual_labor_hours=Decimal("1"),
        routing_revision="3")
    try:
        calibrate_program(
            program="RAD", orders=(invalid,), periods=(),
            thresholds=CalibrationThresholds(
                minimum_orders=1, cycle_mae_days_max=Decimal("1"),
                completion_wape_max=Decimal("1"), wip_wape_max=Decimal("1"),
                labor_wape_max=Decimal("1")),
            staffing_readiness="READY", tooling_readiness="READY")
    except CalibrationError as exc:
        assert "program mismatch" in str(exc) or "completion" in str(exc)
    else:
        raise AssertionError("invalid calibration order was accepted")


def test_unapproved_thresholds_keep_calibration_provisional():
    from app.services.rate_calibration import (
        CalibrationOrder,
        CalibrationPeriod,
        CalibrationThresholds,
        calibrate_program,
    )

    report = calibrate_program(
        program="RAD",
        orders=(CalibrationOrder(
            order_no="R1", program="RAD",
            actual_start=datetime(2026, 1, 1),
            actual_completion=datetime(2026, 1, 2),
            modeled_completion=datetime(2026, 1, 2),
            planned_labor_hours=Decimal("10"),
            actual_labor_hours=Decimal("10"), routing_revision="17"),),
        periods=(CalibrationPeriod(
            month=date(2026, 1, 1), actual_releases=1,
            actual_completions=1, modeled_completions=1,
            actual_average_wip=Decimal("1"), modeled_average_wip=Decimal("1")),),
        thresholds=CalibrationThresholds(
            minimum_orders=1, cycle_mae_days_max=Decimal("1"),
            completion_wape_max=Decimal("0.1"), wip_wape_max=Decimal("0.1"),
            labor_wape_max=Decimal("0.1")),
        staffing_readiness="READY", tooling_readiness="READY",
        thresholds_approved=False)

    assert report.labor_calibration_status == "PROVISIONAL"
    assert report.overall_readiness == "PARTIAL"
    assert "THRESHOLDS_UNAPPROVED" in report.blockers
