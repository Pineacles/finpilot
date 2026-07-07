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


