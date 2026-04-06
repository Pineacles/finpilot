from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.account import Account
from app.models.sync import SyncLog
from app.models.user import User
from app.schemas.stock import SyncResponse, SyncStatusResponse
from app.services.saxo import sync_saxo_positions, create_portfolio_snapshot, saxo_client
from app.services.viseca import sync_viseca_transactions, viseca_client

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/saxo", response_model=SyncResponse)
async def trigger_saxo_sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account).where(Account.user_id == user.id, Account.type == "brokerage")
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="No brokerage account found")

    try:
        count = await sync_saxo_positions(db, user.id, account.id)
        await create_portfolio_snapshot(db, user.id)
        return SyncResponse(status="success", records_synced=count, message=f"Synced {count} positions")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Saxo sync failed: {e}")


@router.post("/saxo/token")
async def set_saxo_token(
    access_token: str,
    refresh_token: str,
    expires_in: int = 1200,
    user: User = Depends(get_current_user),
):
    """Manually set Saxo OAuth tokens (from developer portal 24h token or OAuth callback)."""
    saxo_client.set_tokens(access_token, refresh_token, expires_in)
    return {"status": "ok", "message": "Saxo tokens set"}


@router.post("/viseca", response_model=SyncResponse)
async def trigger_viseca_sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Account).where(Account.user_id == user.id, Account.type == "credit_card")
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="No credit card account found")

    try:
        count = await sync_viseca_transactions(db, user.id, account.id)
        return SyncResponse(status="success", records_synced=count, message=f"Synced {count} transactions")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Viseca sync failed: {e}")


@router.post("/viseca/session")
async def set_viseca_session(
    cookie: str,
    card_id: str,
    user: User = Depends(get_current_user),
):
    """Set Viseca session cookie and card ID for scraping."""
    viseca_client.set_session(cookie, card_id)
    return {"status": "ok", "message": "Viseca session configured"}


@router.get("/status", response_model=list[SyncStatusResponse])
async def get_sync_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = []
    for source in ["saxo", "viseca"]:
        result = await db.execute(
            select(SyncLog)
            .where(SyncLog.user_id == user.id, SyncLog.source == source)
            .order_by(desc(SyncLog.synced_at))
            .limit(1)
        )
        log = result.scalar_one_or_none()
        if log:
            results.append(log)
        else:
            results.append(SyncStatusResponse(
                source=source,
                status="never",
                records_synced=0,
                synced_at=None,
                error_message=None,
            ))
    return results
