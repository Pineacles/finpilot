"""Agent trading endpoints — X-API-Key auth.

These endpoints let the AI agent submit, list orders, and query pending orders.
The agent NEVER calls Saxo directly — it goes through the gate in trading.py.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.database import get_db
from app.models.user import User
from app.services import trading as trading_svc

router = APIRouter(prefix="/api/agent/trading", tags=["agent-trading"])


class OrderRequestBody(BaseModel):
    action: str  # place | modify | cancel
    account_key: str
    symbol: Optional[str] = None
    buy_sell: Optional[str] = None
    amount: Optional[float] = None
    order_type: Optional[str] = None
    duration: Optional[str] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_order_id: Optional[str] = None
    buy_assessment_id: Optional[str] = None
    rationale: Optional[str] = None
    idempotency_key: Optional[str] = None


@router.post("/request-order")
async def agent_request_order(
    body: OrderRequestBody,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await trading_svc.request_order(
            db, user.id,
            action=body.action,
            account_key=body.account_key,
            symbol=body.symbol,
            buy_sell=body.buy_sell,
            amount=body.amount,
            order_type=body.order_type,
            duration=body.duration,
            limit_price=body.limit_price,
            stop_price=body.stop_price,
            target_order_id=body.target_order_id,
            buy_assessment_id=body.buy_assessment_id,
            rationale=body.rationale,
            idempotency_key=body.idempotency_key,
        )
    except trading_svc.GateError as exc:
        raise HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})
    return {
        "pending_order_id": result["pending_order_id"],
        "status": result["status"],
        "mode": result["mode"],
        "broker_order_id": result.get("broker_order_id"),
    }


@router.get("/pending-orders")
async def agent_list_pending_orders(
    status: Optional[str] = Query(None),
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    orders = await trading_svc.list_orders(db, user.id, status=status)
    return {"pending_orders": orders}
