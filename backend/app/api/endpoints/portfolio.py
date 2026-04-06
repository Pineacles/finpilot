from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.user import User
from app.schemas.stock import (
    StockPositionResponse,
    PortfolioSummary,
    PortfolioSnapshotResponse,
    StockTransactionResponse,
)

router = APIRouter(prefix="/api/dashboard/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioSummary)
async def get_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user.id)
    )
    positions = result.scalars().all()

    total_value = sum((p.last_price or p.avg_cost_price) * p.quantity for p in positions)
    total_cost = sum(p.avg_cost_price * p.quantity for p in positions)
    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost else 0

    pos_responses = []
    for p in positions:
        mv = (p.last_price or p.avg_cost_price) * p.quantity
        pos_responses.append(StockPositionResponse(
            id=p.id,
            symbol=p.symbol,
            name=p.name,
            quantity=p.quantity,
            avg_cost_price=p.avg_cost_price,
            currency=p.currency,
            last_price=p.last_price,
            last_price_at=p.last_price_at,
            unrealized_pnl=p.unrealized_pnl,
            market_value=mv,
            weight_pct=(mv / total_value * 100) if total_value else 0,
        ))

    return PortfolioSummary(
        total_value=total_value,
        total_cost=total_cost,
        total_pnl=total_pnl,
        total_pnl_pct=total_pnl_pct,
        positions_count=len(positions),
        positions=pos_responses,
    )


@router.get("/history", response_model=list[PortfolioSnapshotResponse])
async def get_portfolio_history(
    days: int = 90,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(PortfolioSnapshot)
        .where(and_(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.snapshot_date >= since,
        ))
        .order_by(PortfolioSnapshot.snapshot_date)
    )
    return result.scalars().all()


@router.get("/transactions", response_model=list[StockTransactionResponse])
async def get_stock_transactions(
    symbol: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(StockTransaction).where(StockTransaction.user_id == user.id)
    if symbol:
        query = query.where(StockTransaction.symbol == symbol)
    query = query.order_by(desc(StockTransaction.executed_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    return result.scalars().all()
