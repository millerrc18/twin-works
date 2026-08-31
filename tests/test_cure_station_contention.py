"""Discrete cure-station contention tests for the finite-capacity scheduler."""
from datetime import datetime, timedelta

from capacity_engine import simulate


AS_OF = datetime(2026, 8, 24, 6, 0)
OPS = {"TEST": [(100, "Apply material", "TESTWC", 1.0, "FLOW")]}
CURES = {"TEST": [(100, "CURE - Station hold", 4.0, "test fixture")]}


def _units(count=3):
    return [
        dict(serial=f"U{index}", so=f"SO{index}", maxop=0,
             commit=AS_OF.date(), program="TEST")
        for index in range(1, count + 1)
    ]


def _profile(capacity=1):
    return {
        "cure_station_capacities": {"TEST_STATION": capacity},
        "cure_station_rules": {("TEST", 100, "CURE - Station hold"): "TEST_STATION"},
        "shift_budgets": {("TEST", "TESTWC"): {1: 8.0, 2: 8.0, 3: 8.0}},
        "budget_programs": ["TEST"],
        "dpas_programs": set(),
    }


def test_cure_station_capacity_serializes_cures_after_slots_are_full():
    result = simulate(_units(), OPS, CURES, AS_OF, profile=_profile(capacity=1))

    starts = [result[f"U{index}"]["cure_dt"]["CURE - Station hold"] for index in range(1, 4)]

    assert starts == [
        AS_OF + timedelta(hours=1),
        AS_OF + timedelta(hours=5),
        AS_OF + timedelta(hours=9),
    ]


def test_cure_station_capacity_allows_parallel_cures_up_to_slot_count():
    result = simulate(_units(), OPS, CURES, AS_OF, profile=_profile(capacity=2))

    starts = [result[f"U{index}"]["cure_dt"]["CURE - Station hold"] for index in range(1, 4)]

    assert starts == [
        AS_OF + timedelta(hours=1),
        AS_OF + timedelta(hours=1),
        AS_OF + timedelta(hours=5),
    ]


def test_seed_cure_station_rules_cover_only_validated_constraints():
    import routers as R

    def cure_label(cures, after_op, marker):
        return next(label for op, label, *_ in cures if op == after_op and marker in label)

    dry_to_handle = cure_label(R.ELEVATOR_CURES, 3800, "dry-to-handle")
    cor_ban = cure_label(R.ELEVATOR_CURES, 4010, "Cor Ban")
    electrical_seal = cure_label(R.RADOME_CURES, 775, "Electrical Sealing")

    assert R.CURE_STATION_CAPACITIES == {
        "P2_PAINT_BOOTH": 2,
        "P3_ELECTRICAL_SEAL": 1,
    }
    assert R.CURE_STATION_RULES == {
        ("ELEV", 3800, dry_to_handle): "P2_PAINT_BOOTH",
        ("ELEV", 4010, cor_ban): "P2_PAINT_BOOTH",
        ("RAD", 775, electrical_seal): "P3_ELECTRICAL_SEAL",
    }
    assert all("Topcoat 24hr" not in label for _program, _op, label in R.CURE_STATION_RULES)

def test_wrapper_profile_exposes_seed_cure_station_constraints():
    from app.engines import rtg_wrapper as wrapper
    import routers as R

    profile = wrapper._simulation_profile()

    assert profile["cure_station_capacities"] == R.CURE_STATION_CAPACITIES
    assert profile["cure_station_rules"] == R.CURE_STATION_RULES