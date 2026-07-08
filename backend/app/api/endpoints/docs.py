"""API documentation endpoints — the agent API reference, generated live.

Available at (paths kept stable across the docs regeneration redesign):
  GET /api/docs/agent          → Markdown (full agent API reference)
  GET /api/docs/agent/json     → Structured JSON (grouped endpoint listing)
  GET /api/docs/agent/summary  → Quick one-line-per-endpoint summary

Unlike the old hand-maintained AGENT_API.md, everything served here is
introspected from the running app's routes at request time (cached) by
app.services.docs_service — so the docs cannot drift from the actual
routing table. GET /openapi.json remains the authoritative schema for
exact request/response fields.

Deliberately excluded from the agent (X-API-Key) surface — and therefore
absent from these docs:
  - /api/settings/*: user settings + API-key regeneration. The agent must
    never be able to rotate (or read) its own credentials; key management
    is a human-only action in the dashboard.
  - /api/brokers/saxo/connect|callback|disconnect: broker OAuth. The agent
    must not be able to establish or tear down brokerage credentials.
  - /api/dashboard/portfolio/public/toggle|status: public-share control.
    The agent must not be able to widen what is publicly exposed.
These exclusions are intentional security boundaries, not gaps.
"""
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.services import docs_service

router = APIRouter(prefix="/api/docs", tags=["docs"])

# Rendered docs are cached after the first request: route tables are fixed
# once the app has started, so introspection output can't change until
# restart. Keyed by app id so tests that build multiple app instances
# don't cross-contaminate.
_cache: dict[tuple[int, str], object] = {}


def _cached(request: Request, kind: str, render):
    key = (id(request.app), kind)
    if key not in _cache:
        _cache[key] = render(request.app)
    return _cache[key]


@router.get("/agent", response_class=PlainTextResponse)
async def get_agent_docs(request: Request):
    """Full agent API reference in Markdown — generated from the live route
    table (auth, base URL, error shape, every /api/agent endpoint with its
    summary). No authentication required."""
    return _cached(request, "markdown", docs_service.render_markdown)


@router.get("/agent/json")
async def get_agent_docs_json(request: Request):
    """Structured JSON listing of every /api/agent endpoint, grouped by
    resource — generated from the live route table, so it can't go stale.
    GET /openapi.json is the authoritative source for exact request/response
    schemas. No authentication required."""
    return _cached(request, "json", docs_service.render_json)


@router.get("/agent/summary")
async def get_agent_docs_summary(request: Request):
    """Quick one-line summary of every agent endpoint. Designed for AI
    agents to scan quickly. Generated from the live route table."""
    return _cached(request, "summary", docs_service.render_summary)
