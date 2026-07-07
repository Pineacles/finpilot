"""Merchant management — view, add, edit categorization rules."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Category
from app.models.merchant import Merchant
from app.models.user import User
from app.schemas.merchants import MerchantResponse, MerchantCreate, MerchantUpdate

router = APIRouter(prefix="/api/dashboard/merchants", tags=["merchants"])


@router.get("", response_model=list[MerchantResponse])
async def list_merchants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Merchant, Category)
        .outerjoin(Category, Merchant.default_category_id == Category.id)
        .where(Merchant.user_id == user.id)
        .order_by(Merchant.name)
    )
    merchants = []
    for m, cat in result.all():
        r = MerchantResponse.model_validate(m)
        r.category_name = cat.name if cat else None
        merchants.append(r)
    return merchants


@router.post("", response_model=MerchantResponse)
async def create_merchant(
    body: MerchantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = Merchant(user_id=user.id, name=body.name, patterns=body.patterns, default_category_id=body.default_category_id, is_system=False)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return MerchantResponse.model_validate(m)


@router.patch("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: str,
    body: MerchantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id, Merchant.user_id == user.id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    await db.commit()
    await db.refresh(m)
    # Fetch category name
    cat_name = None
    if m.default_category_id:
        cat_result = await db.execute(select(Category).where(Category.id == m.default_category_id))
        cat = cat_result.scalar_one_or_none()
        cat_name = cat.name if cat else None
    r = MerchantResponse.model_validate(m)
    r.category_name = cat_name
    return r


@router.delete("/{merchant_id}")
async def delete_merchant(
    merchant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Merchant).where(Merchant.id == merchant_id, Merchant.user_id == user.id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Merchant not found")
    await db.delete(m)
    await db.commit()
    return {"status": "deleted"}
