from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.sync import SyncLog
from app.models.user import User
from app.schemas.stock import SyncStatusResponse

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/gmail")
async def trigger_gmail_poll(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Poll Gmail for new bank notifications."""
    from app.services.gmail_poller import poll_gmail
    result = await poll_gmail(db, user.id)

    db.add(SyncLog(
        user_id=user.id,
        source="gmail",
        status="success" if not result["errors"] else "partial",
        records_synced=result["new_transactions"],
        error_message="; ".join(result["errors"])[:500] if result["errors"] else None,
    ))
    await db.commit()

    return {
        "status": "ok",
        "new_transactions": result["new_transactions"],
        "balance": result["balance"],
        "errors": result["errors"],
    }


@router.get("/status", response_model=list[SyncStatusResponse])
async def get_sync_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    results = []
    for source in ["gmail"]:
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
