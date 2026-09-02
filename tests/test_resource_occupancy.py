"""Deterministic atomic occupancy lease behavior."""
from datetime import date, datetime
import asyncio

import pytest

from app.engines.occupancy import (
    InvalidOccupancyRelease,
    OccupancyAllocator,
    OccupancyRequest,
    ResourceAllocationDeadlock,
    occupancy_queue_key,
)


START = datetime(2026, 9, 2, 6)


def test_fungible_slots_allow_two_concurrent_holds_and_delay_the_third():
    allocator = OccupancyAllocator({"JIG": 2}, as_of=START)

    first = allocator.reserve_fixed("U1", [OccupancyRequest("JIG")], START, 8)
    second = allocator.reserve_fixed("U2", [OccupancyRequest("JIG")], START, 8)
    third = allocator.reserve_fixed("U3", [OccupancyRequest("JIG")], START, 8)

    assert first.start == second.start == START
    assert third.start == datetime(2026, 9, 2, 14)
    assert {first.leases[0].instance_code, second.leases[0].instance_code} == {
        "JIG#1", "JIG#2",
    }


def test_atomic_multi_tool_request_waits_for_every_pool_without_partial_acquisition():
    allocator = OccupancyAllocator({"JIG": 1, "HOLD": 1}, as_of=START)
    allocator.reserve_fixed("JIG-OWNER", [OccupancyRequest("JIG")], START, 4)
    allocator.reserve_fixed("HOLD-OWNER", [OccupancyRequest("HOLD")], START, 6)

    reservation = allocator.reserve_fixed(
        "U1", [OccupancyRequest("HOLD"), OccupancyRequest("JIG")], START, 2)

    assert reservation.start == datetime(2026, 9, 2, 12)
    assert reservation.end == datetime(2026, 9, 2, 14)
    assert [lease.pool_code for lease in reservation.leases] == ["HOLD", "JIG"]


def test_named_instance_and_minimum_hold_are_enforced():
    allocator = OccupancyAllocator(
        {"MOLD": 2}, instances={"MOLD": ["MOLD-A", "MOLD-B"]}, as_of=START)
    first = allocator.reserve_fixed(
        "U1", [OccupancyRequest("MOLD", instance_code="MOLD-B", min_hold_hours=6)],
        START, 2,
    )
    second = allocator.reserve_fixed(
        "U2", [OccupancyRequest("MOLD", instance_code="MOLD-B")], START, 1)

    assert first.end == datetime(2026, 9, 2, 12)
    assert second.start == first.end
    assert second.leases[0].instance_code == "MOLD-B"


def test_request_order_does_not_change_atomic_reservation():
    left = OccupancyAllocator({"A": 1, "B": 1}, as_of=START)
    right = OccupancyAllocator({"A": 1, "B": 1}, as_of=START)

    a = left.reserve_fixed(
        "U1", [OccupancyRequest("B"), OccupancyRequest("A")], START, 3)
    b = right.reserve_fixed(
        "U1", [OccupancyRequest("A"), OccupancyRequest("B")], START, 3)

    assert a == b


def test_impossible_or_invalid_requests_fail_loudly_without_mutating_slots():
    allocator = OccupancyAllocator({"JIG": 1}, as_of=START)
    before = allocator.availability()

    with pytest.raises(ResourceAllocationDeadlock, match="requires 2 slots"):
        allocator.reserve_fixed(
            "U1", [OccupancyRequest("JIG", quantity=2)], START, 2)
    with pytest.raises(ResourceAllocationDeadlock, match="unknown pool"):
        allocator.reserve_fixed("U1", [OccupancyRequest("MISSING")], START, 2)

    assert allocator.availability() == before


def test_cross_operation_leases_acquire_atomically_and_release_after_hold_and_lag():
    allocator = OccupancyAllocator({"JIG": 1, "HOLD": 1}, as_of=START)
    requests = [
        OccupancyRequest("JIG", min_hold_hours=6, lag_hours=1),
        OccupancyRequest("HOLD", min_hold_hours=2),
    ]

    leases = allocator.acquire_atomic("U1", requests, START)
    assert leases is not None
    before_failed_request = allocator.availability()
    assert allocator.acquire_atomic("U2", requests, START) is None
    assert allocator.availability() == before_failed_request

    hold_ready = allocator.release("U1", "HOLD", datetime(2026, 9, 2, 7))
    jig_ready = allocator.release("U1", "JIG", datetime(2026, 9, 2, 7))
    assert hold_ready == datetime(2026, 9, 2, 8)
    assert jig_ready == datetime(2026, 9, 2, 13)
    assert allocator.acquire_atomic(
        "U2", [OccupancyRequest("JIG")], datetime(2026, 9, 2, 12)) is None
    assert allocator.acquire_atomic(
        "U2", [OccupancyRequest("JIG")], datetime(2026, 9, 2, 13)) is not None
    assert [event.event_type for event in allocator.history()] == [
        "ACQUIRE", "ACQUIRE", "RELEASE", "RELEASE", "ACQUIRE",
    ]


def test_invalid_release_fails_loudly():
    allocator = OccupancyAllocator({"JIG": 1}, as_of=START)
    with pytest.raises(InvalidOccupancyRelease, match="no active lease"):
        allocator.release("U1", "JIG", START)


def test_queue_key_is_explicit_and_independent_of_input_order():
    units = [
        {"program": "RAD", "serial": "R2", "commit": date(2026, 9, 5)},
        {"program": "AEGIS", "serial": "A1", "commit": date(2026, 9, 1)},
        {"program": "RAD", "serial": "R1", "commit": date(2026, 9, 5)},
    ]
    expected = ["A1", "R1", "R2"]

    def ordered(rows):
        return [
            row["serial"] for row in sorted(
                rows,
                key=lambda unit: occupancy_queue_key(
                    unit, START, date(2026, 9, 2), {"AEGIS"}, "TOOL"),
            )
        ]

    assert ordered(units) == expected
    assert ordered(list(reversed(units))) == expected


def _scheduler_profile(requirements, capacities):
    return {
        "resource_mode": "DB_SHADOW",
        "allocation_mode": "LEGACY_COMPAT",
        "crew_by_program": {},
        "dpas_programs": set(),
        "shift_budgets": {("P1", "WC"): {1: 24.0, 2: 0.0, 3: 0.0}},
        "budget_programs": ["P1"],
        "shared_wcs": set(),
        "operation_pools": {},
        "pool_shift_budgets": {},
        "pool_external_reserves": {},
        "pool_calendar_policies": {},
        "pool_assumption_ids": {},
        "occupancy_requirements": requirements,
        "occupancy_pool_capacities": capacities,
        "occupancy_pool_instances": {},
        "cure_station_capacities": {},
        "cure_station_rules": {},
        "parallel_cure_gates": {},
    }


def test_scheduler_holds_tool_across_operations_and_releases_for_next_unit():
    from capacity_engine import simulate

    ops = {"P1": [
        (100, "Acquire jig", "WC", 2.0, "BUILD"),
        (200, "Release jig", "WC", 2.0, "BUILD"),
        (300, "Finish", "WC", 1.0, "SHIP"),
    ]}
    profile = _scheduler_profile(
        {("P1", 100): ({
            "pool_code": "JIG", "quantity": 1, "instance_code": None,
            "release_event": "OP_COMPLETE", "release_op": 200,
            "min_hold_hours": 0.0, "lag_hours": 0.0,
        },)},
        {"JIG": 1},
    )
    units = [
        {"serial": "U1", "so": "1", "maxop": 0,
         "commit": date(2026, 9, 3), "program": "P1"},
        {"serial": "U2", "so": "2", "maxop": 0,
         "commit": date(2026, 9, 4), "program": "P1"},
    ]

    result = simulate(
        units, ops, {"P1": []}, START, profile=profile, trace_constraints=True)

    assert result["U1"]["op_dt"][100] == START
    assert result["U2"]["op_dt"][100] >= result["U1"]["op_dt"][200]
    waits = [event for event in result["U2"]["constraint_events"]
             if event["event_type"] == "OCCUPANCY_WAIT"]
    assert waits and waits[0]["pool_code"] == "JIG"


def test_scheduler_acquires_multiple_required_tools_atomically():
    from capacity_engine import simulate

    def requirement(pool):
        return {
            "pool_code": pool, "quantity": 1, "instance_code": None,
            "release_event": "ROUTE_COMPLETE", "release_op": None,
            "min_hold_hours": 0.0, "lag_hours": 0.0,
        }
    profile = _scheduler_profile(
        {("P1", 100): (requirement("JIG"), requirement("HOLD"))},
        {"JIG": 1, "HOLD": 1},
    )
    units = [
        {"serial": "U1", "so": "1", "maxop": 0,
         "commit": date(2026, 9, 3), "program": "P1"},
        {"serial": "U2", "so": "2", "maxop": 0,
         "commit": date(2026, 9, 4), "program": "P1"},
    ]

    result = simulate(
        units, {"P1": [(100, "Build", "WC", 2.0, "SHIP")]},
        {"P1": []}, START, profile=profile, trace_constraints=True)

    assert result["U1"]["finish"] < result["U2"]["finish"]
    waited = {event["pool_code"] for event in result["U2"]["constraint_events"]
              if event["event_type"] == "OCCUPANCY_WAIT"}
    assert waited == {"HOLD", "JIG"}


def test_scheduler_releases_tool_at_actual_cure_completion():
    from capacity_engine import simulate

    profile = _scheduler_profile(
        {("P1", 100): ({
            "pool_code": "MOLD", "quantity": 1, "instance_code": None,
            "release_event": "CURE_COMPLETE", "release_op": 100,
            "min_hold_hours": 0.0, "lag_hours": 0.0,
        },)},
        {"MOLD": 1},
    )
    units = [
        {"serial": "U1", "so": "1", "maxop": 0,
         "commit": date(2026, 9, 3), "program": "P1"},
        {"serial": "U2", "so": "2", "maxop": 0,
         "commit": date(2026, 9, 4), "program": "P1"},
    ]

    result = simulate(
        units,
        {"P1": [(100, "Mold and cure", "WC", 1.0, "BUILD")]},
        {"P1": [(100, "CURE - Mold hold", 4.0, "test")]},
        START, profile=profile, trace_constraints=True,
    )

    assert result["U1"]["cure_dt"]["CURE - Mold hold"] == datetime(2026, 9, 2, 7)
    assert result["U2"]["op_dt"][100] == datetime(2026, 9, 2, 11)


def test_profile_compiles_only_approved_occupancy_bindings(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import routers
    from app.database import Base
    from app.services.resource_profile import (
        compile_profile,
        persist_replay_snapshot,
        replay_snapshot,
        seed_legacy_resources,
    )
    from app.services.resource_registry import (
        add_assumption,
        add_binding,
        add_capacity_version,
        create_pool,
    )

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'occupancy-profile.db').as_posix()}"
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            await seed_legacy_resources(db)
            pool = await create_pool(
                db, code="TEST_RAD_TOOL", site="59", name="Test Radome tool",
                resource_type="TOOL", capacity_unit="SLOTS",
            )
            assumption = await add_assumption(
                db, subject_type="POOL", subject_key=pool.code,
                parameter="slot_count", value=1, unit="SLOTS",
                basis="OWNER_CONFIRMED", approval_status="APPROVED",
                commitment_grade="INTERNAL_ONLY", effective_from=date(2026, 8, 19),
                owner="Test owner", approver="Test approver",
            )
            await add_capacity_version(
                db, pool_id=pool.id, effective_from=date(2026, 8, 19),
                status="APPROVED", capacity_scope="NET_TRACKED",
                slot_count=1, assumption_id=assumption.id,
            )
            await add_binding(
                db, program="RAD", pool_id=pool.id,
                acquire_op=130, release_op=170,
                requirement_mode="OCCUPANCY", quantity=1,
                demand_source="FIXED", release_event="OP_COMPLETE",
                min_hold_hours=4, lag_hours=1, status="APPROVED",
                valid_operations={row[0] for row in routers.RADOME_OPS},
            )
            from app.data.snapshot_source import SnapshotDataSource
            ds = SnapshotDataSource(use_position_state=False)
            compiled = await compile_profile(
                db, programs=["RAD"], as_of=ds.as_of(),
                horizon_end=date(2026, 10, 1), mode="DB_SHADOW",
            )

            assert compiled.scheduler_profile["occupancy_pool_capacities"] == {
                "TEST_RAD_TOOL": 1,
            }
            assert compiled.scheduler_profile["occupancy_requirements"][("RAD", 130)] == ({
                "pool_code": "TEST_RAD_TOOL",
                "quantity": 1,
                "instance_code": None,
                "release_event": "OP_COMPLETE",
                "release_op": 170,
                "min_hold_hours": 4.0,
                "lag_hours": 1.0,
                "assumption_id": None,
            },)
            assert compiled.readiness == "PROVISIONAL"
            from app.engines.rtg_wrapper import run_pooled
            units = {"RAD": [{
                "serial": "TOOL-TEST", "so": "TOOL-SO", "maxop": 0,
                "commit": date(2026, 9, 30), "program": "RAD",
            }]}
            result = run_pooled(
                units, ds.as_of(), profile=compiled.scheduler_profile,
                trace_constraints=True,
            )
            assert any(
                event["event_type"] == "OCCUPANCY_ACQUIRE"
                for event in result["TOOL-TEST"]["constraint_events"]
            )
            replay = await persist_replay_snapshot(
                db, base_snapshot_id=compiled.snapshot_id,
                units_by_program=units, results=result,
            )
            assert (await replay_snapshot(db, replay.id)).exact_match
        await engine.dispose()

    asyncio.run(scenario())
