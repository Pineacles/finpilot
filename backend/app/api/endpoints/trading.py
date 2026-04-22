"""User-facing trading endpoints — JWT auth.

Mounted at /api/dashboard/trading. Lets the human approve/reject/expire orders
that the agent submitted.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import trading as trading_svc

router = APIRouter(prefix="/api/dashboard/trading", tags=["trading"])


class RejectBody(BaseModel):
    reason: Optional[str] = None


@router.get("/pending-orders")
async def list_pending_orders(
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    orders = await trading_svc.list_orders(db, user.id, status=status)
    return {"pending_orders": orders}


@router.post("/pending-orders/{order_id}/approve")
async def approve_pending_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await trading_svc.approve_order(db, user.id, order_id)
    except trading_svc.GateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    return result


@router.post("/pending-orders/{order_id}/reject")
async def reject_pending_order(
    order_id: str,
    body: RejectBody = RejectBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await trading_svc.reject_order(db, user.id, order_id, reason=body.reason)
    except trading_svc.GateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    return result


@router.post("/pending-orders/{order_id}/expire")
async def expire_pending_order(
    order_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await trading_svc.expire_order(db, user.id, order_id)
    except trading_svc.GateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    return result


@router.post("/expire-stale")
async def expire_stale_orders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await trading_svc.expire_stale(db, user.id)
    return {"expired": count}
