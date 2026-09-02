# DOC-01a/b In-App Handbook

## Status

Handbook shell and initial operating content delivered 2026-09-02 at `/handbook`. FastAPI `/docs`
remains the API reference.

## Architecture

- Versioned manifest: `app/data/handbook.v1.json`
- Source content: `docs/user/*.md`
- Renderer/search: `app/services/handbook_service.py`
- Route: `app/routers/handbook.py`
- Template: `app/templates/handbook.html`

Markdown is rendered with Python-Markdown and sanitized with Bleach. The manifest restricts source
files to the handbook content directory and validates unique URL-safe slugs. Search requires every
query term and ranks title matches first.

## Initial Content

1. Getting Started
2. Planning Basis and Publication
3. Forecast Method
4. Data Sources and Freshness
5. Resources and Tooling
6. Workspace Guide
7. Administration Runbook
8. Glossary
9. Release Notes

Each page exposes an owner and review date. Mutable WIP, forecast, and source-freshness values remain
in live application views rather than copied into documentation.

## Acceptance

- Handbook home, page, and search routes render successfully.
- Missing slugs return 404.
- `/docs` continues to render Swagger UI.
- Markdown HTML and URI schemes are sanitized.
- Internal handbook links resolve against the manifest.
- Layout supports keyboard navigation, narrow screens, dark/light tokens, anchors, and printing.
- Full regression suite: 100 passed; focused Ruff and live route checks passed.

Contextual links and formal documentation review governance remain DOC-01c/DOC-01d.
