"""Offline DataSource. Reads the mutable PositionState table when it's populated (materialized
baseline + IFS syncs); otherwise falls back to the wip_tables module baseline so a fresh DB
still boots. This is a synchronous hot path (matrix/forecast render), so PositionState is read
via position_state.load_state() (stdlib sqlite3, mtime-cached)."""
from datetime import datetime, date
from app.data import wip_tables as W
from app.data.source import DataSource, UnitRecord, ShippedRecord
from app.services import position_state as PS

STALL_DAYS = 7


class SnapshotDataSource(DataSource):
    def __init__(self, use_position_state: bool = True):
        self._state = PS.load_state() if use_position_state else {}

    # --- as-of clock ---
    def as_of(self) -> datetime:
        if not self._state:
            return W.AS_OF
        # data reflects the latest sync: use the most recent last_clock/closed seen, else today
        dates = [v["last_clock"] for v in self._state.values() if v.get("last_clock")]
        dates += [v["closed"] for v in self._state.values() if v.get("closed")]
        if not dates:
            return W.AS_OF
        latest = max(dates)
        # as-of is at least the latest clock; never earlier than the bootstrap as-of
        anchor = max(latest, W.AS_OF.date())
        return datetime(anchor.year, anchor.month, anchor.day, 12, 0)

    def _stalled(self, last_clock: date | None) -> bool:
        if last_clock is None:
            return False
        return (self.as_of().date() - last_clock).days > STALL_DAYS

    # --- WIP (open units) ---
    def get_wip_units(self, program: str) -> list[UnitRecord]:
        if self._state:
            out = []
            for so, v in self._state.items():
                if v["program"] != program or v["closed"] is not None:
                    continue
                out.append(UnitRecord(serial=v["serial"], so=so, maxop=v["maxop"],
                                      commit=v["due"], program=program,
                                      stalled=self._stalled(v["last_clock"])))
            return out
        # baseline fallback
        out = []
        if program not in {"ELEV", "RAD", "AEGIS"}:
            return []
        for u in W.units_for(program):
            out.append(UnitRecord(serial=u["serial"], so=u["so"], maxop=u["maxop"],
                                  commit=u["commit"], program=program,
                                  stalled=W.is_stalled(u["so"])))
        return out

    # --- shipped (closed units) ---
    def get_shipped_units(self, program: str) -> list[ShippedRecord]:
        if self._state:
            out = []
            for so, v in self._state.items():
                if v["program"] != program or v["closed"] is None:
                    continue
                out.append(ShippedRecord(serial=v["serial"], so=so, program=program,
                                         commit=v["due"], close=v["closed"],
                                         pack=v["pack"] or v["closed"], logged_forecast=None))
            return out
        out = []
        for (serial, so, commit, close, pack, fx) in W.SHIPPED.get(program, []):
            out.append(ShippedRecord(serial=serial, so=so, program=program, commit=commit,
                                     close=close, pack=pack, logged_forecast=fx))
        return out

    def get_close_date(self, so: str) -> date | None:
        if self._state:
            v = self._state.get(so)
            return v["closed"] if v else None
        for prog in ("ELEV", "RAD", "AEGIS"):
            for (serial, s, commit, close, pack, fx) in W.SHIPPED.get(prog, []):
                if s == so:
                    return close
        return None
