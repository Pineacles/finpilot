"""Budget CRUD + status: shared between the JWT dashboard router
(api/endpoints/finance.py) and the API-key agent router
(api/endpoints/agent_finance_router.py) so "spent/remaining/pct_used" is
computed identically on both surfaces.
"""
from __future__ import annotations

from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Budget, Category, Transaction
from app.schemas.finance import BudgetCreate, BudgetResponse


class BudgetNotFoundError(Exception):
    def __init__(self, budget_id: str):
        self.budget_id = budget_id
        super().__init__(f"Budget not found: {budget_id}")


def get_period_range(period: str, ref_date: date) -> tuple[date, date]:
    if period == "weekly":
        start = ref_date - timedelta(days=ref_date.weekday())
        end = start + timedelta(days=6)
    elif period == "yearly":
        start = ref_date.replace(month=1, day=1)
        end = ref_date.replace(month=12, day=31)
    else:  # monthly
        start = ref_date.replace(day=1)
        end = (start + relativedelta(months=1)) - timedelta(days=1)
    return start, end


async def list_budgets(db: AsyncSession, user_id: str) -> list[BudgetResponse]:
    result = await db.execute(
        select(Budget, Category)
        .outerjoin(Category, Budget.category_id == Category.id)
        .where(Budget.user_id == user_id)
    )

    responses = []
    today = date.today()
    for budget, cat in result.all():
        period_start, period_end = get_period_range(budget.period, today)

        spent_query = select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            and_(
                Transaction.user_id == user_id,
                Transaction.date >= period_start,
                Transaction.date <= period_end,
                Transaction.amount < 0,  # expenses only
            )
        )
        if budget.category_id:
            spent_query = spent_query.where(Transaction.category_id == budget.category_id)

        spent_result = await db.execute(spent_query)
        spent = float(spent_result.scalar())

        responses.append(BudgetResponse(
            id=budget.id,
            name=budget.name,
            category_id=budget.category_id,
            category_name=cat.name if cat else None,
            amount=budget.amount,
            period=budget.period,
            start_date=budget.start_date,
            end_date=budget.end_date,
            spent=spent,
            remaining=max(budget.amount - spent, 0),
            pct_used=(spent / budget.amount * 100) if budget.amount else 0,
        ))
    return responses


async def create_budget(db: AsyncSession, user_id: str, body: BudgetCreate) -> BudgetResponse:
    budget = Budget(user_id=user_id, **body.model_dump())
    db.add(budget)
    await db.commit()
    await db.refresh(budget)
    return BudgetResponse(
        id=budget.id, name=budget.name, category_id=budget.category_id,
        amount=budget.amount, period=budget.period,
        start_date=budget.start_date, end_date=budget.end_date,
        spent=0, remaining=budget.amount, pct_used=0,
    )


async def delete_budget(db: AsyncSession, user_id: str, budget_id: str) -> None:
    result = await db.execute(
        select(Budget).where(and_(Budget.id == budget_id, Budget.user_id == user_id))
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise BudgetNotFoundError(budget_id)
    await db.delete(budget)
    await db.commit()
