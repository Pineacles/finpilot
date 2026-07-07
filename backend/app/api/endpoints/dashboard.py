from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Category, Budget
from app.models.stock import StockPosition
from app.models.user import User
from app.schemas.dashboard import OverviewResponse, AccountBalance, RecentTransaction
from app.services import account_service
from app.services.account_service import AccountNotFoundError

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

    # Accounts with computed balances
    result = await db.execute(
        select(Account).where(Account.user_id == user.id)
    )
    raw_accounts = result.scalars().all()

    accounts = []
    bank_balance = 0.0
    cc_balance = 0.0
    for acct in raw_accounts:
        balance = await account_service.compute_account_balance(db, user.id, acct)

        ab = AccountBalance.model_validate(acct)
        ab.balance = balance
        accounts.append(ab)

        if acct.type == "bank":
            bank_balance += balance
        elif acct.type == "credit_card":
            cc_balance += balance  # Will be negative (debt)

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

    net_worth = portfolio_value + bank_balance + cc_balance

    return OverviewResponse(
        display_name=user.display_name,
        net_worth=net_worth,
        portfolio_value=portfolio_value,
        portfolio_pnl=portfolio_pnl,
        portfolio_pnl_pct=portfolio_pnl_pct,
        accounts=accounts,
        recent_transactions=recent,
        budget_health=budget_health,
    )


class SetBalanceRequest(BaseModel):
    balance: float

@router.post("/accounts/{account_id}/set-balance")
async def set_account_balance(
    account_id: str,
    body: SetBalanceRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set the actual balance for an account. Stores directly — no fake transactions."""
    result = await db.execute(
        select(Account).where(and_(Account.id == account_id, Account.user_id == user.id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from datetime import datetime, timezone
    previous = account.balance
    account.balance = body.balance
    account.balance_date = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "ok",
        "previous_balance": previous,
        "new_balance": body.balance,
        "balance_date": account.balance_date.isoformat(),
    }


class CreditCardAccountResponse(BaseModel):
    id: str
    name: str
    currency: str
    settlement_patterns: list[str] | None = None

    model_config = {"from_attributes": True}


@router.get("/accounts/credit-cards", response_model=list[CreditCardAccountResponse])
async def list_credit_card_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Credit-card accounts with their configured settlement-match patterns
    (for the Settings > Accounts UI). Empty/None patterns means the account
    falls back to services.settlement.DEFAULT_SETTLEMENT_PATTERNS."""
    return await account_service.get_credit_card_accounts(db, user.id)


class SettlementPatternsRequest(BaseModel):
    patterns: list[str] | None = None


@router.patch("/accounts/{account_id}/settlement-patterns", response_model=CreditCardAccountResponse)
async def update_settlement_patterns(
    account_id: str,
    body: SettlementPatternsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Configure the issuer-match keywords used to detect this credit card's
    settlement payment on bank import (services/settlement.py)."""
    try:
        return await account_service.update_settlement_patterns(db, user.id, account_id, body.patterns)
    except AccountNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
