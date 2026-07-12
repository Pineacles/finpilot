"""Merchant auto-categorization rule CRUD, shared between the JWT dashboard
router (api/endpoints/merchants.py) and the API-key agent router
(api/endpoints/agent_finance_router.py). These are user-owned "when a
transaction matches pattern X, categorize it as Y" rules, distinct from
`transaction_service.upsert_merchant_rule`, which is the auto-upsert path
categorization triggers; this module is the direct user-facing CRUD.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Category
from app.models.merchant import Merchant
from app.schemas.merchants import MerchantCreate, MerchantResponse, MerchantUpdate


class MerchantNotFoundError(Exception):
    def __init__(self, merchant_id: str):
        self.merchant_id = merchant_id
        super().__init__(f"Merchant not found: {merchant_id}")


async def list_merchants(db: AsyncSession, user_id: str) -> list[MerchantResponse]:
    result = await db.execute(
        select(Merchant, Category)
        .outerjoin(Category, Merchant.default_category_id == Category.id)
        .where(Merchant.user_id == user_id)
        .order_by(Merchant.name)
    )
    merchants = []
    for m, cat in result.all():
        r = MerchantResponse.model_validate(m)
        r.category_name = cat.name if cat else None
        merchants.append(r)
    return merchants


async def create_merchant(db: AsyncSession, user_id: str, body: MerchantCreate) -> MerchantResponse:
    m = Merchant(
        user_id=user_id, name=body.name, patterns=body.patterns,
        default_category_id=body.default_category_id, is_system=False,
    )
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return MerchantResponse.model_validate(m)


async def _get_owned(db: AsyncSession, user_id: str, merchant_id: str) -> Merchant:
    result = await db.execute(
        select(Merchant).where(Merchant.id == merchant_id, Merchant.user_id == user_id)
    )
    m = result.scalar_one_or_none()
    if not m:
        raise MerchantNotFoundError(merchant_id)
    return m


async def update_merchant(
    db: AsyncSession, user_id: str, merchant_id: str, body: MerchantUpdate
) -> MerchantResponse:
    m = await _get_owned(db, user_id, merchant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    await db.commit()
    await db.refresh(m)

    cat_name = None
    if m.default_category_id:
        cat_result = await db.execute(select(Category).where(Category.id == m.default_category_id))
        cat = cat_result.scalar_one_or_none()
        cat_name = cat.name if cat else None

    r = MerchantResponse.model_validate(m)
    r.category_name = cat_name
    return r


async def delete_merchant(db: AsyncSession, user_id: str, merchant_id: str) -> None:
    m = await _get_owned(db, user_id, merchant_id)
    await db.delete(m)
    await db.commit()
