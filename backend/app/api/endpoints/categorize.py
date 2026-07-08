"""Endpoints for recategorizing transactions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.finance import Transaction
from app.models.user import User
from app.schemas.categorize import ManualCategorizeResponse, BulkCategorizeResponse, AICategorizeResponse
from app.services.categorize import batch_categorize_with_ai
from app.services import transaction_service
from app.services.transaction_service import upsert_merchant_rule
from app.services import classifier

router = APIRouter(prefix="/api/dashboard", tags=["categorize"])


class ManualCategorize(BaseModel):
    transaction_id: str
    category_id: str
    apply_to_all: bool = True  # Apply to all transactions with same merchant
    new_merchant: str | None = None  # Rename merchant across all matching transactions


class AICategorizeRequest(BaseModel):
    transaction_ids: list[str]
    custom_prompt: str | None = None


@router.post("/categorize/manual", response_model=ManualCategorizeResponse, response_model_exclude_none=True)
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

    # Capture original merchant BEFORE rename for apply_to_all query
    original_merchant = txn.merchant
    renamed = 0

    txn.category_id = body.category_id
    if body.new_merchant:
        txn.merchant = body.new_merchant
        renamed += 1
    updated = 1

    # Apply to all transactions with the same (original) merchant name
    if body.apply_to_all and original_merchant:
        others = await db.execute(
            select(Transaction).where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.merchant == original_merchant,
                    Transaction.id != txn.id,
                )
            )
        )
        for other in others.scalars().all():
            other.category_id = body.category_id
            updated += 1
            if body.new_merchant:
                other.merchant = body.new_merchant
                renamed += 1

    # Upsert Merchant DB rule so future imports auto-categorize correctly
    final_merchant_name = body.new_merchant or original_merchant
    if final_merchant_name and final_merchant_name != "Pending":
        await upsert_merchant_rule(db, user.id, final_merchant_name, original_merchant, body.category_id)

    await db.commit()

    # Retrain classifier in background (non-blocking conceptually, but awaited)
    await classifier.train_classifier(db, user.id)

    resp = {"status": "ok", "updated": updated, "merchant": final_merchant_name}
    if body.new_merchant:
        resp["renamed_to"] = body.new_merchant
        resp["renamed"] = renamed
    return resp


class BulkManualCategorize(BaseModel):
    transaction_ids: list[str]
    category_id: str


@router.post("/categorize/bulk-manual", response_model=BulkCategorizeResponse)
async def bulk_manual_categorize(
    body: BulkManualCategorize,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Shared with the agent surface (POST /api/agent/categorize/bulk) via
    # transaction_service.bulk_categorize — includes classifier retraining.
    count = await transaction_service.bulk_categorize(
        db, user.id, body.transaction_ids, body.category_id
    )
    return {"status": "ok", "updated": count}


@router.post("/categorize/ai", response_model=AICategorizeResponse)
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
