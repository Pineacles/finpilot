from datetime import datetime
from pydantic import BaseModel


class AccountBalance(BaseModel):
    id: str
    name: str
    type: str
    currency: str
    balance: float | None = 0.0

    model_config = {"from_attributes": True}


class RecentTransaction(BaseModel):
    id: str
    date: str
    merchant: str
    amount: float
    currency: str
    category_name: str | None = None

    model_config = {"from_attributes": True}


class OverviewResponse(BaseModel):
    display_name: str
    net_worth: float
    portfolio_value: float
    portfolio_pnl: float
    portfolio_pnl_pct: float
    accounts: list[AccountBalance]
    recent_transactions: list[RecentTransaction]
    budget_health: list[dict]


# --- Accounts (shared between dashboard + agent surfaces) ---

class AccountOut(BaseModel):
    """One account with its computed (anchor-aware) balance — used by both
    the dashboard account list and the agent's read-only account view."""
    id: str
    name: str
    type: str
    currency: str
    balance: float
    balance_date: str | None = None
    settlement_patterns: list[str] | None = None


class SetBalanceRequest(BaseModel):
    balance: float


class SetBalanceResponse(BaseModel):
    status: str
    previous_balance: float | None
    new_balance: float
    balance_date: str


class CreditCardAccountResponse(BaseModel):
    id: str
    name: str
    currency: str
    settlement_patterns: list[str] | None = None

    model_config = {"from_attributes": True}


class SettlementPatternsRequest(BaseModel):
    patterns: list[str] | None = None
