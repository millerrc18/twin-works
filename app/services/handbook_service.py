"""Version-controlled, sanitized user handbook content."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import bleach
import markdown


BASE = Path(__file__).resolve().parents[2]
CONTENT_ROOT = BASE / "docs" / "user"
MANIFEST = BASE / "app" / "data" / "handbook.v1.json"
ALLOWED_TAGS = {
    "a", "blockquote", "code", "em", "h1", "h2", "h3", "h4", "hr",
    "li", "ol", "p", "pre", "strong", "table", "tbody", "td", "th",
    "thead", "tr", "ul",
}
ALLOWED_ATTRIBUTES = {"a": ["href", "title"], "code": ["class"], "h2": ["id"],
                      "h3": ["id"], "h4": ["id"]}


@dataclass(frozen=True)
class HandbookPage:
    slug: str
    title: str
    section: str
    order: int
    summary: str
    owner: str
    review_due: date
    source_path: Path
    markdown_text: str
    html: str


def _safe_source(filename: str) -> Path:
    path = (CONTENT_ROOT / filename).resolve()
    if CONTENT_ROOT.resolve() not in path.parents or path.suffix.lower() != ".md":
        raise ValueError(f"Unsafe handbook source path: {filename}")
    return path


def _render(source: str) -> str:
    rendered = markdown.markdown(
        source, extensions=["fenced_code", "tables", "toc"], output_format="html5")
    return bleach.clean(
        rendered, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES,
        protocols={"http", "https", "mailto"}, strip=True,
    )


@lru_cache(maxsize=1)
def pages() -> tuple[HandbookPage, ...]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported handbook manifest schema")
    seen = set()
    result = []
    for item in manifest.get("pages", []):
        slug = item["slug"].strip().lower()
        if not re.fullmatch(r"[a-z0-9-]+", slug) or slug in seen:
            raise ValueError(f"Invalid or duplicate handbook slug: {slug}")
        seen.add(slug)
        path = _safe_source(item["file"])
        source = path.read_text(encoding="utf-8")
        result.append(HandbookPage(
            slug=slug, title=item["title"], section=item["section"],
            order=int(item["order"]), summary=item["summary"], owner=item["owner"],
            review_due=date.fromisoformat(item["review_due"]), source_path=path,
            markdown_text=source, html=_render(source),
        ))
    return tuple(sorted(result, key=lambda row: (row.order, row.title)))


def page(slug: str) -> HandbookPage | None:
    return next((row for row in pages() if row.slug == slug), None)


def sections() -> list[dict]:
    grouped = {}
    for item in pages():
        grouped.setdefault(item.section, []).append(item)
    return [{"name": name, "pages": rows} for name, rows in grouped.items()]


def search(query: str) -> list[dict]:
    terms = [term for term in re.findall(r"[a-z0-9]+", query.lower()) if len(term) > 1]
    if not terms:
        return []
    results = []
    for item in pages():
        title = item.title.lower()
        haystack = f"{item.title} {item.summary} {item.markdown_text}".lower()
        if not all(term in haystack for term in terms):
            continue
        score = sum(5 if term in title else 1 for term in terms)
        results.append({"page": item, "score": score})
    return sorted(results, key=lambda row: (-row["score"], row["page"].order))


def validate_internal_links() -> list[str]:
    slugs = {item.slug for item in pages()}
    errors = []
    for item in pages():
        for target in re.findall(r"\]\(/handbook/([a-z0-9-]+)(?:#[^)]+)?\)",
                                 item.markdown_text):
            if target not in slugs:
                errors.append(f"{item.slug}: unknown handbook link {target}")
    return errors
