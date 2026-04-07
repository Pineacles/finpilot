"""Endpoints for recategorizing transactions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Transaction, Category
from app.models.user import User
from app.services.categorize import batch_categorize_with_ai

router = APIRouter(prefix="/api/dashboard", tags=["categorize"])


class ManualCategorize(BaseModel):
    transaction_id: str
    category_id: str
    apply_to_all: bool = True  # Apply to all transactions with same merchant


class AICategorizeRequest(BaseModel):
    transaction_ids: list[str]
    custom_prompt: str | None = None


@router.post("/categorize/manual")
async def manual_categorize(
    body: ManualCategorize,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Transaction).where(
            and_(Transaction.id == body.transaction_id, Transaction.user_id == user.id)
        )
    )
    txn = result.scalar_one_or_none()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")

    txn.category_id = body.category_id
    updated = 1

    # Apply to all transactions with the same merchant name
    if body.apply_to_all and txn.merchant:
        others = await db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.merchant == txn.merchant,
                    Transaction.id != txn.id,
                )
            )
        )
        for other in others.scalars().all():
            other.category_id = body.category_id
            updated += 1

    await db.commit()
    return {"status": "ok", "updated": updated, "merchant": txn.merchant}


class BulkManualCategorize(BaseModel):
    transaction_ids: list[str]
    category_id: str


@router.post("/categorize/bulk-manual")
async def bulk_manual_categorize(
    body: BulkManualCategorize,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = 0
    for tid in body.transaction_ids:
        result = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == tid, Transaction.user_id == user.id)
            )
        )
        txn = result.scalar_one_or_none()
        if txn:
            txn.category_id = body.category_id
            count += 1
    await db.commit()
    return {"status": "ok", "updated": count}


@router.post("/categorize/ai")
async def ai_categorize(
    body: AICategorizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send transactions to AI for categorization, optionally with a custom prompt."""
    # Fetch the transactions
    txns = []
    for tid in body.transaction_ids:
        result = await db.execute(
            select(Transaction).where(
                and_(Transaction.id == tid, Transaction.user_id == user.id)
            )
        )
        txn = result.scalar_one_or_none()
        if txn:
            txns.append({
                "id": txn.id,
                "description": txn.notes or txn.merchant,
                "amount": txn.amount,
                "merchant": txn.merchant,
            })

    if not txns:
        raise HTTPException(status_code=400, detail="No valid transactions found")

    # If custom prompt, inject it into the categorization
    if body.custom_prompt:
        # Override the batch categorize to include custom instructions
        from app.services.categorize import _ai_categorize_with_custom_prompt
        results = await _ai_categorize_with_custom_prompt(db, user.id, txns, body.custom_prompt)
    else:
        results = await batch_categorize_with_ai(db, user.id, txns)

    # Apply results
    applied = 0
    for r in results:
        if r.get("category_id"):
            res = await db.execute(
                select(Transaction).where(Transaction.id == r["id"])
            )
            txn = res.scalar_one_or_none()
            if txn:
                txn.category_id = r["category_id"]
                applied += 1

    await db.commit()

    return {
        "status": "ok",
        "sent": len(txns),
        "categorized": applied,
        "results": results,
    }
