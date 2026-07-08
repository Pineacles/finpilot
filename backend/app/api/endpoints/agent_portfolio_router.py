"""Agent sub-router — API key auth for AI assistant integration."""
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Budget, Category, SavingsGoal, Milestone
from app.models.stock import StockPosition
from app.models.user import User
from app.schemas.import_profile import ColumnMappingSchema, CsvPreviewResponse, ImportProfileResponse
from app.schemas.portfolio import PortfolioResponse
from app.services import portfolio_service
from app.services.portfolio_service import (
    TradeNotFoundError,
    InsufficientCashError,
    InsufficientSharesError,
    InvalidTickerError,
    CurrencyMismatchError,
    FxRateUnavailableError,
    suggest_ticker_suffix,
)
from app.services import watchlist_service, import_profile_service, mapped_import
from app.services.watchlist_service import (
    WatchlistDuplicateError,
    WatchlistInvalidSymbolError,
    WatchlistItemNotFoundError,
)
from app.schemas.watchlist import WatchlistItemOut

router = APIRouter(tags=["agent"])


class WatchlistAddRequest(BaseModel):
    symbol: str


# ── Portfolio holdings (full parity with the dashboard) ───────────

@router.get("/portfolio", response_model=PortfolioResponse, summary="Portfolio holdings with live prices, asset type, and staleness/FX warnings")
async def agent_portfolio(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Full portfolio view — same computation as the dashboard's
    GET /api/dashboard/portfolio: live prices, CHF conversion, per-position
    asset_type (equity/etf/index/crypto/bond/commodity/cash), staleness
    flags, and a `warnings` list for any failed price/FX lookups (never
    silent — see PortfolioResponse.warnings).
    For a smaller human-readable digest, see GET /summary/portfolio."""
    return await portfolio_service.get_portfolio(db, user.id)


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
    confirm_currency: bool = False  # true = "yes, use the quote's currency" after a 422 currency_mismatch


@router.post("/trade")
@router.post("/trades")
async def agent_trade(
    body: AgentTradeRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Execute a portfolio trade. Same as dashboard but with API key auth."""
    try:
        return await portfolio_service.execute_trade(
            db, user.id,
            symbol=body.symbol, type=body.type, quantity=body.quantity,
            price=body.price, currency=body.currency, trade_date=body.date,
            fees=body.fees, deduct_from_cash=body.deduct_from_cash,
            confirm_currency=body.confirm_currency,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidTickerError as e:
        raise HTTPException(status_code=400, detail=f"Ticker {e.ticker} not found")
    except CurrencyMismatchError as e:
        suggested_ticker = suggest_ticker_suffix(e.ticker, e.quote_currency)
        message = (
            f"You entered {e.user_currency} for {e.ticker}, but its market quote is denominated "
            f"in {e.quote_currency}."
        )
        if suggested_ticker:
            message += f" If you meant the {e.quote_currency} listing, the ticker is usually '{suggested_ticker}'."
        message += f" Set confirm_currency=true to record this trade in {e.quote_currency} instead, or fix the ticker/currency."
        raise HTTPException(status_code=422, detail={
            "error": "currency_mismatch",
            "message": message,
            "ticker": e.ticker,
            "user_currency": e.user_currency,
            "quote_currency": e.quote_currency,
            "suggested_ticker": suggested_ticker,
        })
    except FxRateUnavailableError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Exchange rate for {e.from_ccy}→{e.to_ccy} is currently unavailable. Try again shortly.",
        )
    except InsufficientCashError as e:
        if e.needed is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient cash: {e.available:.2f} CHF, need {e.needed:.2f} CHF. Deposit cash first or disable deduct_from_cash."
            )
        raise HTTPException(status_code=400, detail=f"Insufficient cash: {e.available:.2f}")
    except InsufficientSharesError as e:
        raise HTTPException(status_code=400, detail=f"Insufficient shares: {e.available}")


@router.get("/trades")
async def agent_trades(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Trade history."""
    trades = await portfolio_service.list_stock_transactions(db, user.id, symbol=symbol, limit=limit)
    return [
        {
            "id": t.id, "symbol": t.symbol, "type": t.type, "quantity": t.quantity,
            "price": t.price, "fees": t.fees, "currency": t.currency, "date": t.executed_at.isoformat(),
        }
        for t in trades
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
    try:
        await portfolio_service.update_trade(db, user.id, trade_id, body.model_dump())
    except TradeNotFoundError:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"status": "ok", "id": trade_id}


@router.delete("/trades/{trade_id}")
async def agent_delete_trade(
    trade_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a stock transaction."""
    try:
        await portfolio_service.delete_trade(db, user.id, trade_id)
    except TradeNotFoundError:
        raise HTTPException(status_code=404, detail="Trade not found")
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


# ── Generic CSV column-mapper import ──────────────────────────────
# For formats detect_format() doesn't recognize (e.g. a Cumulus/Cembra card
# export) — preview the columns, then import with an explicit mapping.
# Same pipeline as /api/import/csv/preview + /api/import/csv/mapped
# (dashboard surface) via app.services.mapped_import.

@router.post("/import/preview", response_model=CsvPreviewResponse, summary="Preview an unrecognized CSV's columns for mapping")
async def agent_preview_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_user_by_api_key),
):
    """Sniff delimiter/encoding and return the header + first ~10 rows so a
    column mapping can be constructed for /import/mapped."""
    raw = await file.read()
    try:
        return mapped_import.preview_csv(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import/mapped", summary="Import a CSV using an explicit column mapping")
async def agent_import_mapped_csv(
    file: UploadFile = File(...),
    account_id: str = Form(...),
    mapping: str = Form(..., description="JSON-encoded ColumnMappingSchema"),
    use_ai: bool = Form(default=True),
    save_as_profile_name: str | None = Form(default=None),
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Import a CSV using a user-supplied column mapping — for any format
    detect_format() doesn't recognize (e.g. Cumulus/Cembra card exports).
    Optionally save the mapping as a reusable named profile."""
    try:
        mapping_dict = json.loads(mapping)
        column_mapping = ColumnMappingSchema(**mapping_dict)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid mapping: {e}")

    acct_result = await db.execute(
        select(Account).where(and_(Account.id == account_id, Account.user_id == user.id))
    )
    if not acct_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Account not found")

    raw = await file.read()
    try:
        internal_mapping = mapped_import.ColumnMapping(**column_mapping.model_dump())
        raw_transactions = mapped_import.parse_mapped_csv(raw, internal_mapping)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not raw_transactions:
        raise HTTPException(status_code=400, detail="No rows matched the given mapping")

    from app.services.csv_import import import_transactions
    from app.services.seed_merchants import seed_merchants

    await seed_merchants(db, user.id)
    result = await import_transactions(
        db, user.id, account_id, "",
        use_ai=use_ai, pre_parsed=raw_transactions, source_format="mapped_csv",
    )

    if save_as_profile_name:
        await import_profile_service.create_profile(
            db, user.id, save_as_profile_name, account_id, column_mapping.model_dump()
        )
        result["saved_profile"] = save_as_profile_name

    return result


@router.get("/import/profiles", response_model=list[ImportProfileResponse], summary="List saved CSV column-mapping profiles")
async def agent_list_import_profiles(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List saved column-mapping profiles (reusable per account for
    non-standard CSV imports)."""
    return await import_profile_service.list_profiles(db, user.id)


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



# ── Watchlist (tracking only — no analysis/recommendations) ──────

@router.get("/watchlist", response_model=list[WatchlistItemOut])
async def agent_watchlist(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Read the user's watchlist — live price + day change per symbol.
    Tracking only; this deliberately does not return any analysis or buy/sell
    recommendations (that stack was removed — see redesign decisions)."""
    return await watchlist_service.list_watchlist(db, user.id)


@router.post("/watchlist", response_model=WatchlistItemOut, summary="Add a symbol to the watchlist")
async def agent_add_to_watchlist(
    body: WatchlistAddRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Add a symbol to the watchlist (tracking only — no recommendations)."""
    try:
        return await watchlist_service.add_watchlist_item(db, user.id, body.symbol)
    except WatchlistDuplicateError as e:
        raise HTTPException(status_code=409, detail=f"{e.symbol} is already on your watchlist")
    except WatchlistInvalidSymbolError as e:
        raise HTTPException(status_code=400, detail=f"No live quote found for {e.symbol} — check the ticker")


@router.delete("/watchlist/{symbol}", summary="Remove a symbol from the watchlist")
async def agent_remove_from_watchlist(
    symbol: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Remove a symbol from the watchlist."""
    try:
        await watchlist_service.remove_watchlist_item(db, user.id, symbol)
    except WatchlistItemNotFoundError:
        raise HTTPException(status_code=404, detail=f"{symbol} is not on your watchlist")
    return {"status": "ok"}


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

