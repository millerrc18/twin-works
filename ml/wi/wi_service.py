"""WI ingestion orchestration: extract -> validate -> persist to wi_constraint table.

Cached extractions live in wis/extractions/<PROGRAM>_<part>.json (produced by an
assistant MCP run). Program -> WI file(s) mapping below. Complexity features are exposed
to the ML feature builder (P3).
"""
import json
from pathlib import Path
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import WIConstraint
from ml.wi.extractor import CachedWIExtractor
from ml.wi.validator import validate

EXTRACTIONS_DIR = settings.wis_dir / "extractions"

# program -> list of (cache_json, source_docx)
PROGRAM_WIS = {
    "RAD": [
        ("RAD_assy.json", "WI 3700ED0001-101 ASSY.docx"),
        ("RAD_lam.json", "WI 3700ED0001-101 LAM.docx"),
    ],
    "ELEV": [
        ("ELEV_4401.json", "WI 4401-ASSEMBLY PROCESS.docx; WI 4401-PAINT.docx"),
    ],
    "AEGIS": [
        ("AEGIS_00999000563.json", "WI 00999000563.docx"),
    ],
}


def load_extracted(program: str):
    """Combine all cached extractions for a program -> list[CureSpec] + complexity dict."""
    cures, complexity = [], {}
    for cache_name, _src in PROGRAM_WIS.get(program, []):
        p = EXTRACTIONS_DIR / cache_name
        if not p.exists():
            continue
        wc = CachedWIExtractor(str(p)).extract(program, str(p))
        cures += wc.cures
        # merge complexity (sum counts across docs)
        for k, v in wc.complexity.items():
            if isinstance(v, (int, float)):
                complexity[k] = complexity.get(k, 0) + v
    return cures, complexity


def get_complexity_features(program: str) -> dict:
    _cures, comp = load_extracted(program)
    return comp


async def ingest_program(db: AsyncSession, program: str) -> dict:
    """Extract + validate + persist wi_constraint rows for a program. Returns report dict."""
    cures, complexity = load_extracted(program)
    rep = validate(program, cures)

    # replace existing rows for this program (idempotent re-ingest)
    await db.execute(delete(WIConstraint).where(WIConstraint.program == program))
    matched_quotes = {id(ec) for (_rc, ec) in rep.matched}
    for ec in cures:
        validated = id(ec) in matched_quotes
        db.add(WIConstraint(
            program=program,
            source_file="; ".join(s for _c, s in PROGRAM_WIS.get(program, [])),
            after_op=ec.op,
            label=ec.label[:255],
            dwell_hr=ec.dwell_hours(),
            constraint_type=ec.constraint_type,
            llm_provider="claude-opus-4-7",
            validated=validated,
            validation_notes=("matched router cure" if validated else "new candidate / unmatched"),
            source_quote=(ec.source_quote or "")[:2000],
        ))
    await db.commit()
    return dict(program=program, summary=rep.summary(),
                matched=len(rep.matched), missing=len(rep.missing),
                ifs_sourced=len(rep.ifs_sourced), candidates=len(rep.extra),
                match_rate=round(rep.match_rate * 100),
                n_extracted=len(cures), complexity=complexity)
