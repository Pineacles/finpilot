"""Statistics endpoints — monthly and yearly aggregated data.

Business logic lives in app.services.stats_service — this router just calls
into it and shapes the HTTP response.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.stats import MonthlyStatsResponse, YearlyStatsResponse
from app.services import stats_service

router = APIRouter(prefix="/api/dashboard/stats", tags=["stats"])


@router.get("/monthly", response_model=MonthlyStatsResponse)
async def monthly_stats(
    year: int | None = None,
    month: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await stats_service.monthly_stats(db, user.id, year=year, month=month)


@router.get("/yearly", response_model=YearlyStatsResponse)
async def yearly_stats(
    year: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await stats_service.yearly_stats(db, user.id, year=year)
