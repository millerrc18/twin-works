"""Canonical IFS shop-order to head-serial resolution."""
from __future__ import annotations

import re

from app.data import wip_tables as W


_SERIAL_PATTERN = re.compile(
    r"\bS\s*/?\s*N(?:O)?\.?\s*[:#-]?\s*([0-9]+)\b",
    re.IGNORECASE,
)


def serial_from_note(program: str, part_no: str | None, note_text: str | None) -> str | None:
    """Parse the head serial stored in SHOP_ORD_CFV.NOTE_TEXT."""
    match = _SERIAL_PATTERN.search(note_text or "")
    if not match:
        return None
    number = match.group(1).lstrip("0") or "0"
    if program.upper() != "ELEV":
        return number
    part_no = part_no or ""
    hand = "LH" if "501" in part_no else "RH" if "502" in part_no else ""
    return f"{hand} {number}".strip()


def serials_from_note_rows(program: str, rows) -> dict[str, str]:
    """Build a deterministic SO-to-serial map from IFS query rows."""
    resolved = {}
    for row in rows:
        serial = serial_from_note(program, row.get("PART_NO"), row.get("NOTE_TEXT"))
        if serial:
            resolved[str(row["SO"])] = serial
    return resolved


def baseline_serial(program: str, so: str) -> str | None:
    """Return the curated bootstrap serial for an SO, if the SO predates live NOTE_TEXT sync."""
    tables = {"ELEV": W.ELEV, "RAD": W.RAD, "AEGIS": W.AEGIS}
    for row in tables.get(program.upper(), ()):
        if str(row[1]) == str(so):
            return row[0]
    return None
