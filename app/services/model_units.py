"""What units are in the model — backtest (retrospective) vs forward (real scored ships).

Backtest cohort: the distinct genuine-production closes in accuracy_results.json (the empirical
bias seed). Forward cohort: ForecastLog rows that have been backfilled with actual_close (real
prospective ships scored once per serial at earliest logged forecast). Powers an admin panel so
the PM can see exactly which SN/SO are feeding each track.
"""
import json
import sqlite3
from pathlib import Path
from app.config import settings
from app.data import wip_tables as W

BASE = Path(__file__).resolve().parent.parent.parent
ACCURACY_JSON = BASE / "accuracy_results.json"


def _db_path() -> str:
    url = settings.database_url
    return url.split(":///", 1)[1] if ":///" in url else url


def _clean_serial(sn: str | None, so: str) -> str:
    """Guard against SO-fragment placeholders. Real elevator SNs are 'LH nnn'/'RH nnn' (3-digit);
    some shipped-baseline rows carry 4-digit SO fragments (e.g. 'RH 3479') that are NOT real head
    serials. Never fabricate — show '(SO …)' until a correct SN is provided."""
    if not sn:
        return f"(SO {so})"
    parts = sn.split()
    # LH/RH prefix with a 4+ digit number = SO fragment, not a true 3-digit head serial
    if len(parts) == 2 and parts[0] in ("LH", "RH") and parts[1].isdigit() and len(parts[1]) >= 4:
        return f"{parts[0]} (SO {so})"
    return sn


def _serial_for_so(so: str, fallback: str | None = None) -> str:
    """Resolve the DPM-verified serial for an SO from the wip_tables maps (SHIPPED + WIP).
    The backtest labels in accuracy_results.json are hand-typed and sometimes wrong (e.g.
    'RAD 3337' is really SN 516); the SO->SN map is the source of truth. Placeholder SO-fragment
    serials are surfaced as '(SO …)' rather than shown as a real serial."""
    for prog in ("ELEV", "RAD", "AEGIS"):
        for row in W.SHIPPED.get(prog, []):
            if row[1] == so:
                return _clean_serial(row[0], so)
        for row in {"ELEV": W.ELEV, "RAD": W.RAD, "AEGIS": W.AEGIS}[prog]:
            if row[1] == so:
                return _clean_serial(row[0], so)
    return _clean_serial(fallback, so)


def backtest_units() -> list[dict]:
    """Distinct backtest units: {program, serial, so, error_days}. Uses the pack-error at the
    smallest horizon available per SO (closest-in call). Empty if no backtest file."""
    if not ACCURACY_JSON.exists():
        return []
    try:
        data = json.load(open(ACCURACY_JSON))
    except Exception:
        return []
    best = {}  # so -> row with smallest horizon
    for u in data.get("units", []):
        if u.get("excluded"):
            continue
        so = u.get("so")
        h = u.get("horizon", 99)
        if so not in best or h < best[so].get("horizon", 99):
            best[so] = u
    out = []
    for so, u in best.items():
        out.append(dict(program=u.get("program"),
                        serial=_serial_for_so(so, u.get("unit")), so=so,
                        error_days=u.get("err_vs_pack")))
    out.sort(key=lambda r: (r["program"] or "", r["serial"] or ""))
    return out


def forward_units() -> list[dict]:
    """Eligible maturity cohort: one earliest pre-pack forecast per program/shop order."""
    path = _db_path()
    if not Path(path).exists():
        return []
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT f.program, f.serial, f.so, f.build_date, f.p50_date,
                   p.pack AS actual_pack
            FROM forecast_log f
            JOIN position_state p ON p.program = f.program AND p.so = f.so
            WHERE p.pack IS NOT NULL AND p.source = 'ifs-sync'
              AND f.p50_date IS NOT NULL
              AND date(f.build_date) < date(p.pack)
            ORDER BY f.program, f.so, f.build_date, f.id
        """).fetchall()
        con.close()
    except sqlite3.OperationalError:
        return []
    earliest = {}
    for row in rows:
        key = (row["program"], row["so"])
        if key not in earliest:
            pack = __import__("datetime").date.fromisoformat(row["actual_pack"])
            p50 = __import__("datetime").date.fromisoformat(row["p50_date"])
            earliest[key] = {
                "program": row["program"], "serial": row["serial"], "so": row["so"],
                "close": row["actual_pack"], "error_days": (p50 - pack).days,
                "build_date": row["build_date"],
            }
    out = list(earliest.values())
    out.sort(key=lambda row: (row["program"] or "", row["serial"] or ""))
    return out
