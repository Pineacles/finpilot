"""Generates the agent API reference FROM the live app, so it can never go
stale. Introspects `app.routes` for everything under /api/agent (path,
methods, auth, summary/description pulled from each route's `summary`
attribute or its endpoint function's docstring) and renders the markdown +
JSON that app.api.endpoints.docs serves.

GET /openapi.json remains the authoritative source for exact request/
response schemas — this module exists to give an agent (or a human) a fast,
readable map of what's available, generated rather than hand-maintained.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from fastapi import FastAPI
from fastapi.routing import APIRoute

AGENT_PREFIX = "/api/agent"

# Friendly group label per first path segment after /api/agent/. Anything
# not listed here falls back to a title-cased version of the segment.
_GROUP_LABELS = {
    "summary": "Summaries",
    "stats": "Statistics",
    "transactions": "Transactions",
    "transaction": "Transactions",
    "categorize": "Categorization",
    "categories": "Categories",
    "recurring": "Recurring expenses",
    "budgets": "Budgets",
    "merchants": "Merchant rules",
    "accounts": "Accounts",
    "portfolio": "Portfolio",
    "trade": "Trades",
    "trades": "Trades",
    "goals": "Goals",
    "milestones": "Milestones",
    "watchlist": "Watchlist",
    "import": "Import",
    "gmail": "Gmail sync",
}

_GROUP_ORDER = [
    "summary", "stats", "transactions", "categorize", "categories",
    "recurring", "budgets", "merchants", "accounts", "portfolio", "trade",
    "goals", "milestones", "watchlist", "import", "gmail",
]


@dataclass
class RouteInfo:
    path: str
    methods: list[str]
    name: str
    summary: str
    description: str
    group: str


def _group_for(path: str) -> str:
    rest = path[len(AGENT_PREFIX):].lstrip("/")
    segment = rest.split("/", 1)[0] if rest else "root"
    return segment or "root"


def _route_info(route: APIRoute) -> RouteInfo:
    methods = sorted(m for m in (route.methods or []) if m != "HEAD")
    doc = inspect.getdoc(route.endpoint) or ""
    summary = route.summary or (doc.splitlines()[0].strip() if doc else route.name.replace("_", " "))
    return RouteInfo(
        path=route.path,
        methods=methods,
        name=route.name,
        summary=summary,
        description=doc,
        group=_group_for(route.path),
    )


def collect_agent_routes(app: FastAPI) -> list[RouteInfo]:
    """Every /api/agent/* route currently registered on `app`, sorted by
    path then method — this IS the live source of truth; nothing here is
    hand-maintained."""
    routes = [
        r for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith(AGENT_PREFIX)
    ]
    infos = [_route_info(r) for r in routes]
    infos.sort(key=lambda r: (r.path, r.methods))
    return infos


def _grouped(infos: list[RouteInfo]) -> dict[str, list[RouteInfo]]:
    groups: dict[str, list[RouteInfo]] = {}
    for info in infos:
        groups.setdefault(info.group, []).append(info)
    return groups


def _ordered_group_keys(groups: dict[str, list[RouteInfo]]) -> list[str]:
    ordered = [g for g in _GROUP_ORDER if g in groups]
    ordered += sorted(g for g in groups if g not in _GROUP_ORDER)
    return ordered


_INTRO_MARKDOWN = """# FinPilot Agent API

FinPilot is a gateway for your AI agent: it can read your full financial
state (transactions, budgets, portfolio, recurring bills, ...) and fix data
mistakes (recategorize, correct balances, adjust trades, ...) on your behalf.

## Authentication

Every route below requires the `X-API-Key` header:

```
X-API-Key: <your agent api key>
```

Generate/rotate your key from the dashboard Settings page — the agent
cannot rotate its own key (see "Deliberately excluded" below).

## Base URL

`https://your-finpilot-domain.example.com/api/agent`

## Errors

All errors are FastAPI's default shape: `{"detail": "..."}` (a string, or a
structured object for a few routes that need extra fields, e.g.
`/trade`'s currency_mismatch 422). Requests for another user's resource (or
one that doesn't exist) return `404` — never a `403` that would leak
whether the resource exists for someone else.

## Deliberately excluded from this surface

The agent can do a lot, but not everything a logged-in user can do:

- **User settings / API key management** (`/api/settings/*`) — the agent
  must not be able to rotate its own credentials.
- **Saxo OAuth / broker connect** (`/api/brokers/saxo/connect|callback|disconnect`)
  — the agent must not be able to establish new brokerage credentials.
- **Public portfolio share toggling** (`/api/dashboard/portfolio/public/*`)
  — the agent must not be able to widen what's publicly exposed.

## Authoritative schema

`GET /openapi.json` is the source of truth for exact request/response
fields and status codes for every route (including the ones below). This
document is generated directly from the running app's routes — it cannot
go stale the way a hand-written reference can, but it intentionally stays
high-level (path, method, one-line summary).
"""


def render_markdown(app: FastAPI) -> str:
    infos = collect_agent_routes(app)
    groups = _grouped(infos)

    lines = [_INTRO_MARKDOWN, "## Endpoints\n"]
    for key in _ordered_group_keys(groups):
        label = _GROUP_LABELS.get(key, key.replace("_", " ").title())
        lines.append(f"### {label}\n")
        for info in groups[key]:
            method = info.methods[0] if info.methods else "?"
            lines.append(f"**{method} {info.path}** — {info.summary}")
            if info.description and info.description.splitlines()[0].strip() != info.summary:
                extra = "\n".join(info.description.splitlines()[1:]).strip()
                if extra:
                    lines.append(f"\n{extra}\n")
        lines.append("")
    return "\n".join(lines)


def render_json(app: FastAPI) -> dict:
    infos = collect_agent_routes(app)
    groups = _grouped(infos)

    endpoint_groups = {}
    for key in _ordered_group_keys(groups):
        endpoint_groups[key] = {
            "label": _GROUP_LABELS.get(key, key.replace("_", " ").title()),
            "endpoints": [
                {
                    "method": info.methods[0] if info.methods else None,
                    "path": info.path,
                    "summary": info.summary,
                }
                for info in groups[key]
            ],
        }

    return {
        "title": "FinPilot Agent API",
        "description": "Gateway for an AI agent to read the user's full financial state and fix data mistakes.",
        "base_url": "https://your-finpilot-domain.example.com/api/agent",
        "authoritative_schema": "GET /openapi.json — full request/response schemas for every route",
        "auth": {
            "header": "X-API-Key: <user_api_key>",
        },
        "excluded_from_agent_surface": [
            "/api/settings/* (user settings + API key rotation)",
            "/api/brokers/saxo/connect|callback|disconnect (broker OAuth)",
            "/api/dashboard/portfolio/public/* (public share toggling)",
        ],
        "endpoint_groups": endpoint_groups,
        "generated_from": "app.routes — always in sync, see app.services.docs_service",
    }


def render_summary(app: FastAPI) -> dict:
    infos = collect_agent_routes(app)
    groups = _grouped(infos)

    summary = {}
    for key in _ordered_group_keys(groups):
        label = _GROUP_LABELS.get(key, key.replace("_", " ").title())
        summary[key] = [
            f"{info.methods[0] if info.methods else '?'} {info.path} — {info.summary}"
            for info in groups[key]
        ]
    summary["_meta"] = [
        "GET /openapi.json is the source of truth for exact request/response schemas.",
        "This summary is generated directly from app.routes (see GET /api/docs/agent for the full reference).",
    ]
    return summary
