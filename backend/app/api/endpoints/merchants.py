"""Merchant management: view, add, edit categorization rules.

Business logic lives in app.services.merchant_service so the dashboard
(JWT) and agent (API key) surfaces share the same behavior.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.merchants import MerchantResponse, MerchantCreate, MerchantUpdate
from app.services import merchant_service
from app.services.merchant_service import MerchantNotFoundError

router = APIRouter(prefix="/api/dashboard/merchants", tags=["merchants"])


@router.get("", response_model=list[MerchantResponse])
async def list_merchants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await merchant_service.list_merchants(db, user.id)


@router.post("", response_model=MerchantResponse)
async def create_merchant(
    body: MerchantCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await merchant_service.create_merchant(db, user.id, body)


@router.patch("/{merchant_id}", response_model=MerchantResponse)
async def update_merchant(
    merchant_id: str,
    body: MerchantUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await merchant_service.update_merchant(db, user.id, merchant_id, body)
    except MerchantNotFoundError:
        raise HTTPException(status_code=404, detail="Merchant not found")


@router.delete("/{merchant_id}")
async def delete_merchant(
    merchant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await merchant_service.delete_merchant(db, user.id, merchant_id)
    except MerchantNotFoundError:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {"status": "deleted"}
