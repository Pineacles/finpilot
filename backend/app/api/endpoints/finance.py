from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, func, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import SavingsGoal, Milestone, Transaction
from app.models.user import User
from app.schemas.finance import (
    BudgetCreate, BudgetResponse,
    SavingsGoalCreate, SavingsGoalUpdate, SavingsGoalResponse,
    MilestoneCreate, MilestoneResponse,
    RecurringExpenseCreate, RecurringExpenseResponse, RecurringExpenseUpdate,
    RecurringSuggestionResponse,
    CashFlowMonth,
)
from app.services import budget_service, portfolio_service, recurring_detection, recurring_service
from app.services.budget_service import BudgetNotFoundError
from app.services.recurring_service import RecurringNotFoundError

router = APIRouter(prefix="/api/dashboard", tags=["finance"])


# ─── Budgets ───────────────────────────────────────────────
# Logic lives in app.services.budget_service so the dashboard (JWT) and
# agent (API key) routers stay in sync.

@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await budget_service.list_budgets(db, user.id)


@router.post("/budgets", response_model=BudgetResponse)
async def create_budget(
    body: BudgetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await budget_service.create_budget(db, user.id, body)


@router.delete("/budgets/{budget_id}")
async def delete_budget(
    budget_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await budget_service.delete_budget(db, user.id, budget_id)
    except BudgetNotFoundError:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"status": "deleted"}


# ─── Savings Goals ─────────────────────────────────────────

def _goal_response(goal: SavingsGoal, total_wealth: float) -> SavingsGoalResponse:
    """Build the response with progress computed from real total wealth
    (portfolio + cash + bank balance), not the manual, never-updated
    SavingsGoal.current_amount column. current_amount is overridden with
    the same figure so the "amount saved so far" the frontend displays
    stays consistent with progress_pct."""
    r = SavingsGoalResponse.model_validate(goal)
    r.current_amount = total_wealth
    r.progress_pct = (total_wealth / goal.target_amount * 100) if goal.target_amount else 0
    return r


@router.get("/goals", response_model=list[SavingsGoalResponse])
async def list_goals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavingsGoal).where(SavingsGoal.user_id == user.id)
    )
    goals = result.scalars().all()
    total_wealth = await portfolio_service.compute_total_wealth(db, user.id)
    return [_goal_response(g, total_wealth) for g in goals]


@router.post("/goals", response_model=SavingsGoalResponse)
async def create_goal(
    body: SavingsGoalCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = SavingsGoal(user_id=user.id, **body.model_dump())
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    total_wealth = await portfolio_service.compute_total_wealth(db, user.id)
    return _goal_response(goal, total_wealth)


@router.patch("/goals/{goal_id}", response_model=SavingsGoalResponse)
async def update_goal(
    goal_id: str,
    body: SavingsGoalUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavingsGoal).where(and_(SavingsGoal.id == goal_id, SavingsGoal.user_id == user.id))
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(goal, field, value)
    await db.commit()
    await db.refresh(goal)
    total_wealth = await portfolio_service.compute_total_wealth(db, user.id)
    return _goal_response(goal, total_wealth)


# ─── Milestones ────────────────────────────────────────────

@router.get("/milestones", response_model=list[MilestoneResponse])
async def list_milestones(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Milestone).where(Milestone.user_id == user.id).order_by(Milestone.target_date)
    )
    return result.scalars().all()


@router.post("/milestones", response_model=MilestoneResponse)
async def create_milestone(
    body: MilestoneCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ms = Milestone(user_id=user.id, **body.model_dump())
    db.add(ms)
    await db.commit()
    await db.refresh(ms)
    return MilestoneResponse.model_validate(ms)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    milestone_id: str,
    achieved: bool = False,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Milestone).where(and_(Milestone.id == milestone_id, Milestone.user_id == user.id))
    )
    ms = result.scalar_one_or_none()
    if not ms:
        raise HTTPException(status_code=404, detail="Milestone not found")
    if achieved:
        from datetime import datetime, timezone
        ms.achieved = True
        ms.achieved_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ms)
    return MilestoneResponse.model_validate(ms)


# ─── Recurring Expenses ───────────────────────────────────
# Note: /recurring/detected must be declared before /recurring/{recurring_id}
# so FastAPI doesn't swallow it as a path-param match.

@router.get("/recurring/detected", response_model=list[RecurringSuggestionResponse])
async def get_detected_recurring(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Suggested recurring expenses inferred from transaction history:
    merchants with >=3 similarly-timed, similarly-priced transactions that
    aren't already tracked as a RecurringExpense. Accept a suggestion by
    POSTing it to /recurring; dismissals are tracked client-side via
    /api/settings (dismissed_recurring_suggestions)."""
    suggestions = await recurring_detection.detect_recurring_expenses(db, user.id)
    return [RecurringSuggestionResponse(**vars(s)) for s in suggestions]


@router.get("/recurring", response_model=list[RecurringExpenseResponse])
async def list_recurring(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await recurring_service.list_recurring(db, user.id)


@router.post("/recurring", response_model=RecurringExpenseResponse)
async def create_recurring(
    body: RecurringExpenseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await recurring_service.create_recurring(db, user.id, body)


@router.patch("/recurring/{recurring_id}", response_model=RecurringExpenseResponse)
async def update_recurring(
    recurring_id: str,
    body: RecurringExpenseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await recurring_service.update_recurring(db, user.id, recurring_id, body)
    except RecurringNotFoundError:
        raise HTTPException(status_code=404, detail="Recurring expense not found")


@router.delete("/recurring/{recurring_id}")
async def delete_recurring(
    recurring_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await recurring_service.delete_recurring(db, user.id, recurring_id)
    except RecurringNotFoundError:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return {"status": "deleted", "id": recurring_id}


# ─── Cash Flow ─────────────────────────────────────────────

@router.get("/cashflow", response_model=list[CashFlowMonth])
async def get_cashflow(
    months: int = 6,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    start = (today - relativedelta(months=months - 1)).replace(day=1)

    result = await db.execute(
        select(
            extract("year", Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(func.case((Transaction.amount > 0, Transaction.amount), else_=0)).label("income"),
            func.sum(func.case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)).label("expenses"),
        )
        .where(and_(Transaction.user_id == user.id, Transaction.date >= start))
        .group_by("year", "month")
        .order_by("year", "month")
    )

    rows = result.all()
    return [
        CashFlowMonth(
            month=f"{int(r.year)}-{int(r.month):02d}",
            income=float(r.income),
            expenses=float(r.expenses),
            net=float(r.income) - float(r.expenses),
        )
        for r in rows
    ]
