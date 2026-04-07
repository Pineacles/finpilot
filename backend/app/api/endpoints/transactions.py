from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc, and_, func
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Transaction, Category
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

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(txn, field, value)

    # If merchant name changed, apply to all transactions with the same old merchant name
    bulk_updated = 0
    if body.merchant and body.merchant != old_merchant:
        others = await db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.merchant == old_merchant,
                    Transaction.id != transaction_id,
                )
            )
        )
        for other in others.scalars().all():
            other.merchant = body.merchant
            bulk_updated += 1

    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


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
