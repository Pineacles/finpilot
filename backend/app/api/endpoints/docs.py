"""API documentation endpoints — serves the full agent API reference.

Available at:
  GET /api/docs/agent          → Markdown (full docs)
  GET /api/docs/agent/json     → Structured JSON (all endpoints with details)
  GET /api/docs/agent/summary  → Quick summary of all available endpoints
"""
import os

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, JSONResponse

router = APIRouter(prefix="/api/docs", tags=["docs"])

_DOCS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "AGENT_API.md")


def _load_docs() -> str:
    try:
        with open(_DOCS_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "# API Documentation\n\nDocumentation file not found."


@router.get("/agent", response_class=PlainTextResponse)
async def get_agent_docs():
    """Full API documentation in Markdown format. No authentication required.

    Returns the complete AGENT_API.md reference including all endpoints,
    request/response schemas, example workflows, and data model.
    """
    return _load_docs()


@router.get("/agent/json")
async def get_agent_docs_json():
    """Structured JSON listing of all API endpoints with details.

    Designed for AI agents to quickly understand what's available.
    No authentication required.
    """
    return {
        "title": "FinPilot API",
        "description": "Personal finance dashboard + stock portfolio tracker for Swiss banking",
        "base_url": "https://your-finpilot-domain.example.com/api",
        "auth": {
            "jwt": {
                "description": "For dashboard/user endpoints",
                "login": "POST /api/auth/login with {email, password} → {access_token, refresh_token}",
                "header": "Authorization: Bearer <access_token>",
            },
            "api_key": {
                "description": "For agent endpoints",
                "header": "X-API-Key: <user_api_key>",
            },
        },
        "endpoint_groups": {
            "auth": {
                "description": "Authentication",
                "endpoints": [
                    {"method": "POST", "path": "/api/auth/login", "body": {"email": "str", "password": "str"}, "returns": "access_token + refresh_token"},
                    {"method": "POST", "path": "/api/auth/refresh", "body": {"refresh_token": "str"}, "returns": "new access_token + refresh_token"},
                ],
            },
            "dashboard": {
                "description": "Dashboard overview (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/overview", "returns": "net_worth, portfolio_value, accounts, recent_transactions, budget_health, display_name"},
                ],
            },
            "transactions": {
                "description": "Transaction management (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/transactions", "params": "category_id, from_date, to_date, search, limit, offset", "returns": "list of transactions"},
                    {"method": "POST", "path": "/api/dashboard/transactions", "body": {"date": "str", "merchant": "str", "amount": "float", "currency": "str", "category_id": "str?"}, "returns": "created transaction"},
                    {"method": "PATCH", "path": "/api/dashboard/transactions/{id}", "body": {"merchant": "str?", "category_id": "str?", "notes": "str?", "apply_merchant_to_all": "bool", "apply_category_to_all": "bool", "description_filter": "str?"}, "returns": "updated transaction"},
                ],
            },
            "categorization": {
                "description": "AI & manual categorization (JWT auth)",
                "endpoints": [
                    {"method": "POST", "path": "/api/dashboard/categorize/manual", "body": {"transaction_id": "str", "category_id": "str", "apply_to_all": "bool", "new_merchant": "str?"}, "returns": "updated count"},
                    {"method": "POST", "path": "/api/dashboard/categorize/bulk-manual", "body": {"transaction_ids": "list[str]", "category_id": "str"}, "returns": "updated count"},
                    {"method": "POST", "path": "/api/dashboard/categorize/ai", "body": {"transaction_ids": "list[str]", "custom_prompt": "str?"}, "returns": "categorized count + results"},
                ],
            },
            "categories": {
                "description": "Category hierarchy (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/categories", "returns": "list of categories with parent_id hierarchy"},
                    {"method": "POST", "path": "/api/dashboard/categories", "body": {"name": "str", "type": "str", "parent_id": "str?"}, "returns": "created category"},
                ],
            },
            "merchants": {
                "description": "Merchant auto-categorization rules (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/merchants", "returns": "list of merchants with patterns and default categories"},
                    {"method": "POST", "path": "/api/dashboard/merchants", "body": {"name": "str", "patterns": "str (pipe-separated)", "default_category_id": "str?"}, "returns": "created merchant"},
                    {"method": "PATCH", "path": "/api/dashboard/merchants/{id}", "body": {"name": "str?", "patterns": "str?", "default_category_id": "str?"}, "returns": "updated merchant"},
                    {"method": "DELETE", "path": "/api/dashboard/merchants/{id}", "returns": "deleted"},
                ],
            },
            "portfolio": {
                "description": "Stock portfolio management (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/portfolio", "returns": "positions with live prices, total_value, total_pnl, cash_balance in CHF"},
                    {"method": "POST", "path": "/api/dashboard/portfolio/trade", "body": {"symbol": "str", "type": "buy|sell|deposit|withdraw", "quantity": "float", "price": "float?", "currency": "str", "date": "str?", "fees": "float?", "deduct_from_cash": "bool"}, "returns": "trade result"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/trades", "params": "symbol, limit", "returns": "trade history with id, total_chf"},
                    {"method": "PATCH", "path": "/api/dashboard/portfolio/{position_id}", "body": {"quantity": "float?", "avg_cost_price": "float?"}, "returns": "ok"},
                    {"method": "DELETE", "path": "/api/dashboard/portfolio/{position_id}", "returns": "ok"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/chart/{ticker}", "params": "range (1d,5d,1mo,3mo,6mo,1y,2y,5y,max)", "returns": "price history (auto-selects intraday interval for 1d/5d)"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/live-prices", "returns": "{symbol: {price, change, change_pct}} — 15s cache for live ticker"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/value-timeline", "returns": "day-by-day portfolio value from transactions + yfinance"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/history", "params": "days", "returns": "portfolio snapshots"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/classifications", "returns": "per-symbol asset_type (equity|etf|index|crypto|bond|commodity|cash)"},
                    {"method": "GET", "path": "/api/dashboard/portfolio/public/status", "returns": "public sharing enabled + token"},
                    {"method": "POST", "path": "/api/dashboard/portfolio/public/toggle", "returns": "toggle public sharing on/off"},
                ],
            },
            "public_portfolio": {
                "description": "Public portfolio (no auth, share token required)",
                "endpoints": [
                    {"method": "GET", "path": "/api/public/portfolio/{token}", "returns": "full portfolio (holdings, P&L, cash)"},
                    {"method": "GET", "path": "/api/public/portfolio/{token}/chart/{ticker}", "params": "range", "returns": "price chart"},
                    {"method": "GET", "path": "/api/public/portfolio/{token}/trades", "params": "symbol, limit", "returns": "trade history"},
                    {"method": "GET", "path": "/api/public/portfolio/{token}/live-prices", "returns": "live prices"},
                    {"method": "GET", "path": "/api/public/portfolio/{token}/value-timeline", "returns": "portfolio value timeline"},
                    {"method": "GET", "path": "/api/public/portfolio/{token}/history", "params": "days", "returns": "snapshots"},
                ],
            },
            "stats": {
                "description": "Financial statistics (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/stats/monthly", "params": "year, month", "returns": "income, expenses, categories, merchants, velocity, budget_vs_actual"},
                    {"method": "GET", "path": "/api/dashboard/stats/yearly", "params": "year", "returns": "yearly summary, monthly breakdown, category trends"},
                ],
            },
            "finance": {
                "description": "Budgets, goals, milestones, recurring (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/dashboard/budgets", "returns": "budgets with spent/remaining"},
                    {"method": "POST", "path": "/api/dashboard/budgets", "body": {"name": "str", "amount": "float", "period": "str", "category_id": "str?"}, "returns": "created budget"},
                    {"method": "DELETE", "path": "/api/dashboard/budgets/{id}", "returns": "deleted"},
                    {"method": "GET", "path": "/api/dashboard/goals", "returns": "savings goals with progress"},
                    {"method": "POST", "path": "/api/dashboard/goals", "body": {"name": "str", "target_amount": "float"}, "returns": "created goal"},
                    {"method": "GET", "path": "/api/dashboard/milestones", "returns": "milestones"},
                    {"method": "POST", "path": "/api/dashboard/milestones", "body": {"name": "str", "target_date": "str?"}, "returns": "created milestone"},
                    {"method": "GET", "path": "/api/dashboard/recurring", "returns": "recurring expenses"},
                    {"method": "GET", "path": "/api/dashboard/cashflow", "params": "months", "returns": "monthly income/expenses/net"},
                ],
            },
            "import": {
                "description": "Bank statement import (JWT auth)",
                "endpoints": [
                    {"method": "POST", "path": "/api/import/csv", "body": "multipart: file (.csv/.xml/.tsv), account_id?, use_ai?", "returns": "imported/skipped/categorized counts + log", "note": "Supports Valiant CSV, PostFinance CSV, Viseca CSV/TSV, camt.053 XML"},
                ],
            },
            "sync": {
                "description": "Gmail bank notification sync (JWT auth)",
                "endpoints": [
                    {"method": "POST", "path": "/api/sync/gmail", "returns": "new_transactions, balance, errors"},
                    {"method": "GET", "path": "/api/sync/status", "returns": "last sync status per source"},
                ],
            },
            "settings": {
                "description": "User settings (JWT auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/settings", "returns": "settings grouped by category"},
                    {"method": "PUT", "path": "/api/settings", "body": {"settings": "dict[key, value]"}, "returns": "updated keys"},
                ],
            },
            "agent": {
                "description": "Full agent API (X-API-Key auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/agent/summary/financial", "returns": "monthly spending, income, budgets, accounts"},
                    {"method": "GET", "path": "/api/agent/summary/portfolio", "returns": "portfolio value, positions, P&L"},
                    {"method": "GET", "path": "/api/agent/stats/monthly", "params": "year, month", "returns": "full monthly stats"},
                    {"method": "GET", "path": "/api/agent/stats/yearly", "params": "year", "returns": "full yearly stats"},
                    {"method": "GET", "path": "/api/agent/transactions", "params": "category, from_date, to_date, search, limit", "returns": "transactions"},
                    {"method": "POST", "path": "/api/agent/transaction", "returns": "create transaction"},
                    {"method": "POST", "path": "/api/agent/categorize", "params": "category_name, transaction_id?, merchant?, description_contains?, new_merchant?, apply_to_all?", "returns": "categorized + renamed count"},
                    {"method": "GET", "path": "/api/agent/categories", "returns": "all categories"},
                    {"method": "POST", "path": "/api/agent/trade", "body": {"symbol": "str", "type": "buy|sell|deposit|withdraw", "quantity": "float", "price": "float?"}, "returns": "trade result"},
                    {"method": "GET", "path": "/api/agent/trades", "params": "symbol, limit", "returns": "trade history with id"},
                    {"method": "PATCH", "path": "/api/agent/trades/{trade_id}", "body": {"symbol?": "str", "quantity?": "float", "price?": "float"}, "returns": "updated"},
                    {"method": "DELETE", "path": "/api/agent/trades/{trade_id}", "returns": "deleted"},
                    {"method": "POST", "path": "/api/agent/goals", "body": {"name": "str", "type": "monthly_limit|monthly_target|savings_goal", "amount": "float"}, "returns": "created goal"},
                    {"method": "GET", "path": "/api/agent/goals", "returns": "all goals"},
                    {"method": "GET", "path": "/api/agent/goals/progress", "returns": "current month progress with status"},
                    {"method": "DELETE", "path": "/api/agent/goals/{id}", "returns": "deleted"},
                    {"method": "POST", "path": "/api/agent/milestones", "body": {"name": "str", "target_date?": "str", "target_net_worth?": "float"}, "returns": "created"},
                    {"method": "GET", "path": "/api/agent/milestones", "returns": "all milestones"},
                    {"method": "PATCH", "path": "/api/agent/milestones/{id}", "params": "achieved, description", "returns": "updated"},
                    {"method": "DELETE", "path": "/api/agent/milestones/{id}", "returns": "deleted"},
                    {"method": "POST", "path": "/api/agent/import", "body": "multipart: file", "returns": "import result"},
                    {"method": "POST", "path": "/api/agent/gmail/poll", "returns": "new_transactions, balance"},
                    {"method": "POST", "path": "/api/agent/portfolio/resync-currencies", "returns": "updated/unchanged/flagged symbols", "note": "Resyncs position currencies from yfinance and flags likely ticker mismatches"},
                ],
                "notes": [
                    "POST /api/agent/trade includes a 5% price collar — rejects fat-finger entries that deviate >5% from market price",
                ],
            },
            "docs": {
                "description": "API documentation (no auth)",
                "endpoints": [
                    {"method": "GET", "path": "/api/docs/agent", "returns": "Full API docs in Markdown"},
                    {"method": "GET", "path": "/api/docs/agent/json", "returns": "Structured JSON endpoint listing"},
                    {"method": "GET", "path": "/api/docs/agent/summary", "returns": "Quick one-line summary of all endpoints"},
                ],
            },
        },
        "supported_import_formats": ["Valiant CSV", "PostFinance CSV", "PostFinance Credit Card PDF", "Viseca CSV/TSV", "camt.053 XML (ISO 20022)"],
        "categorization_pipeline": [
            "1. Merchant DB — user-created + 60+ Swiss merchants with fuzzy matching",
            "2. Keywords — Swiss-German transaction types",
            "3. History — same merchant categorized before",
            "4. ML Classifier — TF-IDF trained on user's data",
            "5. AI/LLM — Claude via custom endpoint",
        ],
    }


@router.get("/agent/summary")
async def get_agent_docs_summary():
    """Quick one-line summary of every endpoint. Designed for AI agents to scan quickly."""
    return {
        "auth": [
            "POST /api/auth/login — get JWT token",
            "POST /api/auth/refresh — refresh token",
        ],
        "dashboard": [
            "GET /api/dashboard/overview — net worth, accounts, recent txns, budgets",
        ],
        "transactions": [
            "GET /api/dashboard/transactions — list/search/filter transactions",
            "POST /api/dashboard/transactions — create transaction",
            "PATCH /api/dashboard/transactions/{id} — update with scoped bulk-apply",
        ],
        "categorize": [
            "POST /api/dashboard/categorize/manual — categorize one (applies to all same merchant)",
            "POST /api/dashboard/categorize/bulk-manual — bulk categorize by IDs",
            "POST /api/dashboard/categorize/ai — AI categorize selected transactions",
        ],
        "portfolio": [
            "GET /api/dashboard/portfolio — positions + live prices + P&L in CHF",
            "POST /api/dashboard/portfolio/trade — buy/sell/deposit/withdraw",
            "GET /api/dashboard/portfolio/trades — trade history with CHF totals",
            "GET /api/dashboard/portfolio/live-prices — real-time prices (15s cache)",
            "GET /api/dashboard/portfolio/value-timeline — portfolio value from txns + yfinance",
            "GET /api/dashboard/portfolio/chart/{ticker} — price history (auto intraday for 1d/5d)",
            "GET /api/dashboard/portfolio/classifications — per-symbol asset_type (equity/etf/index/...)",
        ],
        "agent": [
            "GET /api/agent/summary/financial — monthly spending overview",
            "GET /api/agent/summary/portfolio — portfolio summary",
            "POST /api/agent/trade — execute trade",
            "GET/PATCH/DELETE /api/agent/trades/{id} — full CRUD on trades",
            "POST /api/agent/categorize — categorize by ID or merchant with rename",
            "POST /api/agent/goals — create budget/savings goal",
            "GET /api/agent/goals/progress — current month goal status",
            "POST /api/agent/portfolio/resync-currencies — resync position currencies from yfinance",
        ],
        "import": [
            "POST /api/import/csv — import Valiant/PostFinance/Viseca/camt.053",
        ],
        "docs": [
            "GET /api/docs/agent — full Markdown docs",
            "GET /api/docs/agent/json — structured JSON endpoint listing",
            "GET /api/docs/agent/summary — this summary",
        ],
    }
