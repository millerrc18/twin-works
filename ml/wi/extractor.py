"""WI constraint extraction — LLM does STRUCTURED EXTRACTION ONLY, never prediction.

Proven in spike: reproduced all 15 hand-mined RADOME_CURES + found 4 more.

Architecture note: the LLM (ai-critic MCP / future GPT) can only be invoked by the
assistant, not by unattended Python (same constraint as the IFS MCP). So extraction is a
two-part flow:
  1. `build_prompt(text)` -> (system, prompt)  — pure, testable
  2. an `llm_call(system, prompt) -> str` callable supplied by the caller (the assistant
     runs the MCP and pipes the JSON back; or a cached/stub callable for offline runs)
`parse_response(raw)` -> list[CureSpec] normalizes whatever the provider returns into the
strict schema, so swapping Claude<->GPT never touches downstream code.
"""
import json
import re
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict


# ---------- data model ----------
@dataclass
class CureSpec:
    op: int | None
    label: str
    dwell_value: float | None
    dwell_unit: str | None          # hr | min | day
    gate: str = ""
    source_quote: str = ""
    constraint_type: str = "CURE"   # CURE | GATE

    def dwell_hours(self) -> float | None:
        if self.dwell_value is None:
            return None
        u = (self.dwell_unit or "hr").lower()
        if u.startswith("day"):
            return self.dwell_value * 24.0
        if u.startswith("min"):
            return self.dwell_value / 60.0
        return float(self.dwell_value)


@dataclass
class WIConstraints:
    program: str
    source_file: str
    cures: list = field(default_factory=list)      # list[CureSpec]
    complexity: dict = field(default_factory=dict)  # step_count, hold_points, ...
    provider: str = ""

    def to_json(self):
        return json.dumps(dict(program=self.program, source_file=self.source_file,
                               provider=self.provider,
                               cures=[asdict(c) for c in self.cures],
                               complexity=self.complexity), indent=2)


# ---------- docx text extraction (proven in spike) ----------
def extract_docx_text(path: str) -> str:
    z = zipfile.ZipFile(path)
    xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt


# ---------- complexity features (cheap, deterministic, no LLM) ----------
def complexity_features(text: str) -> dict:
    return dict(
        char_count=len(text),
        op_count=len(set(re.findall(r"\bOP\s*(\d{2,4})\b", text, re.I))),
        hold_points=len(re.findall(r"\b(hold|do not proceed|wait|caution|stop)\b", text, re.I)),
        cure_mentions=len(re.findall(r"\bcure\b", text, re.I)),
        inspection_points=len(re.findall(r"\binspect", text, re.I)),
    )


# ---------- prompt (extraction-only, strict JSON) ----------
SYSTEM_PROMPT = (
    "You are a manufacturing Work Instruction constraint extractor for an aerospace "
    "composite part. Extract STRUCTURED FACTS ONLY — never predict schedules, dates, or "
    "completion times. Extract cure/dwell requirements, hold/gate points, hardness/"
    "inspection gates, time-window couplings ('within X hours'), and fixture/crew "
    "requirements. For each: operation number (OP ###) if stated, short label, numeric "
    "dwell/window value + unit, any hardness/acceptance gate, and the exact WI phrase "
    "(short quote). Output STRICT JSON only: "
    '{"constraints":[{"op":<int|null>,"label":"","dwell_value":<number|null>,'
    '"dwell_unit":"hr|min|day|null","gate":"","source_quote":""}]}. '
    "For min/max windows put both in the label. Do not invent values not in the text. "
    "Be exhaustive for cure/gate/hold constraints; ignore generic safety boilerplate."
)


def build_prompt(text: str, part_label: str = "") -> tuple[str, str]:
    prompt = (f"Extract all cure, dwell, hold-point, hardness-gate, time-window-coupling, "
              f"and fixture/crew constraints from this Work Instruction ({part_label}). "
              f"Return strict JSON per the schema.\n\nWI text follows:\n=====\n{text}\n=====")
    return SYSTEM_PROMPT, prompt


def parse_response(raw: str) -> list[CureSpec]:
    """Normalize LLM JSON (tolerant of prose wrapping the JSON)."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    data = json.loads(m.group(0))
    out = []
    for c in data.get("constraints", []):
        label = c.get("label", "") or ""
        gate = c.get("gate", "") or ""
        ctype = "GATE" if ("gate" in label.lower() or "shore" in gate.lower()
                           or "peel" in label.lower()) else "CURE"
        out.append(CureSpec(op=c.get("op"), label=label,
                            dwell_value=c.get("dwell_value"),
                            dwell_unit=c.get("dwell_unit"),
                            gate=gate, source_quote=c.get("source_quote", "") or "",
                            constraint_type=ctype))
    return out


# ---------- extractor adapter ----------
class WIExtractor(ABC):
    provider = "abstract"

    @abstractmethod
    def extract(self, program: str, path: str) -> WIConstraints: ...


class LLMWIExtractor(WIExtractor):
    """Model-agnostic. `llm_call(system, prompt)->raw_json_str` is injected so the
    assistant can wire the ai-critic MCP (Claude now, GPT later) without code changes."""

    def __init__(self, llm_call, provider="claude"):
        self._call = llm_call
        self.provider = provider

    def extract(self, program: str, path: str) -> WIConstraints:
        text = extract_docx_text(path) if path.endswith(".docx") else open(path, encoding="utf-8").read()
        system, prompt = build_prompt(text, part_label=program)
        raw = self._call(system, prompt)
        cures = parse_response(raw)
        return WIConstraints(program=program, source_file=path, cures=cures,
                             complexity=complexity_features(text), provider=self.provider)


class CachedWIExtractor(WIExtractor):
    """Reads a previously-saved extraction JSON (from an assistant MCP run) so the
    pipeline runs offline and deterministically. provider tag preserved."""
    provider = "cached"

    def __init__(self, cache_path: str):
        self.cache_path = cache_path

    def extract(self, program: str, path: str) -> WIConstraints:
        data = json.load(open(self.cache_path, encoding="utf-8"))
        cures = [CureSpec(**{k: c.get(k) for k in
                             ("op", "label", "dwell_value", "dwell_unit", "gate",
                              "source_quote", "constraint_type") if k in c})
                 for c in data.get("cures", data.get("constraints", []))]
        return WIConstraints(program=program, source_file=path, cures=cures,
                             complexity=data.get("complexity", {}),
                             provider=data.get("provider", "cached"))
