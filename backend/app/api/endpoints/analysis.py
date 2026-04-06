from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user, get_user_by_api_key
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.analysis import AnalysisResponse, RunAnalysisRequest
from app.services.analysis import generate_analysis, get_latest_analysis

router = APIRouter(tags=["analysis"])


@router.get("/api/dashboard/analysis/latest", response_model=list[AnalysisResponse])
async def get_latest(
    analysis_type: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_latest_analysis(db, user.id, analysis_type)


@router.post("/api/dashboard/analysis/run", response_model=AnalysisResponse)
async def run_analysis_endpoint(
    body: RunAnalysisRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
    if body.analysis_type not in ("macro", "sector", "position"):
        raise HTTPException(status_code=400, detail="Invalid analysis type")
    return await generate_analysis(db, user.id, body.analysis_type)


# Agent endpoint
@router.post("/api/agent/analysis/run", response_model=AnalysisResponse)
async def agent_run_analysis(
    body: RunAnalysisRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY not configured")
    return await generate_analysis(db, user.id, body.analysis_type)
