"""Docs/route sync: the /api/docs/agent* endpoints are generated from the
live route table (app.services.docs_service), so every route they document
must exist on the app — and every /api/agent route must be documented.
This is the regression guard that makes stale docs structurally impossible.

Uses FastAPI's TestClient without the lifespan context (no DB, no
SECRET_KEY validation needed — the docs endpoints are pure introspection).
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.main import app
from app.services import docs_service


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _live_agent_routes() -> set[tuple[str, str]]:
    """(METHOD, path) for every /api/agent route actually registered."""
    pairs = set()
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/agent"):
            for method in route.methods or []:
                if method != "HEAD":
                    pairs.add((method, route.path))
    return pairs


def test_docs_json_matches_live_routes_exactly(client):
    """Every endpoint in /api/docs/agent/json exists on the app, and every
    live /api/agent route appears in the docs. Set equality — no drift in
    either direction."""
    resp = client.get("/api/docs/agent/json")
    assert resp.status_code == 200
    body = resp.json()

    documented = set()
    for group in body["endpoint_groups"].values():
        for ep in group["endpoints"]:
            documented.add((ep["method"], ep["path"]))

    live = _live_agent_routes()

    assert documented - live == set(), f"documented but not registered: {documented - live}"
    # Docs list one method per RouteInfo entry; routes with several methods on
    # one path are emitted as separate entries by collect_agent_routes, so
    # full set equality must hold.
    assert live - documented == set(), f"registered but not documented: {live - documented}"


def test_docs_markdown_lists_every_agent_route(client):
    resp = client.get("/api/docs/agent")
    assert resp.status_code == 200
    markdown = resp.text

    # Hand-written intro essentials survive regeneration
    assert "X-API-Key" in markdown
    assert "/openapi.json" in markdown
    assert '{"detail"' in markdown

    # Exclusion rationale is documented
    assert "/api/settings" in markdown
    assert "public" in markdown.lower()

    for _method, path in _live_agent_routes():
        assert path in markdown, f"{path} missing from markdown docs"


def test_docs_summary_lists_every_agent_route(client):
    resp = client.get("/api/docs/agent/summary")
    assert resp.status_code == 200
    body = resp.json()

    lines = [line for key, group in body.items() if key != "_meta" for line in group]
    blob = "\n".join(lines)
    for _method, path in _live_agent_routes():
        assert path in blob, f"{path} missing from summary docs"


def test_every_agent_route_has_a_summary():
    """collect_agent_routes falls back name→summary; make sure no route ends
    up with a bare function-name summary (i.e. everything has summary= or a
    docstring)."""
    for info in docs_service.collect_agent_routes(app):
        assert info.summary and info.summary != info.name.replace("_", " "), (
            f"{info.methods} {info.path} has neither summary= nor a docstring"
        )
