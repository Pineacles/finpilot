from datetime import date, datetime
from pydantic import BaseModel


# --- Categories ---
class CategoryCreate(BaseModel):
    name: str
    type: str = "expense"
    icon: str | None = None
    color: str | None = None
    parent_id: str | None = None


class CategoryResponse(BaseModel):
    id: str
    name: str
    type: str
    icon: str | None
    color: str | None
    parent_id: str | None

    model_config = {"from_attributes": True}


# --- Transactions ---
class TransactionCreate(BaseModel):
    account_id: str
    date: date
    merchant: str
    amount: float
    currency: str = "CHF"
    original_amount: float | None = None
    original_currency: str | None = None
    category_id: str | None = None
    notes: str | None = None


class TransactionResponse(BaseModel):
    id: str
    account_id: str
    date: date
    merchant: str
    amount: float
    currency: str
    original_amount: float | None
    original_currency: str | None
    category_id: str | None
    category_name: str | None = None
    notes: str | None
    viseca_transaction_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionUpdate(BaseModel):
    category_id: str | None = None
    notes: str | None = None
    merchant: str | None = None


# --- Budgets ---
class BudgetCreate(BaseModel):
    name: str
    category_id: str | None = None
    amount: float
    period: str = "monthly"
    start_date: date
    end_date: date | None = None


class BudgetResponse(BaseModel):
    id: str
    name: str
    category_id: str | None
    category_name: str | None = None
    amount: float
    period: str
    start_date: date
    end_date: date | None
    spent: float = 0.0
    remaining: float = 0.0
    pct_used: float = 0.0

    model_config = {"from_attributes": True}


# --- Savings Goals ---
class SavingsGoalCreate(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0.0
    target_date: date | None = None
    currency: str = "CHF"


class SavingsGoalUpdate(BaseModel):
    current_amount: float | None = None
    target_amount: float | None = None
    target_date: date | None = None
    name: str | None = None


class SavingsGoalResponse(BaseModel):
    id: str
    name: str
    target_amount: float
    current_amount: float
    target_date: date | None
    currency: str
    progress_pct: float = 0.0
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Milestones ---
class MilestoneCreate(BaseModel):
    name: str
    description: str | None = None
    target_date: date | None = None
    target_net_worth: float | None = None
    target_savings: float | None = None


class MilestoneResponse(BaseModel):
    id: str
    name: str
    description: str | None
    target_date: date | None
    target_net_worth: float | None
    target_savings: float | None
    achieved: bool
    achieved_at: datetime | None

    model_config = {"from_attributes": True}


# --- Recurring Expenses ---
class RecurringExpenseCreate(BaseModel):
    name: str
    amount: float
    currency: str = "CHF"
    frequency: str = "monthly"
    next_due_date: date
    category_id: str | None = None


class RecurringExpenseResponse(BaseModel):
    id: str
    name: str
    amount: float
    currency: str
    frequency: str
    next_due_date: date
    category_id: str | None
    category_name: str | None = None
    active: bool

    model_config = {"from_attributes": True}


# --- Cash Flow ---
class CashFlowMonth(BaseModel):
    month: str
    income: float
    expenses: float
    net: float
