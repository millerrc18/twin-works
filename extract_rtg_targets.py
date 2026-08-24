"""Extract per-milestone RTG target dates from the GAC RTG workbook -> rtg_targets.json.

Elevator RTG tab: col B=serial, cols D/E/F/G = Assy Jig / Assembly 1 / Assembly 2 / Finish-Ship.
Aeronose RTG tab: col B=serial, cols D/E/F/G = Lamination / Assembly / Paint / Ship.
Milestone codes map to the app's registry: ELEV AJ/A1/A2/FS, RAD LAM/ASSY/PAINT/SHIP.
Aegis has no RTG plan (omitted -> app falls back to contract).
"""
import json
from datetime import date
import openpyxl

SRC = r"C:\Users\ryan.c.miller\Downloads\Copy of GAC RTG 2026.xlsx"
OUT = r"C:\Users\ryan.c.miller\Downloads\rtg-tracker-build\rtg_targets.json"

# (sheet, program, milestone codes for cols D,E,F,G)
TABS = [
    ("Elevator RTG", "ELEV", ["AJ", "A1", "A2", "FS"]),
    ("Aeronose RTG", "RAD", ["LAM", "ASSY", "PAINT", "SHIP"]),
]


def _iso(v):
    if v is None:
        return None
    if hasattr(v, "date"):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return None


def _serial(program, raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if program == "RAD":
        # radome serials are numeric in the sheet (513, 508, 430...) -> keep as string
        try:
            return str(int(float(s)))
        except ValueError:
            return s
    return s  # elevator already "LH 232" etc.


wb = openpyxl.load_workbook(SRC, data_only=True)
targets = {}
for sheet, program, ms_codes in TABS:
    ws = wb[sheet]
    for row in ws.iter_rows(min_row=3, values_only=True):
        serial = _serial(program, row[1] if len(row) > 1 else None)  # col B
        if not serial:
            continue
        ms = {}
        for i, code in enumerate(ms_codes):     # cols D,E,F,G = index 3,4,5,6
            d = _iso(row[3 + i]) if len(row) > 3 + i else None
            if d:
                ms[code] = d
        ship = _iso(row[6]) if len(row) > 6 else None  # col G = ship
        if ms or ship:
            targets[serial] = dict(program=program, milestones=ms, ship=ship)

json.dump(targets, open(OUT, "w"), indent=2)
print(f"wrote {len(targets)} RTG target rows -> {OUT}")
for k in list(targets)[:4]:
    print(" ", k, targets[k])
