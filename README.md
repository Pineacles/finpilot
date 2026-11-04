# FinPilot

A personal finance app I built around Swiss e-banking: import bank and card
statements, categorize them automatically, track a small ETF/stock portfolio,
and expose a narrow API for a personal AI agent.

[![CI](https://github.com/Pineacles/finpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Pineacles/finpilot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![Dashboard overview](docs/screenshots/dashboard.png)

The screenshots use a deterministic, fully synthetic demo dataset (`backend/seed.py --demo`).

## What it does

- **Statement import**: camt.053 XML (ISO 20022), Valiant and Viseca CSV, PostFinance PDF
  statements, and a generic column mapper with saved import profiles. Imports are deduplicated
  by bank reference, with a fuzzy fallback.
- **Categorization that learns**: keyword rules, then a merchant table, then transaction
  history, then a per-user scikit-learn classifier (TF-IDF + SGD). An LLM is used only for
  genuinely unknown merchants. It is a per-user setting: Anthropic, any OpenAI-compatible
  endpoint, or a custom gateway, optionally enriched by a SearXNG lookup. User-supplied URLs go
  through an SSRF guard.
- **Credit card settlement**: detects the monthly card-bill payment on the bank account and
  zeroes the card balance, idempotently, so re-importing a statement is a no-op.
- **Portfolio**: positions and trades with live Yahoo Finance quotes, staleness and FX warnings,
  asset-type classification (equity, ETF, index, ...), value timeline and price charts, and an
  optional public read-only share link.
- **Saxo Bank sync**: read-only OpenAPI adapter (OAuth with PKCE, rotating refresh tokens, SIM
  environment, no order routing) with a background scheduler.
- **Gmail poller**: reads bank notification emails over IMAP and records the transactions.
- **Planning**: monthly and yearly statistics, budgets, savings goals with milestones, recurring
  payment detection with an upcoming-payments view, and a watchlist.
- **Customizable dashboard**: widget registry with per-user visibility and order.
- **Agent API**: `X-API-Key` authenticated routes under `/api/agent/*` over the same service
  layer as the UI (summaries, transactions, categorization, budgets, goals, merchants, trades,
  watchlist), plus self-describing docs at `/api/docs/agent`.

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, TanStack Query, Recharts |
| Backend | FastAPI, Python 3.12, async SQLAlchemy 2, Alembic, slowapi rate limiting |
| Database | PostgreSQL 16 (SQLite in tests) |
| Auth | JWT with refresh for the UI, per-user API key for the agent API |
| ML | scikit-learn, thefuzz |
| External | Yahoo Finance, Saxo OpenAPI, Anthropic / OpenAI-compatible LLM, Gmail IMAP |
| Infra | Docker Compose, GitHub Actions (pytest, tsc, eslint, build) |

Architecture, data model and integrations are described in [docs/architecture.md](docs/architecture.md).

## Run it locally

```bash
cp .env.example .env        # set SECRET_KEY and POSTGRES_PASSWORD
docker compose up -d        # web on :3010, api on :8001
docker compose exec api python seed.py --demo
```

Tests run offline: `cd backend && pytest tests -q`, and `cd frontend && npx tsc --noEmit`.

## License

[MIT](LICENSE)
