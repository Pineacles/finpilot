"""Journal endpoints — PostMortem and BuyAssessment CRUD.

JWT-authenticated user endpoints only. Agent equivalents are appended to agent.py.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.stock import PostMortem, BuyAssessment
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["journal"])


# ── Schemas ──────────────────────────────────────────────────────

class PostMortemCreate(BaseModel):
    symbol: str
    entry_price: float
    exit_price: float
    notes: str | None = None
    analysis_id: str | None = None


class PostMortemUpdate(BaseModel):
    entry_price: float | None = None
    exit_price: float | None = None
    notes: str | None = None


class BuyAssessmentCreate(BaseModel):
    symbol: str
    recommendation: str  # buy|hold|watch|avoid
    target_price: float | None = None
    stop_loss: float | None = None
    thesis: str = Field(..., min_length=1, max_length=4000)
    risk_factors: str | None = None
    conviction: int = Field(..., ge=1, le=5)
    time_horizon: str | None = None  # short|medium|long
    assessed_at: datetime | None = None


class BuyAssessmentUpdate(BaseModel):
    recommendation: str | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    thesis: str | None = Field(None, max_length=4000)
    risk_factors: str | None = None
    conviction: int | None = Field(None, ge=1, le=5)
    time_horizon: str | None = None
    assessed_at: datetime | None = None


# ── Helpers ──────────────────────────────────────────────────────

def _pm_to_dict(pm: PostMortem) -> dict:
    return {
        "id": pm.id,
        "user_id": pm.user_id,
        "symbol": pm.symbol,
        "analysis_id": pm.analysis_id,
        "entry_price": pm.entry_price,
        "exit_price": pm.exit_price,
        "pnl_pct": pm.pnl_pct,
        "notes": pm.notes,
        "created_at": pm.created_at.isoformat(),
    }


def _ba_to_dict(ba: BuyAssessment) -> dict:
    return {
        "id": ba.id,
        "user_id": ba.user_id,
        "symbol": ba.symbol,
        "recommendation": ba.recommendation,
        "target_price": ba.target_price,
        "stop_loss": ba.stop_loss,
        "thesis": ba.thesis,
        "risk_factors": ba.risk_factors,
        "conviction": ba.conviction,
        "time_horizon": ba.time_horizon,
        "assessed_at": ba.assessed_at.isoformat(),
        "created_at": ba.created_at.isoformat(),
        "updated_at": ba.updated_at.isoformat(),
    }


# ── Post-Mortems (user) ──────────────────────────────────────────

@router.get("/post-mortems")
async def list_post_mortems(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(PostMortem).where(PostMortem.user_id == user.id)
    if symbol:
        q = q.where(PostMortem.symbol == symbol.upper())
    q = q.order_by(desc(PostMortem.created_at)).limit(limit)
    result = await db.execute(q)
    return [_pm_to_dict(pm) for pm in result.scalars().all()]


@router.post("/post-mortems", status_code=201)
async def create_post_mortem(
    body: PostMortemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    pnl_pct = (body.exit_price - body.entry_price) / body.entry_price * 100
    pm = PostMortem(
        user_id=user.id,
        symbol=body.symbol.upper(),
        entry_price=body.entry_price,
        exit_price=body.exit_price,
        pnl_pct=pnl_pct,
        notes=body.notes,
        analysis_id=body.analysis_id,
    )
    db.add(pm)
    await db.commit()
    await db.refresh(pm)
    return _pm_to_dict(pm)


@router.patch("/post-mortems/{pm_id}")
async def update_post_mortem(
    pm_id: str,
    body: PostMortemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PostMortem).where(and_(PostMortem.id == pm_id, PostMortem.user_id == user.id))
    )
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    if body.notes is not None:
        pm.notes = body.notes
    if body.entry_price is not None:
        pm.entry_price = body.entry_price
    if body.exit_price is not None:
        pm.exit_price = body.exit_price
    if body.entry_price is not None or body.exit_price is not None:
        pm.pnl_pct = (pm.exit_price - pm.entry_price) / pm.entry_price * 100
    await db.commit()
    await db.refresh(pm)
    return _pm_to_dict(pm)


@router.delete("/post-mortems/{pm_id}", status_code=204)
async def delete_post_mortem(
    pm_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PostMortem).where(and_(PostMortem.id == pm_id, PostMortem.user_id == user.id))
    )
    pm = result.scalar_one_or_none()
    if not pm:
        raise HTTPException(status_code=404, detail="Post-mortem not found")
    await db.delete(pm)
    await db.commit()


# ── Buy Assessments (user) ────────────────────────────────────────

VALID_RECOMMENDATIONS = {"buy", "hold", "watch", "avoid"}
VALID_HORIZONS = {"short", "medium", "long", None}


@router.get("/buy-assessments")
async def list_buy_assessments(
    symbol: str | None = None,
    recommendation: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(BuyAssessment).where(BuyAssessment.user_id == user.id)
    if symbol:
        q = q.where(BuyAssessment.symbol == symbol.upper())
    if recommendation:
        q = q.where(BuyAssessment.recommendation == recommendation)
    q = q.order_by(desc(BuyAssessment.created_at)).limit(limit)
    result = await db.execute(q)
    return [_ba_to_dict(ba) for ba in result.scalars().all()]


@router.post("/buy-assessments", status_code=201)
async def create_buy_assessment(
    body: BuyAssessmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.recommendation not in VALID_RECOMMENDATIONS:
        raise HTTPException(status_code=422, detail=f"recommendation must be one of: {', '.join(VALID_RECOMMENDATIONS)}")
    if body.time_horizon not in VALID_HORIZONS:
        raise HTTPException(status_code=422, detail="time_horizon must be short, medium, or long")
    ba = BuyAssessment(
        user_id=user.id,
        symbol=body.symbol.upper(),
        recommendation=body.recommendation,
        target_price=body.target_price,
        stop_loss=body.stop_loss,
        thesis=body.thesis,
        risk_factors=body.risk_factors,
        conviction=body.conviction,
        time_horizon=body.time_horizon,
        assessed_at=body.assessed_at or datetime.now(timezone.utc),
    )
    db.add(ba)
    await db.commit()
    await db.refresh(ba)
    return _ba_to_dict(ba)


@router.patch("/buy-assessments/{ba_id}")
async def update_buy_assessment(
    ba_id: str,
    body: BuyAssessmentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BuyAssessment).where(and_(BuyAssessment.id == ba_id, BuyAssessment.user_id == user.id))
    )
    ba = result.scalar_one_or_none()
    if not ba:
        raise HTTPException(status_code=404, detail="Buy assessment not found")
    if body.recommendation is not None:
        if body.recommendation not in VALID_RECOMMENDATIONS:
            raise HTTPException(status_code=422, detail=f"recommendation must be one of: {', '.join(VALID_RECOMMENDATIONS)}")
        ba.recommendation = body.recommendation
    if body.target_price is not None:
        ba.target_price = body.target_price
    if body.stop_loss is not None:
        ba.stop_loss = body.stop_loss
    if body.thesis is not None:
        ba.thesis = body.thesis
    if body.risk_factors is not None:
        ba.risk_factors = body.risk_factors
    if body.conviction is not None:
        ba.conviction = body.conviction
    if body.time_horizon is not None:
        if body.time_horizon not in {"short", "medium", "long"}:
            raise HTTPException(status_code=422, detail="time_horizon must be short, medium, or long")
        ba.time_horizon = body.time_horizon
    if body.assessed_at is not None:
        ba.assessed_at = body.assessed_at
    ba.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ba)
    return _ba_to_dict(ba)


@router.delete("/buy-assessments/{ba_id}", status_code=204)
async def delete_buy_assessment(
    ba_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BuyAssessment).where(and_(BuyAssessment.id == ba_id, BuyAssessment.user_id == user.id))
    )
    ba = result.scalar_one_or_none()
    if not ba:
        raise HTTPException(status_code=404, detail="Buy assessment not found")
    await db.delete(ba)
    await db.commit()
