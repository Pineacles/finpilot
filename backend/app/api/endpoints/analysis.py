"""Analysis endpoints — view stored portfolio analyses (JWT auth for dashboard)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.stock import MarketAnalysis
from app.models.user import User

router = APIRouter(prefix="/api/dashboard/analysis", tags=["analysis"])


@router.get("/latest")
async def get_latest(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent portfolio analysis."""
    result = await db.execute(
        select(MarketAnalysis).where(MarketAnalysis.user_id == user.id)
        .order_by(desc(MarketAnalysis.created_at)).limit(1)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        return {"status": "none", "message": "No analysis yet."}
    return {
        "id": analysis.id,
        "content": analysis.content,
        "created_at": analysis.created_at.isoformat(),
    }


@router.get("")
async def list_analyses(
    limit: int = 10,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List analysis history."""
    result = await db.execute(
        select(MarketAnalysis).where(MarketAnalysis.user_id == user.id)
        .order_by(desc(MarketAnalysis.created_at))
        .limit(limit).offset(offset)
    )
    return [
        {
            "id": a.id,
            "market_sentiment": a.content.get("market_sentiment") if isinstance(a.content, dict) else None,
            "stocks_count": len(a.content.get("stocks", [])) if isinstance(a.content, dict) else 0,
            "created_at": a.created_at.isoformat(),
        }
        for a in result.scalars().all()
    ]


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific analysis by ID."""
    result = await db.execute(
        select(MarketAnalysis).where(and_(
            MarketAnalysis.id == analysis_id,
            MarketAnalysis.user_id == user.id,
        ))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {
        "id": analysis.id,
        "content": analysis.content,
        "created_at": analysis.created_at.isoformat(),
    }
