"""RTG plan target dates (elevator + radome). Aegis has no RTG plan.
Loaded from rtg_targets.json (produced by extract_rtg_targets.py from the GAC RTG workbook)."""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
RTG_JSON = BASE / "rtg_targets.json"

_targets = {}
if RTG_JSON.exists():
    try:
        _targets = json.load(open(RTG_JSON))
    except Exception:
        _targets = {}


def _pdate(s):
    return date.fromisoformat(s) if s else None


def rtg_ship(serial: str):
    """RTG ship target date for a serial, or None if no RTG plan (e.g. Aegis)."""
    t = _targets.get(serial)
    return _pdate(t["ship"]) if t and t.get("ship") else None


def rtg_milestone(serial: str, ms_code: str):
    t = _targets.get(serial)
    if not t:
        return None
    return _pdate(t.get("milestones", {}).get(ms_code))


def has_rtg(serial: str) -> bool:
    return serial in _targets
