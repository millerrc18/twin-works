"""RTG delivery slots + serial assignment.

A SLOT = a fixed RTG delivery target (program, hand, target_date). Each slot is filled by
a currently-assigned serial (default from the RTG plan; reassignable inline on a swap).
Elevator has LH + RH slot groups; radome one group; Aegis has no RTG plan (serial-anchored).
"""
import json
from datetime import date
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SlotAssignment

BASE = Path(__file__).resolve().parent.parent.parent
RTG_JSON = BASE / "rtg_targets.json"


def _hand(serial: str) -> str:
    s = serial.upper()
    if s.startswith("LH"):
        return "LH"
    if s.startswith("RH"):
        return "RH"
    return ""


def _rtg_plan():
    return json.load(open(RTG_JSON)) if RTG_JSON.exists() else {}


def default_slots(program: str, wip_serials: set):
    """Slots for the CURRENTLY-TRACKED units only (intersection of RTG plan + live WIP).
    One slot per assigned serial, keyed by serial so same-date same-hand units don't collide.
    Returns (slot_id, hand, target_date, default_serial), sorted by target then hand."""
    plan = _rtg_plan()
    slots = []
    for serial, t in plan.items():
        if t.get("program") != program or serial not in wip_serials:
            continue
        ship = t.get("ship")
        if not ship:
            continue
        hand = _hand(serial)
        # key by serial to guarantee uniqueness; the delivery target still drives ordering
        sid = f"{program}:{hand}:{serial}"
        slots.append((sid, hand, date.fromisoformat(ship), serial))
    slots.sort(key=lambda x: (x[2], x[1]))
    return slots


async def seed_slots(db: AsyncSession, program: str, wip_serials: set):
    """Insert any missing default slots (idempotent). Does not overwrite existing assignments."""
    existing = {r.slot_id for r in (await db.execute(
        select(SlotAssignment).where(SlotAssignment.program == program))).scalars()}
    for (sid, hand, tdate, serial) in default_slots(program, wip_serials):
        if sid not in existing:
            db.add(SlotAssignment(slot_id=sid, program=program, hand=hand,
                                  target_date=tdate, serial=serial))
    await db.commit()


async def get_slots(db: AsyncSession, program: str, wip_serials: set):
    """Return the program's slots (seeding first). List of SlotAssignment ORM rows,
    sorted by target then hand."""
    await seed_slots(db, program, wip_serials)
    rows = (await db.execute(
        select(SlotAssignment).where(SlotAssignment.program == program))).scalars().all()
    rows.sort(key=lambda r: (r.target_date or date.max, r.hand))
    return rows


async def reassign(db: AsyncSession, slot_id: str, serial: str | None):
    """Assign `serial` to `slot_id`. Atomic swap: if that serial already fills another slot,
    the two slots swap serials (the target slot's old serial moves to the serial's old slot),
    so every serial fills at most one slot and none is silently lost."""
    target = (await db.execute(
        select(SlotAssignment).where(SlotAssignment.slot_id == slot_id))).scalar_one_or_none()
    if not target:
        return None
    old_serial = target.serial
    if serial:
        prior = (await db.execute(
            select(SlotAssignment).where(SlotAssignment.program == target.program,
                                         SlotAssignment.serial == serial,
                                         SlotAssignment.slot_id != slot_id))).scalar_one_or_none()
        if prior:
            prior.serial = old_serial   # swap: displaced serial takes the vacated slot
    target.serial = serial or None
    await db.commit()
    return target


async def assigned_serials(db: AsyncSession, program: str) -> set:
    rows = await get_slots(db, program)
    return {r.serial for r in rows if r.serial}
