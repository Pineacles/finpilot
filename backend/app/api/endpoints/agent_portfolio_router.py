"""Agent sub-router — API key auth for AI assistant integration."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, and_, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Budget, Category, RecurringExpense, SavingsGoal, Milestone
from app.models.merchant import Merchant
from app.models.stock import StockPosition, StockTransaction
from app.models.user import User
from app.schemas.finance import TransactionCreate, TransactionResponse

router = APIRouter(tags=["agent"])


# ── Portfolio Trades ─────────────────────────────────────────────

class AgentTradeRequest(BaseModel):
    symbol: str
    type: str  # buy | sell | deposit | withdraw
    quantity: float
    price: float = 0
    currency: str = "USD"
    date: str | None = None
    fees: float = 0
    deduct_from_cash: bool = True


@router.post("/trade")
@router.post("/trades")
async def agent_trade(
    body: AgentTradeRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Execute a portfolio trade. Same as dashboard but with API key auth."""
    from app.api.endpoints.portfolio import execute_trade, TradeRequest
    trade_req = TradeRequest(**body.model_dump())
    return await execute_trade(body=trade_req, user=user, db=db)


@router.get("/trades")
async def agent_trades(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Trade history."""
    query = select(StockTransaction).where(StockTransaction.user_id == user.id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol.upper())
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": t.id, "symbol": t.symbol, "type": t.type, "quantity": t.quantity,
            "price": t.price, "fees": t.fees, "currency": t.currency, "date": t.executed_at.isoformat(),
        }
        for t in result.scalars().all()
    ]


class AgentTradeUpdate(BaseModel):
    symbol: str | None = None
    type: str | None = None
    quantity: float | None = None
    price: float | None = None
    fees: float | None = None
    currency: str | None = None
    date: str | None = None


@router.patch("/trades/{trade_id}")
async def agent_update_trade(
    trade_id: str,
    body: AgentTradeUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a stock transaction."""
    result = await db.execute(
        select(StockTransaction).where(and_(StockTransaction.id == trade_id, StockTransaction.user_id == user.id))
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Trade not found")

    if body.symbol is not None:
        txn.symbol = body.symbol.upper().strip()
    if body.type is not None:
        txn.type = body.type
    if body.quantity is not None:
        txn.quantity = body.quantity
    if body.price is not None:
        txn.price = body.price
    if body.fees is not None:
        txn.fees = body.fees
    if body.currency is not None:
        txn.currency = body.currency
    if body.date is not None:
        from datetime import datetime, timezone
        txn.executed_at = datetime.fromisoformat(body.date).replace(tzinfo=timezone.utc)

    await db.commit()
    return {"status": "ok", "id": trade_id}


@router.delete("/trades/{trade_id}")
async def agent_delete_trade(
    trade_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a stock transaction."""
    result = await db.execute(
        select(StockTransaction).where(and_(StockTransaction.id == trade_id, StockTransaction.user_id == user.id))
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Trade not found")
    await db.delete(txn)
    await db.commit()
    return {"status": "deleted", "id": trade_id}


# ── File Import ──────────────────────────────────────────────────

@router.post("/import")
async def agent_import_file(
    file: UploadFile = File(...),
    use_ai: bool = Form(default=True),
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Import a bank statement file (camt.053 XML, Valiant CSV, Viseca CSV/TSV).
    Same as /api/import/csv but with API key auth for agent use."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xml", "tsv"):
        raise HTTPException(status_code=400, detail="File must be .csv, .tsv, or .xml")

    raw = await file.read()
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252"):
        try:
            content = raw.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise HTTPException(status_code=400, detail="Could not decode file")

    from app.services.csv_import import detect_format, import_transactions
    from app.services.seed_merchants import seed_merchants

    fmt = detect_format(content)
    is_credit_card = fmt == "viseca"

    acct_type = "credit_card" if is_credit_card else "bank"
    acct_name = "Viseca Credit Card" if is_credit_card else "Valiant Bank"
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user.id, Account.type == acct_type))
    )
    account = result.scalar_one_or_none()
    if not account:
        account = Account(user_id=user.id, name=acct_name, type=acct_type, currency="CHF")
        db.add(account)
        await db.flush()

    await seed_merchants(db, user.id)
    result = await import_transactions(db, user.id, account.id, content, use_ai=use_ai)
    return result


# ── Gmail Poll ───────────────────────────────────────────────────

@router.post("/gmail/poll")
async def agent_poll_gmail(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Poll Gmail for bank notifications."""
    from app.services.gmail_poller import poll_gmail
    return await poll_gmail(db, user.id)


# ── Goals & Budget Targets ───────────────────────────────────────

class GoalCreate(BaseModel):
    name: str
    type: str  # monthly_limit | monthly_target | savings_goal
    amount: float
    category: str | None = None  # category name for monthly_limit/target
    currency: str = "CHF"
    target_date: str | None = None  # ISO date for savings_goal


@router.post("/goals")
async def create_goal(
    body: GoalCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a financial goal.

    Types:
    - monthly_limit: spending cap (e.g. Food: 750 CHF). Alert when exceeded.
    - monthly_target: amount to reach monthly (e.g. invest 1500 CHF/month)
    - savings_goal: long-term milestone with optional target date
    """
    if body.type not in ("monthly_limit", "monthly_target", "savings_goal"):
        raise HTTPException(status_code=400, detail="type must be: monthly_limit, monthly_target, savings_goal")

    if body.type in ("monthly_limit", "monthly_target"):
        # Use Budget table
        category_id = None
        if body.category:
            cat_result = await db.execute(
                select(Category).where(and_(Category.user_id == user.id, Category.name == body.category))
            )
            cat = cat_result.scalar_one_or_none()
            if cat:
                category_id = cat.id

        budget = Budget(
            user_id=user.id, name=body.name, amount=body.amount,
            period="monthly", category_id=category_id,
            start_date=date.today().replace(day=1),
        )
        db.add(budget)
        await db.commit()
        return {"status": "ok", "id": budget.id, "type": body.type, "name": body.name}

    else:  # savings_goal
        target_dt = date.fromisoformat(body.target_date) if body.target_date else None
        goal = SavingsGoal(
            user_id=user.id, name=body.name,
            target_amount=body.amount, current_amount=0,
            target_date=target_dt, currency=body.currency,
        )
        db.add(goal)
        await db.commit()
        return {"status": "ok", "id": goal.id, "type": body.type, "name": body.name}


@router.get("/goals")
async def list_goals(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List all goals (budgets + savings goals)."""
    # Budgets
    budget_result = await db.execute(select(Budget, Category).outerjoin(Category, Budget.category_id == Category.id).where(Budget.user_id == user.id))
    goals = []
    for b, cat in budget_result.all():
        goals.append({
            "id": b.id, "name": b.name,
            "type": "monthly_limit",  # All budgets treated as limits
            "amount": b.amount, "category": cat.name if cat else None,
            "currency": "CHF", "target_date": None,
        })

    # Savings goals
    sg_result = await db.execute(select(SavingsGoal).where(SavingsGoal.user_id == user.id))
    for g in sg_result.scalars().all():
        goals.append({
            "id": g.id, "name": g.name,
            "type": "savings_goal",
            "amount": g.target_amount, "category": None,
            "currency": g.currency,
            "target_date": g.target_date.isoformat() if g.target_date else None,
        })

    return goals


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a goal (budget or savings goal)."""
    # Try budget first
    result = await db.execute(select(Budget).where(and_(Budget.id == goal_id, Budget.user_id == user.id)))
    budget = result.scalar_one_or_none()
    if budget:
        await db.delete(budget)
        await db.commit()
        return {"status": "ok", "deleted": budget.name}

    # Try savings goal
    result = await db.execute(select(SavingsGoal).where(and_(SavingsGoal.id == goal_id, SavingsGoal.user_id == user.id)))
    goal = result.scalar_one_or_none()
    if goal:
        await db.delete(goal)
        await db.commit()
        return {"status": "ok", "deleted": goal.name}

    raise HTTPException(status_code=404, detail="Goal not found")


@router.get("/goals/progress")
async def goals_progress(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Current month progress for all goals."""
    today = date.today()
    month_start = today.replace(day=1)
    days_in_month = (month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(days=1)).day if month_start.month < 12 else 31
    days_elapsed = (today - month_start).days + 1
    pct_month_elapsed = days_elapsed / days_in_month * 100

    progress = []

    # Budget goals (monthly_limit)
    budget_result = await db.execute(
        select(Budget, Category).outerjoin(Category, Budget.category_id == Category.id)
        .where(Budget.user_id == user.id)
    )
    for b, cat in budget_result.all():
        # Calculate actual spending for this budget's category
        conditions = [
            Transaction.user_id == user.id,
            Transaction.date >= month_start,
            Transaction.amount < 0,
        ]
        if b.category_id:
            conditions.append(Transaction.category_id == b.category_id)

        spent_result = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(and_(*conditions))
        )
        actual = float(spent_result.scalar())
        remaining = max(b.amount - actual, 0)
        pct_used = (actual / b.amount * 100) if b.amount else 0

        # Status logic
        if actual > b.amount:
            status = "exceeded"
        elif pct_used > 80 and pct_month_elapsed < 70:
            status = "at_risk"
        else:
            status = "on_track"

        progress.append({
            "goal_id": b.id, "name": b.name, "type": "monthly_limit",
            "target": b.amount, "actual": actual, "remaining": remaining,
            "pct_used": round(pct_used, 1), "status": status,
            "category": cat.name if cat else None,
        })

    # Savings goals
    sg_result = await db.execute(select(SavingsGoal).where(SavingsGoal.user_id == user.id))

    # Get total portfolio + cash for savings goal progress
    pos_result = await db.execute(select(StockPosition).where(StockPosition.user_id == user.id))
    positions = pos_result.scalars().all()
    portfolio_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in positions if p.symbol != "CASH")
    cash_in_portfolio = sum(p.quantity for p in positions if p.symbol == "CASH")

    # Bank balance
    acct_result = await db.execute(select(Account).where(and_(Account.user_id == user.id, Account.type == "bank")))
    bank_balance = 0
    for acct in acct_result.scalars().all():
        bal_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(and_(
                Transaction.user_id == user.id, Transaction.account_id == acct.id,
            ))
        )
        bank_balance += float(bal_result.scalar())

    total_wealth = portfolio_value + cash_in_portfolio + bank_balance

    for g in sg_result.scalars().all():
        pct_used = (total_wealth / g.target_amount * 100) if g.target_amount else 0
        remaining = max(g.target_amount - total_wealth, 0)

        if total_wealth >= g.target_amount:
            status = "achieved"
        elif g.target_date and g.target_date < today:
            status = "overdue"
        else:
            status = "in_progress"

        progress.append({
            "goal_id": g.id, "name": g.name, "type": "savings_goal",
            "target": g.target_amount, "actual": total_wealth, "remaining": remaining,
            "pct_used": round(pct_used, 1), "status": status,
            "target_date": g.target_date.isoformat() if g.target_date else None,
        })

    return progress


# ── Milestones ───────────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    name: str
    description: str | None = None
    target_date: str | None = None  # ISO date
    target_net_worth: float | None = None
    target_savings: float | None = None


@router.post("/milestones")
async def create_milestone(
    body: MilestoneCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a milestone (life event / financial target).

    Examples:
    - "Emergency fund: 10k CHF" (target_savings=10000)
    - "Buy a car by 2027" (target_date=2027-01-01, target_savings=25000)
    - "Net worth 100k" (target_net_worth=100000)
    """
    target_dt = date.fromisoformat(body.target_date) if body.target_date else None
    m = Milestone(
        user_id=user.id, name=body.name,
        description=body.description, target_date=target_dt,
        target_net_worth=body.target_net_worth,
        target_savings=body.target_savings,
    )
    db.add(m)
    await db.commit()
    return {"status": "ok", "id": m.id, "name": m.name}


@router.get("/milestones")
async def list_milestones(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List all milestones with achievement status."""
    result = await db.execute(
        select(Milestone).where(Milestone.user_id == user.id)
        .order_by(Milestone.target_date.nulls_last(), Milestone.name)
    )
    return [
        {
            "id": m.id, "name": m.name, "description": m.description,
            "target_date": m.target_date.isoformat() if m.target_date else None,
            "target_net_worth": m.target_net_worth,
            "target_savings": m.target_savings,
            "achieved": m.achieved,
            "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
        }
        for m in result.scalars().all()
    ]


@router.patch("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: str,
    achieved: bool | None = None,
    description: str | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a milestone. Set achieved=true to mark as completed."""
    result = await db.execute(
        select(Milestone).where(and_(Milestone.id == milestone_id, Milestone.user_id == user.id))
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")

    if achieved is not None:
        m.achieved = achieved
        if achieved and not m.achieved_at:
            m.achieved_at = datetime.now(timezone.utc)
        elif not achieved:
            m.achieved_at = None
    if description is not None:
        m.description = description

    await db.commit()
    return {"status": "ok", "name": m.name, "achieved": m.achieved}


@router.delete("/milestones/{milestone_id}")
async def delete_milestone(
    milestone_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a milestone."""
    result = await db.execute(
        select(Milestone).where(and_(Milestone.id == milestone_id, Milestone.user_id == user.id))
    )
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Milestone not found")
    await db.delete(m)
    await db.commit()
    return {"status": "ok", "deleted": m.name}



# ── Currency Resync ──────────────────────────────────────────────

@router.post("/portfolio/resync-currencies")
async def resync_currencies(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Resync position currencies from yfinance.

    For each stock position:
    - Fetches the yfinance quote (which already returns normalized major currency).
    - If the DB currency differs, updates it.
    - Flags positions where the cost basis looks unrealistic for the yfinance price
      (ratio > 5x or < 0.2x), suggesting a possible ticker mismatch (e.g. SHEL
      instead of SHEL.L).

    Returns:
        updated:   [{symbol, old_ccy, new_ccy}]
        unchanged: [symbols]
        flagged:   [{symbol, reason}]
    """
    from app.services.prices import get_quote
    from app.services.currency import normalize_currency

    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()
    stock_positions = [p for p in positions if p.symbol != "CASH"]

    updated = []
    unchanged = []
    flagged = []

    for pos in stock_positions:
        quote = await get_quote(pos.symbol)
        if not quote:
            flagged.append({
                "symbol": pos.symbol,
                "reason": "yfinance returned no data — symbol may be invalid or delisted",
            })
            continue

        yf_ccy = quote["currency"]  # already normalized by get_quote
        db_ccy, _ = normalize_currency(pos.currency)  # normalize DB value too

        if db_ccy != yf_ccy:
            updated.append({
                "symbol": pos.symbol,
                "old_ccy": pos.currency,
                "new_ccy": yf_ccy,
            })
            pos.currency = yf_ccy
        else:
            unchanged.append(pos.symbol)

        # Flag possible ticker mismatch: price ratio out of expected range
        yf_price = quote["price"]
        db_cost = pos.avg_cost_price
        if db_cost and db_cost > 0 and yf_price and yf_price > 0:
            ratio = yf_price / db_cost
            if ratio > 5.0:
                flagged.append({
                    "symbol": pos.symbol,
                    "reason": (
                        f"yfinance price {yf_price:.4f} {yf_ccy} is {ratio:.1f}x higher than "
                        f"avg cost {db_cost:.4f} {pos.currency} — possible wrong ticker "
                        f"(e.g. should be {pos.symbol}.L for LSE?)"
                    ),
                })
            elif ratio < 0.2:
                flagged.append({
                    "symbol": pos.symbol,
                    "reason": (
                        f"yfinance price {yf_price:.4f} {yf_ccy} is {1/ratio:.1f}x lower than "
                        f"avg cost {db_cost:.4f} {pos.currency} — possible wrong ticker or stale cost basis"
                    ),
                })

    if updated:
        await db.commit()

    return {
        "updated": updated,
        "unchanged": unchanged,
        "flagged": flagged,
    }

