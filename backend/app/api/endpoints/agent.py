"""Agent endpoints — API key auth for AI assistant integration."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.database import get_db
from app.models.finance import Transaction, Budget, Category, RecurringExpense
from app.models.stock import StockPosition
from app.models.user import User
from app.schemas.finance import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/transaction", response_model=TransactionResponse)
async def log_transaction(
    body: TransactionCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    txn = Transaction(user_id=user.id, **body.model_dump())
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.get("/summary/financial")
async def financial_summary(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    month_start = today.replace(day=1)

    # Monthly spending
    result = await db.execute(
        select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
            and_(
                Transaction.user_id == user.id,
                Transaction.date >= month_start,
                Transaction.amount < 0,
            )
        )
    )
    monthly_spent = float(result.scalar())

    # Monthly income
    result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            and_(
                Transaction.user_id == user.id,
                Transaction.date >= month_start,
                Transaction.amount > 0,
            )
        )
    )
    monthly_income = float(result.scalar())

    # Budget status
    result = await db.execute(select(Budget).where(Budget.user_id == user.id))
    budgets = result.scalars().all()
    budget_status = []
    for b in budgets:
        spent_result = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.date >= month_start,
                    Transaction.amount < 0,
                    Transaction.category_id == b.category_id if b.category_id else True,
                )
            )
        )
        spent = float(spent_result.scalar())
        budget_status.append({"name": b.name, "limit": b.amount, "spent": spent})

    # Upcoming bills
    result = await db.execute(
        select(RecurringExpense).where(
            and_(
                RecurringExpense.user_id == user.id,
                RecurringExpense.active == True,
                RecurringExpense.next_due_date <= today + timedelta(days=14),
            )
        )
    )
    upcoming = [{"name": r.name, "amount": r.amount, "due": r.next_due_date.isoformat()} for r in result.scalars().all()]

    return {
        "month": month_start.isoformat(),
        "spent": monthly_spent,
        "income": monthly_income,
        "net": monthly_income - monthly_spent,
        "budgets": budget_status,
        "upcoming_bills": upcoming,
    }


@router.get("/summary/portfolio")
async def portfolio_summary(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()

    total_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in positions)
    total_pnl = sum(p.unrealized_pnl or 0 for p in positions)

    top_movers = sorted(positions, key=lambda p: abs(p.unrealized_pnl or 0), reverse=True)[:5]

    return {
        "total_value": total_value,
        "total_pnl": total_pnl,
        "positions_count": len(positions),
        "top_movers": [
            {
                "symbol": p.symbol,
                "name": p.name,
                "pnl": p.unrealized_pnl,
                "value": (p.last_price or p.avg_cost_price) * p.quantity,
            }
            for p in top_movers
        ],
    }
