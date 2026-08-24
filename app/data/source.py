"""DataSource interface — swappable IFS access. SnapshotDataSource (offline JSON/tables)
now; LiveMcpDataSource (OAuth IFS MCP) is a drop-in at P5. The rest of the app depends
only on this ABC.
"""
from abc import ABC, abstractmethod
from datetime import datetime, date
from dataclasses import dataclass


@dataclass
class UnitRecord:
    serial: str
    so: str
    maxop: int | None
    commit: date | None
    program: str
    stalled: bool = False

    def as_sim_unit(self) -> dict:
        return dict(serial=self.serial, so=self.so, maxop=self.maxop,
                    commit=self.commit, program=self.program)


@dataclass
class ShippedRecord:
    serial: str
    so: str
    program: str
    commit: date | None
    close: date
    pack: date
    logged_forecast: date | None


class DataSource(ABC):
    @abstractmethod
    def get_wip_units(self, program: str) -> list[UnitRecord]: ...

    @abstractmethod
    def get_shipped_units(self, program: str) -> list[ShippedRecord]: ...

    @abstractmethod
    def get_close_date(self, so: str) -> date | None: ...

    @abstractmethod
    def as_of(self) -> datetime: ...
