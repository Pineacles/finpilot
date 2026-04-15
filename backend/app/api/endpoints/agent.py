"""Agent endpoints — API key auth for AI assistant integration.

All endpoints use X-API-Key header authentication.
The agent can do everything a user can do through these endpoints.
"""
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
from app.models.stock import StockPosition, StockTransaction, PostMortem, BuyAssessment
from app.models.user import User
from app.schemas.finance import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ── Financial Summaries ──────────────────────────────────────────

@router.get("/summary/financial")
async def financial_summary(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Monthly financial overview: spending, income, budgets, upcoming bills."""
    today = date.today()
    month_start = today.replace(day=1)

    result = await db.execute(
        select(
            func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0).label("income"),
            func.coalesce(func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)), 0).label("expenses"),
            func.count(Transaction.id).label("txn_count"),
        ).where(and_(Transaction.user_id == user.id, Transaction.date >= month_start))
    )
    row = result.one()
    income, expenses, txn_count = float(row.income), float(row.expenses), int(row.txn_count)

    # Category breakdown
    cat_result = await db.execute(
        select(Category.name, func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(and_(Transaction.user_id == user.id, Transaction.date >= month_start, Transaction.amount < 0))
        .group_by(Category.name)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    )
    categories = [{"name": r.name or "Uncategorized", "total": float(r.total)} for r in cat_result.all()]

    # Budget status
    result = await db.execute(select(Budget).where(Budget.user_id == user.id))
    budgets = []
    for b in result.scalars().all():
        spent_result = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(and_(
                Transaction.user_id == user.id, Transaction.date >= month_start,
                Transaction.amount < 0,
                Transaction.category_id == b.category_id if b.category_id else True,
            ))
        )
        spent = float(spent_result.scalar())
        budgets.append({"name": b.name, "limit": b.amount, "spent": spent, "pct": (spent / b.amount * 100) if b.amount else 0})

    # Upcoming bills
    result = await db.execute(
        select(RecurringExpense).where(and_(
            RecurringExpense.user_id == user.id, RecurringExpense.active == True,
            RecurringExpense.next_due_date <= today + timedelta(days=14),
        ))
    )
    upcoming = [{"name": r.name, "amount": r.amount, "due": r.next_due_date.isoformat()} for r in result.scalars().all()]

    # Account balances
    acct_result = await db.execute(select(Account).where(Account.user_id == user.id))
    account_balances = []
    for acct in acct_result.scalars().all():
        bal_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(and_(
                Transaction.user_id == user.id, Transaction.account_id == acct.id,
            ))
        )
        balance = float(bal_result.scalar())
        account_balances.append({"name": acct.name, "type": acct.type, "balance": balance})

    return {
        "month": month_start.isoformat(),
        "income": income,
        "expenses": expenses,
        "net": income - expenses,
        "txn_count": txn_count,
        "categories": categories,
        "budgets": budgets,
        "upcoming_bills": upcoming,
        "accounts": account_balances,
    }


@router.get("/summary/portfolio")
async def portfolio_summary(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Portfolio overview with positions."""
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()

    stock_positions = [p for p in positions if p.symbol != "CASH"]
    cash_pos = next((p for p in positions if p.symbol == "CASH"), None)

    total_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in stock_positions)
    total_cost = sum(p.avg_cost_price * p.quantity for p in stock_positions)
    total_pnl = total_value - total_cost

    return {
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_cost * 100) if total_cost else 0,
        "cash_balance": cash_pos.quantity if cash_pos else 0,
        "positions_count": len(stock_positions),
        "positions": [
            {
                "symbol": p.symbol,
                "name": p.name,
                "quantity": p.quantity,
                "avg_cost": p.avg_cost_price,
                "last_price": p.last_price,
                "pnl": p.unrealized_pnl or 0,
                "value": (p.last_price or p.avg_cost_price) * p.quantity,
            }
            for p in stock_positions
        ],
    }


# ── Stats ────────────────────────────────────────────────────────

@router.get("/stats/monthly")
async def agent_monthly_stats(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Monthly stats — same as dashboard endpoint but with API key auth."""
    from app.api.endpoints.stats import monthly_stats
    # Inject user into the request
    return await monthly_stats(year=year, month=month, user=user, db=db)


@router.get("/stats/yearly")
async def agent_yearly_stats(
    year: int | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Yearly stats — same as dashboard endpoint but with API key auth."""
    from app.api.endpoints.stats import yearly_stats
    return await yearly_stats(year=year, user=user, db=db)


# ── Transactions ─────────────────────────────────────────────────

@router.get("/transactions")
async def agent_list_transactions(
    category: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List transactions with filtering."""
    query = (
        select(Transaction, Category)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == user.id)
    )
    if category:
        query = query.where(Category.name == category)
    if from_date:
        query = query.where(Transaction.date >= date.fromisoformat(from_date))
    if to_date:
        query = query.where(Transaction.date <= date.fromisoformat(to_date))
    if search:
        query = query.where(Transaction.merchant.ilike(f"%{search}%"))

    query = query.order_by(desc(Transaction.date)).limit(limit)
    result = await db.execute(query)

    return [
        {
            "id": txn.id, "date": txn.date.isoformat(), "merchant": txn.merchant,
            "amount": txn.amount, "currency": txn.currency,
            "category": cat.name if cat else None, "notes": txn.notes,
        }
        for txn, cat in result.all()
    ]


@router.post("/transaction")
async def log_transaction(
    body: TransactionCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a transaction."""
    txn = Transaction(user_id=user.id, **body.model_dump())
    db.add(txn)
    await db.commit()
    return {"status": "ok", "id": txn.id}


# ── Categorization ───────────────────────────────────────────────


async def _upsert_merchant_rule(
    db: AsyncSession, merchant_name: str, original_name: str | None, category_id: str,
):
    """Create or update a Merchant DB entry so future imports auto-categorize.

    Builds patterns from both the new merchant name and the original name.
    """
    # Build patterns: lowercase, pipe-separated, deduplicated
    patterns_set: set[str] = set()
    for name in (merchant_name, original_name):
        if name:
            cleaned = name.strip().lower()
            if cleaned:
                patterns_set.add(cleaned)
                # Also add significant words (3+ chars) as individual patterns
                for word in cleaned.split():
                    if len(word) >= 4 and word not in ("gmbh", "sarl", "bank", "card", "payment", "services"):
                        patterns_set.add(word)

    if not patterns_set:
        return

    # Check if a merchant with this name already exists
    result = await db.execute(
        select(Merchant).where(Merchant.name == merchant_name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Merge new patterns into existing
        old_patterns = set(p.strip().lower() for p in existing.patterns.split("|") if p.strip())
        merged = old_patterns | patterns_set
        existing.patterns = "|".join(sorted(merged))
        existing.default_category_id = category_id
    else:
        db.add(Merchant(
            name=merchant_name,
            patterns="|".join(sorted(patterns_set)),
            default_category_id=category_id,
            is_system=False,
        ))


@router.post("/categorize")
async def agent_categorize(
    category_name: str,
    transaction_id: str | None = None,
    merchant: str | None = None,
    description_contains: str | None = None,
    new_merchant: str | None = None,
    apply_to_all: bool = True,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Categorize transactions by category name.

    Two modes:
    1. By transaction_id: categorize one transaction (+ all with same merchant if apply_to_all)
    2. By merchant + optional description_contains: batch categorize by pattern

    Optional new_merchant: rename matching transactions' merchant field too.

    Examples:
      ?transaction_id=uuid&category_name=Supermarket
      ?merchant=Swisscom&description_contains=Swisscharge&category_name=Fuel&new_merchant=Swisscharge
      ?merchant=Pending&category_name=Other (categorize all "Pending" from email notifications)
    """
    # Find category
    cat_result = await db.execute(
        select(Category).where(and_(Category.user_id == user.id, Category.name == category_name))
    )
    cat = cat_result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category '{category_name}' not found")

    updated = 0
    renamed = 0
    matched_merchant = merchant

    if transaction_id:
        # Mode 1: by transaction ID
        txn_result = await db.execute(
            select(Transaction).where(and_(Transaction.id == transaction_id, Transaction.user_id == user.id))
        )
        txn = txn_result.scalar_one_or_none()
        if not txn:
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Capture original merchant BEFORE rename for apply_to_all query
        original_merchant = txn.merchant

        txn.category_id = cat.id
        if new_merchant:
            txn.merchant = new_merchant
            renamed += 1
        updated = 1
        matched_merchant = original_merchant

        if apply_to_all and original_merchant:
            conditions = [
                Transaction.user_id == user.id,
                Transaction.merchant == original_merchant,
                Transaction.id != txn.id,
            ]
            if description_contains:
                conditions.append(Transaction.notes.ilike(f"%{description_contains}%"))

            others = await db.execute(select(Transaction).where(and_(*conditions)))
            for other in others.scalars().all():
                other.category_id = cat.id
                updated += 1
                if new_merchant:
                    other.merchant = new_merchant
                    renamed += 1

    elif merchant:
        # Mode 2: by merchant name + optional description filter
        conditions = [
            Transaction.user_id == user.id,
            Transaction.merchant == merchant,
        ]
        if description_contains:
            conditions.append(Transaction.notes.ilike(f"%{description_contains}%"))

        result = await db.execute(select(Transaction).where(and_(*conditions)))
        for txn in result.scalars().all():
            txn.category_id = cat.id
            updated += 1
            if new_merchant:
                txn.merchant = new_merchant
                renamed += 1
    else:
        raise HTTPException(status_code=400, detail="Provide transaction_id or merchant")

    # Upsert Merchant DB rule so future imports auto-categorize correctly
    final_merchant_name = new_merchant or matched_merchant or merchant
    if final_merchant_name and final_merchant_name != "Pending":
        await _upsert_merchant_rule(db, final_merchant_name, matched_merchant or merchant, cat.id)

    await db.commit()

    response = {"status": "ok", "updated": updated, "category": category_name}
    if merchant:
        response["merchant"] = merchant
    if description_contains:
        response["description_filter"] = description_contains
    if new_merchant:
        response["renamed_to"] = new_merchant
        response["renamed"] = renamed
    return response


@router.get("/categories")
async def agent_list_categories(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List all categories with hierarchy."""
    result = await db.execute(
        select(Category).where(Category.user_id == user.id).order_by(Category.name)
    )
    cats = result.scalars().all()
    parent_map = {c.id: c.name for c in cats}

    return [
        {
            "id": c.id, "name": c.name, "type": c.type,
            "parent": parent_map.get(c.parent_id) if c.parent_id else None,
        }
        for c in cats
    ]


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


# ── Analysis ─────────────────────────────────────────────────────

class StockAnalysis(BaseModel):
    symbol: str
    action: str  # HOLD | SELL | ADD
    current_price: float = 0
    entry_price: float = 0
    unrealized_pnl_pct: float = 0
    rationale: str = ""
    key_risks: list[str] = []
    key_catalysts: list[str] = []


class AnalysisCreate(BaseModel):
    analysis_type: str = "portfolio"  # portfolio | economy
    market_summary: str
    market_sentiment: str  # bullish | bearish | neutral
    stocks: list[StockAnalysis] = []
    # Economy-specific fields
    key_indicators: list[dict] | None = None  # [{"name": "GDP", "value": "2.1%", "trend": "up"}]
    outlook: str | None = None
    risks: list[str] | None = None
    opportunities: list[str] | None = None
    analyzed_at: str | None = None


@router.post("/analysis")
async def store_analysis(
    body: AnalysisCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Store an analysis.

    analysis_type: "portfolio" (per-stock actions) or "economy" (macro outlook)
    """
    from app.models.stock import MarketAnalysis

    if body.analysis_type not in ("portfolio", "economy"):
        raise HTTPException(status_code=400, detail="analysis_type must be: portfolio, economy")

    content = {
        "market_summary": body.market_summary,
        "market_sentiment": body.market_sentiment,
        "analyzed_at": body.analyzed_at or datetime.now(timezone.utc).isoformat(),
    }

    if body.analysis_type == "portfolio":
        content["stocks"] = [s.model_dump() for s in body.stocks]
    else:
        content["key_indicators"] = body.key_indicators or []
        content["outlook"] = body.outlook or ""
        content["risks"] = body.risks or []
        content["opportunities"] = body.opportunities or []

    analysis = MarketAnalysis(
        user_id=user.id,
        analysis_type=body.analysis_type,
        content=content,
        model_used="agent",
    )
    db.add(analysis)
    await db.commit()

    return {"status": "ok", "id": analysis.id, "type": body.analysis_type}


@router.get("/analysis/latest")
async def get_latest_analysis(
    analysis_type: str | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent analysis. Optional filter by type (portfolio|economy)."""
    from app.models.stock import MarketAnalysis

    query = select(MarketAnalysis).where(MarketAnalysis.user_id == user.id)
    if analysis_type:
        query = query.where(MarketAnalysis.analysis_type == analysis_type)
    query = query.order_by(desc(MarketAnalysis.created_at)).limit(1)

    result = await db.execute(query)
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"status": "none", "message": "No analysis stored yet."}

    return {
        "id": analysis.id,
        "analysis_type": analysis.analysis_type,
        "content": analysis.content,
        "created_at": analysis.created_at.isoformat(),
    }


@router.get("/analysis")
async def list_analyses(
    analysis_type: str | None = None,
    limit: int = 10,
    offset: int = 0,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List analysis history. Optional filter by type (portfolio|economy)."""
    from app.models.stock import MarketAnalysis

    query = select(MarketAnalysis).where(MarketAnalysis.user_id == user.id)
    if analysis_type:
        query = query.where(MarketAnalysis.analysis_type == analysis_type)
    query = query.order_by(desc(MarketAnalysis.created_at)).limit(limit).offset(offset)

    result = await db.execute(query)
    return [
        {
            "id": a.id,
            "analysis_type": a.analysis_type,
            "market_sentiment": a.content.get("market_sentiment") if isinstance(a.content, dict) else None,
            "stocks_count": len(a.content.get("stocks", [])) if isinstance(a.content, dict) else 0,
            "created_at": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ]


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


# ── Journal: Post-Mortems (agent) ────────────────────────────────

def _pm_to_dict(pm: PostMortem) -> dict:
    return {
        "id": pm.id,
        "user_id": pm.user_id,
        "symbol": pm.symbol,
        "analysis_id": pm.analysis_id,
        "entry_price": pm.entry_price,
        "exit_price": pm.exit_price,
        "pnl_pct": pm.pnl_pct,
        "notes": pm.notes,
        "created_at": pm.created_at.isoformat(),
    }


def _ba_to_dict(ba: BuyAssessment) -> dict:
    return {
        "id": ba.id,
        "user_id": ba.user_id,
        "symbol": ba.symbol,
        "recommendation": ba.recommendation,
        "target_price": ba.target_price,
        "stop_loss": ba.stop_loss,
        "thesis": ba.thesis,
        "risk_factors": ba.risk_factors,
        "conviction": ba.conviction,
        "time_horizon": ba.time_horizon,
        "assessed_at": ba.assessed_at.isoformat(),
        "created_at": ba.created_at.isoformat(),
        "updated_at": ba.updated_at.isoformat(),
    }


class AgentPostMortemCreate(BaseModel):
    symbol: str
    entry_price: float
    exit_price: float
    notes: str | None = None
    analysis_id: str | None = None


class AgentPostMortemUpdate(BaseModel):
    entry_price: float | None = None
    exit_price: float | None = None
    notes: str | None = None


class AgentBuyAssessmentCreate(BaseModel):
    symbol: str
    recommendation: str
    target_price: float | None = None
    stop_loss: float | None = None
    thesis: str
    risk_factors: str | None = None
    conviction: int
    time_horizon: str | None = None
    assessed_at: datetime | None = None


class AgentBuyAssessmentUpdate(BaseModel):
    recommendation: str | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    thesis: str | None = None
    risk_factors: str | None = None
    conviction: int | None = None
    time_horizon: str | None = None
    assessed_at: datetime | None = None


_VALID_RECS = {"buy", "hold", "watch", "avoid"}
_VALID_HORIZONS = {"short", "medium", "long", None}


@router.get("/post-mortems")
async def agent_list_post_mortems(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    q = select(PostMortem).where(PostMortem.user_id == user.id)
    if symbol:
        q = q.where(PostMortem.symbol == symbol.upper())
    q = q.order_by(desc(PostMortem.created_at)).limit(limit)
    result = await db.execute(q)
    return [_pm_to_dict(pm) for pm in result.scalars().all()]


@router.post("/post-mortems", status_code=201)
async def agent_create_post_mortem(
    body: AgentPostMortemCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    pnl_pct = (body.exit_price - body.entry_price) / body.entry_price * 100
    pm = PostMortem(
        user_id=user.id,
        symbol=body.symbol.upper(),
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        pnl_pct=pnl_pct,
        notes=body.notes,
        analysis_id=body.analysis_id,
    )
    db.add(pm)
    await db.commit()
    await db.refresh(pm)
    return _pm_to_dict(pm)


@router.patch("/post-mortems/{pm_id}")
async def agent_update_post_mortem(
    pm_id: str,
    body: AgentPostMortemUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PostMortem).where(and_(PostMortem.id == pm_id, PostMortem.user_id == user.id))
    )
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    if body.notes is not None:
        pm.notes = body.notes
    if body.entry_price is not None:
        pm.entry_price = body.entry_price
    if body.exit_price is not None:
        pm.exit_price = body.exit_price
    if body.entry_price is not None or body.exit_price is not None:
        pm.pnl_pct = (pm.exit_price - pm.entry_price) / pm.entry_price * 100
    await db.commit()
    await db.refresh(pm)
    return _pm_to_dict(pm)


@router.delete("/post-mortems/{pm_id}", status_code=204)
async def agent_delete_post_mortem(
    pm_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PostMortem).where(and_(PostMortem.id == pm_id, PostMortem.user_id == user.id))
    )
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    await db.delete(pm)
    await db.commit()


# ── Journal: Buy Assessments (agent) ─────────────────────────────

@router.get("/buy-assessments")
async def agent_list_buy_assessments(
    symbol: str | None = None,
    recommendation: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    q = select(BuyAssessment).where(BuyAssessment.user_id == user.id)
    if symbol:
        q = q.where(BuyAssessment.symbol == symbol.upper())
    if recommendation:
        q = q.where(BuyAssessment.recommendation == recommendation)
    q = q.order_by(desc(BuyAssessment.created_at)).limit(limit)
    result = await db.execute(q)
    return [_ba_to_dict(ba) for ba in result.scalars().all()]


@router.post("/buy-assessments", status_code=201)
async def agent_create_buy_assessment(
    body: AgentBuyAssessmentCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    if body.recommendation not in _VALID_RECS:
        raise HTTPException(status_code=422, detail=f"recommendation must be one of: {', '.join(_VALID_RECS)}")
    if body.time_horizon not in _VALID_HORIZONS:
        raise HTTPException(status_code=422, detail="time_horizon must be short, medium, or long")
    ba = BuyAssessment(
        user_id=user.id,
        symbol=body.symbol.upper(),
        recommendation=body.recommendation,
        target_price=body.target_price,
        stop_loss=body.stop_loss,
        thesis=body.thesis,
        risk_factors=body.risk_factors,
        conviction=body.conviction,
        time_horizon=body.time_horizon,
        assessed_at=body.assessed_at or datetime.now(timezone.utc),
    )
    db.add(ba)
    await db.commit()
    await db.refresh(ba)
    return _ba_to_dict(ba)


@router.patch("/buy-assessments/{ba_id}")
async def agent_update_buy_assessment(
    ba_id: str,
    body: AgentBuyAssessmentUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BuyAssessment).where(and_(BuyAssessment.id == ba_id, BuyAssessment.user_id == user.id))
    )
    ba = result.scalar_one_or_none()
    if not ba:
        raise HTTPException(status_code=404, detail="Buy assessment not found")
    if body.recommendation is not None:
        if body.recommendation not in _VALID_RECS:
            raise HTTPException(status_code=422, detail=f"recommendation must be one of: {', '.join(_VALID_RECS)}")
        ba.recommendation = body.recommendation
    if body.target_price is not None:
        ba.target_price = body.target_price
    if body.stop_loss is not None:
        ba.stop_loss = body.stop_loss
    if body.thesis is not None:
        ba.thesis = body.thesis
    if body.risk_factors is not None:
        ba.risk_factors = body.risk_factors
    if body.conviction is not None:
        ba.conviction = body.conviction
    if body.time_horizon is not None:
        if body.time_horizon not in {"short", "medium", "long"}:
            raise HTTPException(status_code=422, detail="time_horizon must be short, medium, or long")
        ba.time_horizon = body.time_horizon
    if body.assessed_at is not None:
        ba.assessed_at = body.assessed_at
    ba.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ba)
    return _ba_to_dict(ba)


@router.delete("/buy-assessments/{ba_id}", status_code=204)
async def agent_delete_buy_assessment(
    ba_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BuyAssessment).where(and_(BuyAssessment.id == ba_id, BuyAssessment.user_id == user.id))
    )
    ba = result.scalar_one_or_none()
    if not ba:
        raise HTTPException(status_code=404, detail="Buy assessment not found")
    await db.delete(ba)
    await db.commit()
