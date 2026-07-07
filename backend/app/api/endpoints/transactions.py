from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.finance import (
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
    CategoryCreate,
    CategoryResponse,
)
from app.services import transaction_service
from app.services.transaction_service import TransactionNotFoundError

router = APIRouter(prefix="/api/dashboard", tags=["transactions"])


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    category_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=5000),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.list_transactions(
        db, user.id,
        category_id=category_id, from_date=from_date, to_date=to_date,
        search=search, limit=limit, offset=offset,
    )


@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(
    body: TransactionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.create_transaction(db, user.id, body)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await transaction_service.update_transaction(db, user.id, transaction_id, body)
    except TransactionNotFoundError:
        raise HTTPException(status_code=404, detail="Transaction not found")


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await transaction_service.delete_transaction(db, user.id, transaction_id)
    except TransactionNotFoundError:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"status": "deleted", "id": transaction_id}


class BulkDeleteRequest(BaseModel):
    transaction_ids: list[str]


@router.post("/transactions/bulk-delete")
async def bulk_delete_transactions(
    body: BulkDeleteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await transaction_service.bulk_delete_transactions(db, user.id, body.transaction_ids)
    return {"status": "ok", "deleted": deleted}


# --- Categories ---
@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.list_categories(db, user.id)


@router.post("/categories", response_model=CategoryResponse)
async def create_category(
    body: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await transaction_service.create_category(db, user.id, body)
