"""WIP data tables + position/stall helpers — extracted from build_tracker.py so the
app can import them without triggering the Excel-builder's module-level side effects.

Snapshot as-of 2026-08-19 (bootstrap data). The live IFS data source (P5) replaces
these; treat them as the offline snapshot only.
"""
from datetime import datetime as DT, date

AS_OF = DT(2026, 8, 19, 12, 0)


def d(m, dd):
    return date(2026, m, dd)


def dt_(y, m, dd):
    return date(y, m, dd)


# ELEVATOR WIP: (serial, SO, maxop, AJ, A1, A2, FS-ship)
ELEV = [
    ("LH 232", "1455596", 4000, None, d(8, 18), None, d(8, 21)),
    ("LH 233", "1456550", 3400, None, None, d(8, 21), d(8, 28)),
    ("LH 229", "1452748", 3400, None, None, d(8, 28), d(9, 4)),
    ("LH 234", "1457061", 2300, None, d(8, 18), d(9, 4), d(9, 11)),
    ("LH 235", "1458317", 1950, None, d(8, 25), d(9, 11), d(9, 18)),
    ("LH 236", "1459236", 1940, None, d(9, 1), d(9, 18), d(9, 25)),
    ("LH 237", "1460167", 1920, None, d(9, 8), d(9, 25), d(10, 2)),
    ("LH 238", "1460758", 1000, d(8, 29), d(9, 15), d(10, 2), d(10, 9)),
    ("LH 239", "1461523", None, d(9, 5), d(9, 22), d(10, 9), d(10, 16)),
    ("RH 227", "1452749", 3700, None, None, d(8, 14), d(8, 21)),
    ("RH 231", "1456551", 3400, None, None, d(8, 21), d(8, 28)),
    ("RH 232", "1457063", 3030, None, None, d(8, 28), d(9, 4)),
    ("RH 233", "1458318", 2050, None, d(8, 18), d(9, 4), d(9, 11)),
    ("RH 235", "1460168", 1700, None, d(8, 25), d(9, 11), d(9, 18)),
    ("RH 234", "1459237", 1550, None, d(8, 22), d(9, 25), d(9, 25)),
    ("RH 236", "1460759", 1450, None, d(9, 1), d(9, 18), d(9, 25)),
    ("RH 237", "1461524", 500, None, d(9, 8), d(9, 25), d(10, 2)),
]

# RADOME WIP: (serial, SO, maxop, ship=IFS REVISED_DUE_DATE)
# CORRECTED 2026-08-21 from DPM/statusline: prior SN<->SO mapping was substantially wrong.
# Verified against IFS SHOP_ORD_CFV (state/due) + OPER_STATUS_CODE_DB (position).
# 1453338 & 1454081 closed 8/21 -> moved to SHIPPED. Parked units flagged (deep-idle).
RAD = [
    # serial, SO,        maxop, IFS due
    ("508", "1449908", 785, d(9, 3)),
    ("518", "1456255", 620, d(8, 12)),
    ("514", "1453339", 770, d(8, 27)),
    ("511", "1451436", 745, d(9, 3)),
    ("517", "1454080", 680, d(9, 3)),
    ("519", "1458360", 635, d(9, 10)),
    ("520", "1459009", 530, d(9, 10)),
    ("430", "1401814", 695, d(10, 1)),
    ("521", "1460451", 570, d(9, 17)),
    ("522", "1460931", 410, d(9, 17)),
    ("523", "1460932", 570, d(9, 24)),
    # Parked / deep-idle (flagged STALLED by last-clock rule):
    ("509", "1451434", 775, d(7, 2)),
    ("516", "1454082", 625, d(8, 4)),
    ("361", "1360294", 9998, d(10, 29)),
    ("355", "1357521", 650, date(2025, 12, 19)),
    ("358", "1357524", 9998, date(2025, 12, 19)),
    ("397", "1379197", 9998, date(2025, 12, 19)),
    ("460", "1414098", 570, date(2025, 8, 20)),
]

# AEGIS reflector (530349): (serial, SO, maxop, contract-due)
AEGIS = [
    ("176", "1442037", 240, d(5, 14)),
    ("178", "1450617", 170, d(7, 14)),
    ("180", "1455178", 240, d(9, 14)),
    ("181", "1457856", 160, d(11, 12)),
    ("182", "1460448", 155, d(12, 14)),
]

# SHIPPED (retained as hidden accuracy records): serial, SO, commit, close, pack, logged_forecast
SHIPPED = {
    # SN/hand corrected 2026-08-24 from IFS SHOP_ORD_CFV.NOTE_TEXT ('S/N nnn') + PART_NO
    # (501=LH, 502=RH). Prior 4-digit values (RH 3479, LH 1270...) were SO fragments AND the
    # hands were wrong. IFS note is the source of truth (no serial column exists).
    "ELEV": [
        ("LH 230", "1453479", d(6, 26), dt_(2026, 8, 13), dt_(2026, 8, 13), dt_(2026, 8, 7)),
        ("LH 231", "1453860", d(7, 10), dt_(2026, 8, 14), dt_(2026, 8, 14), dt_(2026, 8, 11)),
        ("RH 230", "1455597", d(7, 17), dt_(2026, 8, 15), dt_(2026, 8, 15), dt_(2026, 8, 13)),
        ("RH 228", "1453480", d(6, 26), dt_(2026, 8, 6), dt_(2026, 8, 6), dt_(2026, 8, 3)),
        ("LH 228", "1451269", d(6, 12), dt_(2026, 8, 6), dt_(2026, 8, 1), dt_(2026, 7, 30)),
        ("RH 226", "1451270", d(6, 12), dt_(2026, 8, 3), dt_(2026, 8, 3), dt_(2026, 7, 28)),
    ],
    "RAD": [
        ("518", "1451435", d(7, 6), dt_(2026, 7, 31), dt_(2026, 7, 31), dt_(2026, 7, 27)),
        ("516", "1453337", d(7, 15), dt_(2026, 8, 10), dt_(2026, 8, 7), dt_(2026, 8, 3)),
    ],
    "AEGIS": [],
}

# Status-based position (OPER_STATUS_CODE_DB=90 MAX_CLOSED) — authoritative over table maxop.
STATUS_MAXCLOSED = {
    "1455596": 3850, "1456550": 3300, "1452748": 3300, "1457061": 2210, "1458317": 1950,
    "1459236": 1930, "1460167": 1930, "1460758": 1200, "1461523": None,
    "1452749": 3750, "1456551": 3400, "1457063": 3030, "1458318": 2110, "1460168": 1910,
    "1459237": 1550, "1460759": 1300, "1461524": 500,
    # radome (refreshed 2026-08-21 from OPER_STATUS_CODE_DB=90)
    "1449908": 785, "1456255": 620, "1453339": 770, "1451436": 745, "1454080": 680,
    "1458360": 635, "1459009": 530, "1401814": 695, "1460451": 570, "1460931": 410,
    "1460932": 570, "1451434": 775, "1454082": 625, "1360294": 9998,
    "1357521": 650, "1357524": 9998, "1379197": 9998, "1414098": 570,
    "1442037": 240, "1450617": 170, "1455178": 240, "1457856": 160, "1460448": 155,
}

# last-clock per SO; idle >7d before AS_OF = STALLED
LAST_CLOCK = {
    # radome (refreshed 2026-08-21)
    "1449908": d(8, 21), "1456255": d(8, 17), "1453339": d(8, 21), "1451436": d(8, 21),
    "1454080": d(8, 21), "1458360": d(8, 20), "1459009": d(8, 6), "1401814": d(7, 14),
    "1460451": d(8, 21), "1460931": d(8, 21), "1460932": d(8, 21),
    "1451434": d(7, 29), "1454082": d(7, 30), "1360294": dt_(2024, 2, 20),
    "1357521": dt_(2024, 10, 3), "1357524": dt_(2024, 2, 19), "1379197": dt_(2024, 8, 29),
    "1414098": dt_(2025, 5, 28),
    "1452748": d(8, 17), "1455596": d(8, 19), "1456550": d(8, 18), "1457061": d(8, 17),
    "1458317": d(8, 17), "1459236": d(8, 17), "1460167": d(8, 19), "1460758": d(8, 19),
    "1452749": d(8, 19), "1456551": d(8, 19), "1457063": d(8, 19), "1458318": d(8, 19),
    "1460168": d(8, 19), "1459237": d(8, 17), "1460759": d(8, 17), "1461524": d(8, 19),
    "1442037": d(8, 5), "1450617": d(7, 30), "1455178": d(8, 18), "1457856": d(8, 19),
    "1460448": d(8, 16),
}

PROGRAM_META = {
    "ELEV": {"name": "G500 Elevator", "project": "531335", "target_per_wk": 1.4},
    "RAD": {"name": "Aeronose Radome", "project": "C48178", "target_per_wk": 1.4},
    "AEGIS": {"name": "Aegis Reflector", "project": "530349", "target_per_wk": 1.4},
}


def true_maxop(so, fallback):
    """Status-based MAX_CLOSED op (authoritative), else the table fallback."""
    return STATUS_MAXCLOSED.get(so, fallback)


def is_stalled(so, as_of=None):
    as_of = as_of or AS_OF
    lc = LAST_CLOCK.get(so)
    return lc is not None and (as_of.date() - lc).days > 7


def units_for(program):
    """Normalize each program's table into sim-ready dicts:
       {serial, so, maxop, commit, program}. commit = FS/ship/contract date (last col)."""
    tbl = {"ELEV": ELEV, "RAD": RAD, "AEGIS": AEGIS}[program]
    out = []
    for row in tbl:
        serial, so, maxop = row[0], row[1], row[2]
        commit = row[-1]
        out.append(dict(serial=serial, so=so, maxop=true_maxop(so, maxop),
                        commit=commit, program=program))
    return out
