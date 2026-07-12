"""Agent sub-router: API key auth for AI assistant integration."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Budget, Category, RecurringExpense
from app.models.stock import StockPosition
from app.models.user import User
from app.schemas.dashboard import (
    AccountOut, SetBalanceRequest, SetBalanceResponse,
    CreditCardAccountResponse, SettlementPatternsRequest,
)
from app.schemas.finance import (
    TransactionCreate, TransactionResponse, TransactionUpdate,
    BudgetCreate, BudgetResponse,
    RecurringExpenseCreate, RecurringExpenseResponse, RecurringExpenseUpdate,
    RecurringSuggestionResponse,
)
from app.schemas.merchants import MerchantCreate, MerchantResponse, MerchantUpdate
from app.schemas.stats import MonthlyStatsResponse, YearlyStatsResponse
from app.services import (
    account_service, budget_service, merchant_service,
    transaction_service, stats_service, recurring_detection, recurring_service,
)
from app.services.stats_service import exclude_transfer_category, get_transfer_category_ids
from app.services.account_service import AccountNotFoundError
from app.services.budget_service import BudgetNotFoundError
from app.services.merchant_service import MerchantNotFoundError
from app.services.transaction_service import TransactionNotFoundError
from app.services.recurring_service import RecurringNotFoundError

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

    # Transfer-categorized rows (Viseca/Cembra settlements etc.) are internal
    # money movement, not real income/expense: exclude them from every
    # aggregate below, same as the dashboard stats (stats_service). Account
    # balances further down deliberately keep transfers, since a transfer
    # really does move money in or out of that account.
    transfer_cat_ids = await get_transfer_category_ids(db, user.id)

    conditions = [Transaction.user_id == user.id, Transaction.date >= month_start]
    if transfer_cat_ids:
        conditions.append(exclude_transfer_category(transfer_cat_ids))

    result = await db.execute(
        select(
            func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)), 0).label("income"),
            func.coalesce(func.sum(case((Transaction.amount < 0, func.abs(Transaction.amount)), else_=0)), 0).label("expenses"),
            func.count(Transaction.id).label("txn_count"),
        ).where(and_(*conditions))
    )
    row = result.one()
    income, expenses, txn_count = float(row.income), float(row.expenses), int(row.txn_count)

    # Category breakdown
    cat_result = await db.execute(
        select(Category.name, func.coalesce(func.sum(func.abs(Transaction.amount)), 0).label("total"))
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(and_(
            Transaction.user_id == user.id, Transaction.date >= month_start, Transaction.amount < 0,
            exclude_transfer_category(transfer_cat_ids) if transfer_cat_ids else True,
        ))
        .group_by(Category.name)
        .order_by(func.sum(func.abs(Transaction.amount)).desc())
        .limit(10)
    )
    categories = [{"name": r.name or "Uncategorized", "total": float(r.total)} for r in cat_result.all()]

    # Budget status. A budget with category_id=None means "all spending":
    # keep that semantic but still drop Transfer rows from it.
    result = await db.execute(select(Budget).where(Budget.user_id == user.id))
    budgets = []
    for b in result.scalars().all():
        spent_conditions = [
            Transaction.user_id == user.id, Transaction.date >= month_start,
            Transaction.amount < 0,
        ]
        if b.category_id:
            spent_conditions.append(Transaction.category_id == b.category_id)
        elif transfer_cat_ids:
            spent_conditions.append(exclude_transfer_category(transfer_cat_ids))
        spent_result = await db.execute(
            select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(and_(*spent_conditions))
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

@router.get("/stats/monthly", response_model=MonthlyStatsResponse)
async def agent_monthly_stats(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Monthly stats, same as dashboard endpoint but with API key auth."""
    return await stats_service.monthly_stats(db, user.id, year=year, month=month)


@router.get("/stats/yearly", response_model=YearlyStatsResponse)
async def agent_yearly_stats(
    year: int | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Yearly stats, same as dashboard endpoint but with API key auth."""
    return await stats_service.yearly_stats(db, user.id, year=year)


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
    txns = await transaction_service.list_transactions(
        db, user.id,
        category_name=category,
        from_date=date.fromisoformat(from_date) if from_date else None,
        to_date=date.fromisoformat(to_date) if to_date else None,
        search=search, limit=limit,
    )
    return [
        {
            "id": t.id, "date": t.date.isoformat(), "merchant": t.merchant,
            "amount": t.amount, "currency": t.currency,
            "category": t.category_name, "notes": t.notes,
        }
        for t in txns
    ]


@router.post("/transaction")
@router.post("/transactions")
async def log_transaction(
    body: TransactionCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a transaction."""
    txn = await transaction_service.create_transaction(db, user.id, body)
    return {"status": "ok", "id": txn.id}


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse, summary="Update a transaction (with optional bulk-apply)")
async def agent_update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a transaction's merchant/category/notes. By default the
    merchant rename and category change also apply to all other transactions
    with the same merchant (apply_merchant_to_all / apply_category_to_all,
    optionally narrowed by description_filter): the primary "fix a data
    mistake everywhere at once" tool. Same behavior as the dashboard PATCH."""
    try:
        return await transaction_service.update_transaction(db, user.id, transaction_id, body)
    except TransactionNotFoundError:
        raise HTTPException(status_code=404, detail="Transaction not found")


@router.delete("/transactions/{transaction_id}")
async def agent_delete_transaction(
    transaction_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a transaction."""
    try:
        await transaction_service.delete_transaction(db, user.id, transaction_id)
    except TransactionNotFoundError:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "id": transaction_id}


class BulkDeleteRequest(BaseModel):
    transaction_ids: list[str]


@router.post("/transactions/bulk-delete")
async def agent_bulk_delete_transactions(
    body: BulkDeleteRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete multiple transactions by id in one call."""
    deleted = await transaction_service.bulk_delete_transactions(db, user.id, body.transaction_ids)
    return {"status": "ok", "deleted": deleted}


# ── Categorization ───────────────────────────────────────────────


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
        await transaction_service.upsert_merchant_rule(
            db, user.id, final_merchant_name, matched_merchant or merchant, cat.id,
        )

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


class AgentBulkCategorizeRequest(BaseModel):
    transaction_ids: list[str]
    category_name: str


@router.post("/categorize/bulk", summary="Bulk categorize transactions by id")
async def agent_bulk_categorize(
    body: AgentBulkCategorizeRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Set one category on many transactions by id in a single call.
    IDs that don't exist (or belong to another user) are silently skipped;
    returns how many were actually updated. Same shared logic as the
    dashboard's /categorize/bulk-manual (incl. classifier retraining)."""
    cat_result = await db.execute(
        select(Category).where(and_(Category.user_id == user.id, Category.name == body.category_name))
    )
    cat = cat_result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail=f"Category '{body.category_name}' not found")

    updated = await transaction_service.bulk_categorize(db, user.id, body.transaction_ids, cat.id)
    return {"status": "ok", "updated": updated, "category": body.category_name}


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


# ── Recurring Expenses ───────────────────────────────────────────
# Mirrors app.api.endpoints.finance's dashboard surface via the shared
# recurring_service/recurring_detection modules. /recurring/detected must
# stay registered before /recurring/{recurring_id}.

@router.get("/recurring/detected", response_model=list[RecurringSuggestionResponse])
async def agent_detected_recurring(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Suggested recurring expenses inferred from transaction history."""
    suggestions = await recurring_detection.detect_recurring_expenses(db, user.id)
    return [RecurringSuggestionResponse(**vars(s)) for s in suggestions]


@router.get("/recurring", response_model=list[RecurringExpenseResponse], summary="List tracked recurring expenses")
async def agent_list_recurring(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List all recurring expenses (bills/subscriptions) the user tracks."""
    return await recurring_service.list_recurring(db, user.id)


@router.post("/recurring", response_model=RecurringExpenseResponse, summary="Track a new recurring expense")
async def agent_create_recurring(
    body: RecurringExpenseCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a recurring expense: accept a /recurring/detected suggestion
    (POST the suggested fields) or add one manually."""
    return await recurring_service.create_recurring(db, user.id, body)


@router.patch("/recurring/{recurring_id}", response_model=RecurringExpenseResponse, summary="Update a recurring expense")
async def agent_update_recurring(
    recurring_id: str,
    body: RecurringExpenseUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a recurring expense (e.g. amount changed, new due date)."""
    try:
        return await recurring_service.update_recurring(db, user.id, recurring_id, body)
    except RecurringNotFoundError:
        raise HTTPException(status_code=404, detail="Recurring expense not found")


@router.delete("/recurring/{recurring_id}", summary="Stop tracking a recurring expense")
async def agent_delete_recurring(
    recurring_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete/dismiss a recurring expense."""
    try:
        await recurring_service.delete_recurring(db, user.id, recurring_id)
    except RecurringNotFoundError:
        raise HTTPException(status_code=404, detail="Recurring expense not found")
    return {"status": "deleted", "id": recurring_id}


# ── Budgets ──────────────────────────────────────────────────────
# Mirrors app.api.endpoints.finance's dashboard surface via the shared
# budget_service module (spent/remaining/pct_used computed identically).

@router.get("/budgets", response_model=list[BudgetResponse], summary="List budgets with spend status")
async def agent_list_budgets(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List budgets with current-period spent/remaining/pct_used."""
    return await budget_service.list_budgets(db, user.id)


@router.post("/budgets", response_model=BudgetResponse, summary="Create a budget")
async def agent_create_budget(
    body: BudgetCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a budget (spending cap for a category over a period)."""
    return await budget_service.create_budget(db, user.id, body)


@router.delete("/budgets/{budget_id}", summary="Delete a budget")
async def agent_delete_budget(
    budget_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a budget."""
    try:
        await budget_service.delete_budget(db, user.id, budget_id)
    except BudgetNotFoundError:
        raise HTTPException(status_code=404, detail="Budget not found")
    return {"status": "deleted"}


# ── Merchant rules ───────────────────────────────────────────────
# Direct CRUD on the auto-categorization rule table (distinct from
# /categorize's rename+recategorize workflow, which upserts these same
# rows as a side effect). Shared via app.services.merchant_service.

@router.get("/merchants", response_model=list[MerchantResponse], summary="List merchant categorization rules")
async def agent_list_merchants(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List merchant auto-categorization rules (pattern -> default category)."""
    return await merchant_service.list_merchants(db, user.id)


@router.post("/merchants", response_model=MerchantResponse, summary="Create a merchant categorization rule")
async def agent_create_merchant(
    body: MerchantCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a merchant rule so future imports auto-categorize matching
    transactions without manual intervention."""
    return await merchant_service.create_merchant(db, user.id, body)


@router.patch("/merchants/{merchant_id}", response_model=MerchantResponse, summary="Update a merchant categorization rule")
async def agent_update_merchant(
    merchant_id: str,
    body: MerchantUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a merchant rule's name, match patterns, or default category."""
    try:
        return await merchant_service.update_merchant(db, user.id, merchant_id, body)
    except MerchantNotFoundError:
        raise HTTPException(status_code=404, detail="Merchant not found")


@router.delete("/merchants/{merchant_id}", summary="Delete a merchant categorization rule")
async def agent_delete_merchant(
    merchant_id: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Delete a merchant rule."""
    try:
        await merchant_service.delete_merchant(db, user.id, merchant_id)
    except MerchantNotFoundError:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {"status": "deleted"}


# ── Accounts ─────────────────────────────────────────────────────
# Read the account list/balances and fix data mistakes (wrong anchor
# balance, wrong settlement-match keywords for card-payoff detection).
# Deliberately NOT here: creating/deleting accounts, connecting brokers
# (see app.api.endpoints.docs for the excluded-from-agent rationale).

@router.get("/accounts", response_model=list[AccountOut], summary="List accounts with computed balances")
async def agent_list_accounts(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """List every account (bank/credit_card/brokerage) with its computed
    (anchor-aware) balance."""
    return await account_service.list_accounts_with_balances(db, user.id)


@router.get("/accounts/credit-cards", response_model=list[CreditCardAccountResponse], summary="List credit-card accounts and their settlement patterns")
async def agent_list_credit_card_accounts(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Credit-card accounts with their configured settlement-match patterns.
    Empty/None means the account falls back to
    services.settlement.DEFAULT_SETTLEMENT_PATTERNS."""
    return await account_service.get_credit_card_accounts(db, user.id)


@router.post("/accounts/{account_id}/set-balance", response_model=SetBalanceResponse, summary="Correct an account's balance")
async def agent_set_account_balance(
    account_id: str,
    body: SetBalanceRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Fix an account's balance anchor to match the real bank/card statement.
    Stores directly; no fake transactions created."""
    try:
        previous, account = await account_service.set_account_balance(db, user.id, account_id, body.balance)
    except AccountNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")
    return {
        "status": "ok",
        "previous_balance": previous,
        "new_balance": body.balance,
        "balance_date": account.balance_date.isoformat(),
    }


@router.patch("/accounts/{account_id}/settlement-patterns", response_model=CreditCardAccountResponse, summary="Configure a card's settlement-match keywords")
async def agent_update_settlement_patterns(
    account_id: str,
    body: SettlementPatternsRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Configure the issuer-match keywords used to detect this credit card's
    settlement payment on bank import (services/settlement.py): fixes a
    card that isn't auto-resetting to zero after the statement is paid."""
    try:
        return await account_service.update_settlement_patterns(db, user.id, account_id, body.patterns)
    except AccountNotFoundError:
        raise HTTPException(status_code=404, detail="Account not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


