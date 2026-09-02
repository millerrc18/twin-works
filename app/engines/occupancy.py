"""Deterministic atomic reservations for finite tooling and station slots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


class ResourceAllocationDeadlock(RuntimeError):
    """An occupancy request can never be satisfied by the configured resources."""


class InvalidOccupancyRelease(RuntimeError):
    """A release request does not match an active lease."""


@dataclass(frozen=True, order=True)
class OccupancyRequest:
    pool_code: str
    quantity: int = 1
    instance_code: str | None = None
    min_hold_hours: float = 0.0
    lag_hours: float = 0.0


@dataclass(frozen=True, order=True)
class OccupancyLease:
    pool_code: str
    instance_code: str
    unit_key: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class OccupancyReservation:
    unit_key: str
    requested_start: datetime
    start: datetime
    end: datetime
    leases: tuple[OccupancyLease, ...]

    @property
    def wait_hours(self) -> float:
        return (self.start - self.requested_start).total_seconds() / 3600.0


@dataclass(frozen=True, order=True)
class ActiveOccupancyLease:
    pool_code: str
    instance_code: str
    unit_key: str
    acquired_at: datetime
    min_release_at: datetime
    lag_hours: float


@dataclass(frozen=True, order=True)
class OccupancyEvent:
    event_type: str
    pool_code: str
    instance_code: str
    unit_key: str
    occurred_at: datetime
    effective_at: datetime


def occupancy_queue_key(unit: dict, ready_time: datetime,
                        as_of_date: date, dpas_programs: set[str],
                        pool_code: str) -> tuple:
    """Stable acquisition order independent of DB and input-list ordering."""
    commit = unit.get("commit") or date(2099, 1, 1)
    behind = bool(unit.get("commit") and unit["commit"] < as_of_date)
    dpas_behind = unit.get("program") in dpas_programs and behind
    return (
        ready_time,
        0 if dpas_behind else 1,
        commit,
        unit.get("program", ""),
        unit.get("serial", ""),
        pool_code,
    )


class OccupancyAllocator:
    """Reserve known-duration intervals across one or more pools atomically."""

    def __init__(self, capacities: dict[str, int], *,
                 instances: dict[str, list[str]] | None = None,
                 as_of: datetime):
        self._slots: dict[str, dict[str, datetime]] = {}
        self._active: dict[tuple[str, str], ActiveOccupancyLease] = {}
        self._history: list[OccupancyEvent] = []
        self._unavailable: dict[
            str, dict[str, list[tuple[datetime, datetime, str]]]
        ] = {}
        instances = instances or {}
        for pool_code, raw_capacity in sorted(capacities.items()):
            capacity = int(raw_capacity)
            if capacity < 1:
                raise ResourceAllocationDeadlock(
                    f"Occupancy pool {pool_code} has no usable slots")
            named = list(instances.get(pool_code, ()))
            if named and len(named) != capacity:
                raise ResourceAllocationDeadlock(
                    f"Occupancy pool {pool_code} has {capacity} slots but "
                    f"{len(named)} named instances")
            if len(set(named)) != len(named):
                raise ResourceAllocationDeadlock(
                    f"Occupancy pool {pool_code} has duplicate instance codes")
            codes = named or [f"{pool_code}#{index}" for index in range(1, capacity + 1)]
            self._slots[pool_code] = {code: as_of for code in sorted(codes)}
            self._unavailable[pool_code] = {code: [] for code in sorted(codes)}

    def availability(self) -> dict[str, tuple[tuple[str, datetime], ...]]:
        return {
            pool: tuple(sorted(slots.items()))
            for pool, slots in sorted(self._slots.items())
        }

    def reserve_fixed(self, unit_key: str, requests: list[OccupancyRequest],
                      requested_start: datetime,
                      duration_hours: float) -> OccupancyReservation:
        if duration_hours < 0:
            raise ResourceAllocationDeadlock("Occupancy duration cannot be negative")
        plan = self._plan(requests)
        start = requested_start
        selected = {}
        for _iteration in range(1000):
            selected, next_start = self._select_for_interval(
                plan, start, float(duration_hours))
            if next_start == start:
                break
            start = next_start
        else:
            raise ResourceAllocationDeadlock(
                f"Occupancy request for {unit_key} made no scheduling progress")

        leases = []
        for pool_code, item in plan.items():
            hold_hours = max(float(duration_hours), item["min_hold_hours"])
            end = start + timedelta(hours=hold_hours + item["lag_hours"])
            for instance_code in selected[pool_code]:
                leases.append(OccupancyLease(
                    pool_code=pool_code, instance_code=instance_code,
                    unit_key=unit_key, start=start, end=end,
                ))
        # Mutate only after every pool and instance has a valid atomic plan.
        for lease in leases:
            self._slots[lease.pool_code][lease.instance_code] = lease.end
            self._history.append(OccupancyEvent(
                event_type="RESERVE", pool_code=lease.pool_code,
                instance_code=lease.instance_code, unit_key=lease.unit_key,
                occurred_at=lease.start, effective_at=lease.end,
            ))
        leases = tuple(sorted(leases))
        return OccupancyReservation(
            unit_key=unit_key, requested_start=requested_start,
            start=start, end=max((lease.end for lease in leases), default=start),
            leases=leases,
        )

    def acquire_atomic(self, unit_key: str, requests: list[OccupancyRequest],
                       at: datetime) -> tuple[ActiveOccupancyLease, ...] | None:
        """Acquire every requested slot now or acquire none."""
        plan = self._plan(requests)
        selected: dict[str, list[str]] = {}
        for pool_code, item in plan.items():
            slots = self._slots[pool_code]
            chosen = list(item["specific"])
            hold_hours = item["min_hold_hours"]
            if any(self._next_gap(pool_code, code, at, hold_hours) != at
                   or (pool_code, code) in self._active
                   for code in chosen):
                return None
            remaining = [
                code for code, available in sorted(
                    slots.items(), key=lambda row: (row[1], row[0]))
                if code not in chosen
                and available <= at
                and self._next_gap(pool_code, code, at, hold_hours) == at
                and (pool_code, code) not in self._active
            ]
            if len(remaining) < item["fungible_quantity"]:
                return None
            chosen.extend(remaining[:item["fungible_quantity"]])
            selected[pool_code] = chosen

        leases = []
        for pool_code, item in plan.items():
            for instance_code in selected[pool_code]:
                lease = ActiveOccupancyLease(
                    pool_code=pool_code,
                    instance_code=instance_code,
                    unit_key=unit_key,
                    acquired_at=at,
                    min_release_at=at + timedelta(hours=item["min_hold_hours"]),
                    lag_hours=item["lag_hours"],
                )
                leases.append(lease)
        for lease in leases:
            self._active[(lease.pool_code, lease.instance_code)] = lease
            self._slots[lease.pool_code][lease.instance_code] = datetime.max
            self._history.append(OccupancyEvent(
                event_type="ACQUIRE", pool_code=lease.pool_code,
                instance_code=lease.instance_code, unit_key=lease.unit_key,
                occurred_at=lease.acquired_at, effective_at=lease.min_release_at,
            ))
        return tuple(sorted(leases))

    def next_available_at(self, requests: list[OccupancyRequest],
                          at: datetime) -> datetime:
        """Earliest instant all requested slots could be acquired, without mutation."""
        plan = self._plan(requests)
        _selected, candidate = self._select_for_interval(plan, at, 0.0)
        return candidate

    def add_unavailability(self, pool_code: str, start: datetime, end: datetime,
                           *, reason: str,
                           instance_code: str | None = None) -> None:
        """Add a reviewed future maintenance/unavailable interval before scheduling starts."""
        if self._history or self._active:
            raise ResourceAllocationDeadlock(
                "Maintenance intervals must be loaded before reservations or leases")
        if pool_code not in self._slots:
            raise ResourceAllocationDeadlock(
                f"Maintenance references unknown pool {pool_code}")
        if end <= start or not (reason or "").strip():
            raise ResourceAllocationDeadlock(
                "Maintenance requires a positive interval and reason")
        targets = ([instance_code] if instance_code else sorted(self._slots[pool_code]))
        for code in targets:
            if code not in self._slots[pool_code]:
                raise ResourceAllocationDeadlock(
                    f"Maintenance references unknown instance {code} in pool {pool_code}")
        for code in targets:
            self._unavailable[pool_code][code].append((start, end, reason.strip()))
            self._unavailable[pool_code][code].sort()

    def release(self, unit_key: str, pool_code: str, at: datetime,
                *, instance_code: str | None = None) -> datetime:
        """Release matching active leases and return their effective availability time."""
        matches = [
            lease for lease in self._active.values()
            if lease.unit_key == unit_key and lease.pool_code == pool_code
            and (instance_code is None or lease.instance_code == instance_code)
        ]
        if not matches:
            target = f"/{instance_code}" if instance_code else ""
            raise InvalidOccupancyRelease(
                f"Unit {unit_key} has no active lease for {pool_code}{target}")
        effective = max(
            max(at, lease.min_release_at) + timedelta(hours=lease.lag_hours)
            for lease in matches
        )
        for lease in matches:
            conflicts = [
                (start, end, reason)
                for start, end, reason in self._unavailable[lease.pool_code][lease.instance_code]
                if lease.acquired_at < end and effective > start
            ]
            if conflicts:
                raise ResourceAllocationDeadlock(
                    f"Lease {lease.pool_code}/{lease.instance_code} for {unit_key} "
                    "overlaps an unavailable interval")
        for lease in matches:
            self._active.pop((lease.pool_code, lease.instance_code))
            self._slots[lease.pool_code][lease.instance_code] = effective
            self._history.append(OccupancyEvent(
                event_type="RELEASE", pool_code=lease.pool_code,
                instance_code=lease.instance_code, unit_key=lease.unit_key,
                occurred_at=at, effective_at=effective,
            ))
        return effective

    def active_leases(self, unit_key: str | None = None) -> tuple[ActiveOccupancyLease, ...]:
        rows = self._active.values()
        if unit_key is not None:
            rows = [lease for lease in rows if lease.unit_key == unit_key]
        return tuple(sorted(rows))

    def history(self) -> tuple[OccupancyEvent, ...]:
        return tuple(self._history)

    def unavailable_intervals(self) -> dict:
        return {
            pool: {
                code: tuple(rows) for code, rows in sorted(instances.items())
            }
            for pool, instances in sorted(self._unavailable.items())
        }

    def _next_gap(self, pool_code: str, instance_code: str,
                  requested_start: datetime, duration_hours: float) -> datetime:
        candidate = max(requested_start, self._slots[pool_code][instance_code])
        if candidate == datetime.max:
            return candidate
        duration = timedelta(hours=max(0.0, duration_hours))
        for start, end, _reason in self._unavailable[pool_code][instance_code]:
            if duration == timedelta(0) and start <= candidate < end:
                candidate = end
                continue
            if candidate + duration <= start:
                break
            if candidate < end and candidate + duration > start:
                candidate = end
        return candidate

    def _select_for_interval(self, plan: dict[str, dict], start: datetime,
                             duration_hours: float) -> tuple[dict[str, list[str]], datetime]:
        selected = {}
        candidate = start
        for pool_code, item in plan.items():
            hold_hours = max(float(duration_hours), item["min_hold_hours"]) + item["lag_hours"]
            specific = list(item["specific"])
            ready = [
                (self._next_gap(pool_code, code, start, hold_hours), code)
                for code in self._slots[pool_code]
                if code not in specific
            ]
            ready.sort()
            chosen = specific + [
                code for _available, code in ready[:item["fungible_quantity"]]
            ]
            selected[pool_code] = chosen
            candidate = max(candidate, *(
                self._next_gap(pool_code, code, start, hold_hours) for code in chosen
            ))
        return selected, candidate

    def _plan(self, requests: list[OccupancyRequest]) -> dict[str, dict]:
        if not requests:
            return {}
        plan: dict[str, dict] = {}
        for request in sorted(requests):
            pool_code = request.pool_code
            if pool_code not in self._slots:
                raise ResourceAllocationDeadlock(
                    f"Occupancy request references unknown pool {pool_code}")
            if request.quantity < 1:
                raise ResourceAllocationDeadlock(
                    f"Occupancy request for {pool_code} must have positive quantity")
            if request.instance_code and request.quantity != 1:
                raise ResourceAllocationDeadlock(
                    f"Named-instance request for {pool_code} must have quantity 1")
            item = plan.setdefault(pool_code, {
                "specific": [], "fungible_quantity": 0,
                "min_hold_hours": 0.0, "lag_hours": 0.0,
            })
            if request.instance_code:
                if request.instance_code not in self._slots[pool_code]:
                    raise ResourceAllocationDeadlock(
                        f"Unknown instance {request.instance_code} in pool {pool_code}")
                if request.instance_code in item["specific"]:
                    raise ResourceAllocationDeadlock(
                        f"Duplicate request for instance {request.instance_code}")
                item["specific"].append(request.instance_code)
            else:
                item["fungible_quantity"] += int(request.quantity)
            item["min_hold_hours"] = max(
                item["min_hold_hours"], float(request.min_hold_hours))
            item["lag_hours"] = max(item["lag_hours"], float(request.lag_hours))

        for pool_code, item in plan.items():
            required = len(item["specific"]) + item["fungible_quantity"]
            capacity = len(self._slots[pool_code])
            if required > capacity:
                raise ResourceAllocationDeadlock(
                    f"Occupancy pool {pool_code} requires {required} slots but has {capacity}")
            item["specific"] = tuple(sorted(item["specific"]))
        return dict(sorted(plan.items()))
