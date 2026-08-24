"""DataSource factory + LiveMcpDataSource (OAuth IFS MCP).

Live source queries IFS through the authenticated MCP client. SQL templates are module
strings so they're auditable/testable. Serial labels are NOT in IFS (verified) — the live
source pulls SO-side truth (positions, dates, closes) and overlays serial labels from the
snapshot/statusline mapping in wip_tables. Falls back to snapshot if not authenticated.
"""
from datetime import datetime, date
from app.data.source import DataSource, UnitRecord, ShippedRecord
from app.data.snapshot_source import SnapshotDataSource
from app.data import wip_tables as W
from app.engines.router_registry import registry

# program -> (project_id, part_no)
PROG_IFS = {
    "ELEV": ("531335", ("72P5520501-029P01", "72P5520502-029P01")),
    "RAD": ("C48178", ("3700ED0001-101",)),
    "AEGIS": ("530349", ("00999000563",)),
}

# --- auditable SQL templates ---
SQL_WIP = """
SELECT s.ORDER_NO AS SO, s.OBJSTATE AS STATE,
       TO_CHAR(s.REVISED_DUE_DATE,'YYYY-MM-DD') AS DUE,
       TO_CHAR(s.CLOSE_DATE,'YYYY-MM-DD') AS CLOSED
FROM SHOP_ORD_CFV s
WHERE s.PROJECT_ID = '{project}' AND s.PART_NO IN ({parts})
  AND s.CLOSE_DATE IS NULL
"""

SQL_POSITION = """
SELECT o.ORDER_NO AS SO,
       MAX(CASE WHEN o.OPER_STATUS_CODE_DB=90 THEN o.OPERATION_NO END) AS MAX_CLOSED
FROM SO_OPER_DISPATCH_LIST_CFV o
WHERE o.ORDER_NO IN ({sos})
GROUP BY o.ORDER_NO
"""

SQL_LASTCLK = """
SELECT c.ORDER_NO AS SO, TO_CHAR(MAX(c.FINISH_TIME),'YYYY-MM-DD') AS LAST_CLK
FROM GD_SHOP_FLOOR_CLOCKING c
WHERE c.ORDER_NO IN ({sos}) AND c.OPERATION_NO < 9000 AND c.FINISH_TIME IS NOT NULL
GROUP BY c.ORDER_NO
"""


def get_data_source(kind: str = "snapshot", tokens: dict | None = None) -> DataSource:
    if kind == "live" and tokens and tokens.get("access_token"):
        try:
            src = LiveMcpDataSource(tokens)
            if src.is_ready():
                return src
        except Exception:
            pass
    return SnapshotDataSource()


class LiveMcpDataSource(DataSource):
    """OAuth IFS-MCP-backed source. Serial labels overlaid from wip_tables (not in IFS)."""

    def __init__(self, tokens: dict):
        from app.data.ifs_mcp_client import IfsMcpClient
        self.client = IfsMcpClient(**tokens)
        self._as_of = datetime.now()
        self._cache = {}

    def is_ready(self) -> bool:
        return self.client.is_authenticated()

    def as_of(self) -> datetime:
        return self._as_of

    def _q(self, sql):
        res = self.client.execute_query(sql)
        # execute_query returns {data:[...]} or a JSON string; normalize to list of dicts
        if isinstance(res, dict):
            return res.get("data", [])
        return res or []

    def _serial_for(self, program, so):
        """Overlay serial from the wip_tables mapping (statusline/DPM truth)."""
        tbl = {"ELEV": W.ELEV, "RAD": W.RAD, "AEGIS": W.AEGIS}[program]
        for row in tbl:
            if row[1] == so:
                return row[0]
        return so  # fall back to SO if no known serial

    def get_wip_units(self, program: str) -> list[UnitRecord]:
        if program in self._cache:
            return self._cache[program]
        try:
            return self._live_wip(program)
        except Exception as e:
            # degrade gracefully: a live-query failure must not 500 the whole app
            print(f"[live_source] {program} live query failed ({e}); using snapshot")
            snap = SnapshotDataSource().get_wip_units(program)
            self._cache[program] = snap
            return snap

    def _live_wip(self, program: str) -> list[UnitRecord]:
        from app.services.program_service import ifs_meta
        proj, parts = ifs_meta().get(program, PROG_IFS.get(program))
        parts_in = ",".join(f"'{p}'" for p in parts)
        wip = self._q(SQL_WIP.format(project=proj, parts=parts_in))
        sos = [r["SO"] for r in wip]
        if not sos:
            self._cache[program] = []
            return []
        so_in = ",".join(f"'{s}'" for s in sos)
        pos = {r["SO"]: r["MAX_CLOSED"] for r in self._q(SQL_POSITION.format(sos=so_in))}
        clk = {r["SO"]: r["LAST_CLK"] for r in self._q(SQL_LASTCLK.format(sos=so_in))}
        out = []
        for r in wip:
            so = r["SO"]
            due = datetime.strptime(r["DUE"], "%Y-%m-%d").date() if r.get("DUE") else None
            lc = clk.get(so)
            stalled = bool(lc) and (self._as_of.date() - datetime.strptime(lc, "%Y-%m-%d").date()).days > 7
            out.append(UnitRecord(serial=self._serial_for(program, so), so=so,
                                  maxop=pos.get(so), commit=due, program=program,
                                  stalled=stalled))
        self._cache[program] = out
        return out

    def get_shipped_units(self, program: str) -> list[ShippedRecord]:
        # shipped/accuracy records stay from the curated snapshot set (pack dates + logged fx)
        return SnapshotDataSource().get_shipped_units(program)

    def get_close_date(self, so: str) -> date | None:
        return SnapshotDataSource().get_close_date(so)
