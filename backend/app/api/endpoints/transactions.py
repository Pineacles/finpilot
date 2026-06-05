from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Transaction, Category
from app.models.merchant import Merchant
from app.models.user import User
from app.schemas.finance import (
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
    CategoryCreate,
    CategoryResponse,
)

router = APIRouter(prefix="/api/dashboard", tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    category_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=5000),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ParentCat = aliased(Category)
    query = (
        select(Transaction, Category, ParentCat)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .outerjoin(ParentCat, Category.parent_id == ParentCat.id)
        .where(Transaction.user_id == user.id)
    )
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if from_date:
        query = query.where(Transaction.date >= from_date)
    if to_date:
        query = query.where(Transaction.date <= to_date)
    if search:
        query = query.where(Transaction.merchant.ilike(f"%{search}%"))

    query = query.order_by(desc(Transaction.date)).limit(limit).offset(offset)
    result = await db.execute(query)

    responses = []
    for txn, cat, parent_cat in result.all():
        r = TransactionResponse.model_validate(txn)
        r.category_name = cat.name if cat else None
        r.parent_category_name = parent_cat.name if parent_cat else None
        responses.append(r)
    return responses


@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    txn = Transaction(user_id=user.id, **body.model_dump())
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == transaction_id, Transaction.user_id == user.id)
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    old_merchant = txn.merchant
    old_category_id = txn.category_id

    # Only apply actual data fields to the transaction (not control flags)
    for field in ("category_id", "notes", "merchant"):
        value = getattr(body, field, None)
        if value is not None:
            setattr(txn, field, value)

    merchant_changed = body.merchant and body.merchant != old_merchant
    category_changed = body.category_id and body.category_id != old_category_id

    # Build conditions for finding related transactions
    should_bulk_merchant = merchant_changed and body.apply_merchant_to_all
    should_bulk_category = category_changed and body.apply_category_to_all

    if should_bulk_merchant or should_bulk_category:
        conditions = [
            Transaction.user_id == user.id,
            Transaction.merchant == old_merchant,
            Transaction.id != transaction_id,
        ]
        # Scope by description if provided (e.g. only "carvolution" notes, not all "revolut")
        if body.description_filter:
            conditions.append(Transaction.notes.ilike(f"%{body.description_filter}%"))

        others = await db.execute(select(Transaction).where(and_(*conditions)))
        for other in others.scalars().all():
            if should_bulk_merchant:
                other.merchant = body.merchant
            if should_bulk_category:
                other.category_id = body.category_id

    # Upsert Merchant DB rule so future imports auto-categorize correctly
    final_merchant = body.merchant or old_merchant
    final_category = body.category_id or old_category_id
    if final_merchant and final_merchant != "Pending" and final_category:
        # Include description_filter as a pattern so future imports with that keyword also match
        await _upsert_merchant_rule(
            db, user.id, final_merchant,
            old_merchant if merchant_changed else None,
            final_category,
            extra_pattern=body.description_filter,
        )

    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


async def _upsert_merchant_rule(
    db: AsyncSession, user_id: str, merchant_name: str, original_name: str | None, category_id: str,
    extra_pattern: str | None = None,
):
    """Create or update a Merchant DB entry so future imports auto-categorize."""
    patterns_set: set[str] = set()
    for name in (merchant_name, original_name):
        if name:
            cleaned = name.strip().lower()
            if cleaned:
                patterns_set.add(cleaned)
                for word in cleaned.split():
                    if len(word) >= 4 and word not in ("gmbh", "sarl", "bank", "card", "payment", "services"):
                        patterns_set.add(word)
    if extra_pattern:
        cleaned = extra_pattern.strip().lower()
        if cleaned:
            patterns_set.add(cleaned)

    if not patterns_set:
        return

    result = await db.execute(
        select(Merchant).where(and_(Merchant.name == merchant_name, Merchant.user_id == user_id))
    )
    existing = result.scalar_one_or_none()

    if existing:
        old_patterns = set(p.strip().lower() for p in existing.patterns.split("|") if p.strip())
        merged = old_patterns | patterns_set
        existing.patterns = "|".join(sorted(merged))
        existing.default_category_id = category_id
    else:
        db.add(Merchant(
            user_id=user_id,
            name=merchant_name,
            patterns="|".join(sorted(patterns_set)),
            default_category_id=category_id,
            is_system=False,
        ))


# --- Categories ---
@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.user_id == user.id).order_by(Category.name)
    )
    return result.scalars().all()


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    body: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cat = Category(user_id=user.id, **body.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryResponse.model_validate(cat)
