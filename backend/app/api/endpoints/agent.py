"""Agent endpoints: API key auth for AI assistant integration.

All endpoints use X-API-Key header authentication.
The agent can do everything a user can do through these endpoints.

This module is a thin aggregator. The actual route implementations live in:
  - agent_finance_router.py   : summaries, stats, transactions, categorize
  - agent_portfolio_router.py : trades, import, gmail, goals, milestones
"""
from fastapi import APIRouter

from app.api.endpoints.agent_finance_router import router as _finance_router
from app.api.endpoints.agent_portfolio_router import router as _portfolio_router

router = APIRouter(prefix="/api/agent", tags=["agent"])
router.include_router(_finance_router)
router.include_router(_portfolio_router)
