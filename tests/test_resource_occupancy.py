"""Deterministic atomic occupancy lease behavior."""
from datetime import date, datetime

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
