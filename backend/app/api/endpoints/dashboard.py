from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Category, Budget
from app.models.stock import StockPosition
from app.models.user import User
from app.schemas.dashboard import OverviewResponse, AccountBalance, RecentTransaction

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Portfolio
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()
    portfolio_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in positions)
    portfolio_cost = sum(p.avg_cost_price * p.quantity for p in positions)
    portfolio_pnl = portfolio_value - portfolio_cost
    portfolio_pnl_pct = (portfolio_pnl / portfolio_cost * 100) if portfolio_cost else 0

    # Accounts
    result = await db.execute(
        select(Account).where(Account.user_id == user.id)
    )
    accounts = [AccountBalance.model_validate(a) for a in result.scalars().all()]

    # Recent transactions
    result = await db.execute(
        select(Transaction, Category)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user.id)
        .order_by(desc(Transaction.date))
        .limit(5)
    )
    recent = []
    for txn, cat in result.all():
        recent.append(RecentTransaction(
            id=txn.id,
            date=txn.date.isoformat(),
            merchant=txn.merchant,
            amount=txn.amount,
            currency=txn.currency,
            category_name=cat.name if cat else None,
        ))

    # Budget health (simple: how much spent vs budget for active budgets)
    result = await db.execute(
        select(Budget).where(Budget.user_id == user.id)
    )
    budgets = result.scalars().all()
    budget_health = []
    for b in budgets:
        budget_health.append({
            "id": b.id,
            "name": b.name,
            "amount": b.amount,
            "period": b.period,
            "spent": 0,  # Will be computed properly when transactions exist
        })

    net_worth = portfolio_value  # Will add bank balances when available

    return OverviewResponse(
        net_worth=net_worth,
        portfolio_value=portfolio_value,
        portfolio_pnl=portfolio_pnl,
        portfolio_pnl_pct=portfolio_pnl_pct,
        accounts=accounts,
        recent_transactions=recent,
        budget_health=budget_health,
    )
