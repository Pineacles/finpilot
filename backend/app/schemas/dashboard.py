from datetime import datetime
from pydantic import BaseModel


class AccountBalance(BaseModel):
    id: str
    name: str
    type: str
    currency: str
    balance: float = 0.0

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
