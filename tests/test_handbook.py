"""DOC-01 handbook registry, sanitization, search, and route contracts."""
from fastapi.testclient import TestClient


def test_handbook_registry_and_links_are_valid():
    from app.services import handbook_service as handbook

    handbook.pages.cache_clear()
    pages = handbook.pages()

    assert len(pages) == 9
    assert pages[0].slug == "getting-started"
    assert handbook.validate_internal_links() == []
    assert handbook.page("resources-tooling").owner == "Industrial Engineering"
    assert handbook.page("missing") is None


def test_handbook_search_requires_all_terms_and_ranks_title_matches():
    from app.services import handbook_service as handbook

    results = handbook.search("resources tooling")

    assert results
    assert results[0]["page"].slug == "resources-tooling"
    assert handbook.search("term-that-does-not-exist") == []


def test_handbook_markdown_is_sanitized():
    from app.services.handbook_service import _render

    rendered = _render(
        "# Safe\n<script>alert('x')</script>\n[bad](javascript:alert('x'))")

    assert "<h1>Safe</h1>" in rendered
    assert "<script" not in rendered
    assert "javascript:" not in rendered


def test_handbook_routes_and_openapi_coexist():
    from app.main import app

    with TestClient(app) as client:
        home = client.get("/handbook")
        tooling = client.get("/handbook/resources-tooling")
        search = client.get("/handbook", params={"q": "occupancy lease"})
        missing = client.get("/handbook/not-a-page")
        openapi = client.get("/docs")

    assert home.status_code == 200
    assert "Getting Started" in home.text
    assert 'href="/handbook"' in home.text
    assert tooling.status_code == 200
    assert "Aeronose counts are draft inventory facts only" in tooling.text
    assert "Resources and Tooling" in search.text
    assert missing.status_code == 404
    assert openapi.status_code == 200
    assert "Swagger UI" in openapi.text
