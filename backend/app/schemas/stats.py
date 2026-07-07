"""Response schemas for monthly/yearly statistics (app.services.stats_service)."""
from pydantic import BaseModel


class StatsPeriod(BaseModel):
    year: int
    month: int | None = None
    start: str | None = None
    end: str | None = None


class PeriodTotals(BaseModel):
    income: float
    expenses: float
    txn_count: int
    net: float | None = None
    savings_rate: float | None = None
    avg_daily_spend: float | None = None
    avg_monthly_spend: float | None = None
    avg_monthly_income: float | None = None


class ComparisonEntry(BaseModel):
    current: float
    previous: float
    change: float
    change_pct: float


class CategoryTotal(BaseModel):
    id: str | None
    name: str
    color: str | None
    total: float
    count: int


class MerchantTotal(BaseModel):
    merchant: str
    total: float
    count: int


class DailySpend(BaseModel):
    date: str
    amount: float


class CumulativeSpend(BaseModel):
    date: str
    cumulative: float


class BudgetVsActual(BaseModel):
    name: str
    category: str
    budget: float
    spent: float
    remaining: float
    pct: float


class RecurringVsDiscretionary(BaseModel):
    recurring: float
    discretionary: float


class AccountBreakdown(BaseModel):
    name: str
    type: str
    total: float
    count: int


class MonthlyStatsResponse(BaseModel):
    period: StatsPeriod
    summary: PeriodTotals
    comparison: dict[str, ComparisonEntry]
    categories: list[CategoryTotal]
    top_merchants: list[MerchantTotal]
    daily_spend: list[DailySpend]
    spending_velocity: list[CumulativeSpend]
    budget_vs_actual: list[BudgetVsActual]
    recurring_vs_discretionary: RecurringVsDiscretionary
    account_breakdown: list[AccountBreakdown]


class MonthlyBreakdown(BaseModel):
    month: int
    income: float
    expenses: float
    net: float


class CategoryTrend(BaseModel):
    month: int
    category: str | None
    total: float


class NetWorthPoint(BaseModel):
    date: str
    value: float
    pnl: float


class YearlyStatsResponse(BaseModel):
    period: StatsPeriod
    summary: PeriodTotals
    comparison: dict[str, ComparisonEntry]
    monthly: list[MonthlyBreakdown]
    categories: list[CategoryTotal]
    category_trends: list[CategoryTrend]
    top_merchants: list[MerchantTotal]
    net_worth_history: list[NetWorthPoint]
