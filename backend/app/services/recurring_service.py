"""Business logic for recurring expenses (bills/subscriptions).

Shared between the JWT-authenticated dashboard router (finance.py) and the
API-key agent router (agent_finance_router.py) so the two surfaces can't
drift out of sync — same pattern as transaction_service.py.
"""
from __future__ import annotations

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Category, RecurringExpense
from app.schemas.finance import RecurringExpenseCreate, RecurringExpenseResponse, RecurringExpenseUpdate


class RecurringNotFoundError(Exception):
    """Raised when a recurring_id doesn't exist (or isn't owned by the user)."""

    def __init__(self, recurring_id: str):
        self.recurring_id = recurring_id
        super().__init__(f"Recurring expense not found: {recurring_id}")


async def list_recurring(db: AsyncSession, user_id: str) -> list[RecurringExpenseResponse]:
    result = await db.execute(
        select(RecurringExpense, Category)
        .outerjoin(Category, RecurringExpense.category_id == Category.id)
        .where(RecurringExpense.user_id == user_id)
        .order_by(RecurringExpense.next_due_date)
    )
    responses = []
    for rec, cat in result.all():
        r = RecurringExpenseResponse.model_validate(rec)
        r.category_name = cat.name if cat else None
        responses.append(r)
    return responses


async def create_recurring(
    db: AsyncSession, user_id: str, body: RecurringExpenseCreate
) -> RecurringExpenseResponse:
    rec = RecurringExpense(user_id=user_id, **body.model_dump())
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return RecurringExpenseResponse.model_validate(rec)


async def _get_owned(db: AsyncSession, user_id: str, recurring_id: str) -> RecurringExpense:
    result = await db.execute(
        select(RecurringExpense).where(
            and_(RecurringExpense.id == recurring_id, RecurringExpense.user_id == user_id)
        )
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise RecurringNotFoundError(recurring_id)
    return rec


async def update_recurring(
    db: AsyncSession, user_id: str, recurring_id: str, body: RecurringExpenseUpdate
) -> RecurringExpenseResponse:
    rec = await _get_owned(db, user_id, recurring_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(rec, field, value)
    await db.commit()
    await db.refresh(rec)

    cat_name = None
    if rec.category_id:
        cat_result = await db.execute(select(Category).where(Category.id == rec.category_id))
        cat = cat_result.scalar_one_or_none()
        cat_name = cat.name if cat else None
    r = RecurringExpenseResponse.model_validate(rec)
    r.category_name = cat_name
    return r


async def delete_recurring(db: AsyncSession, user_id: str, recurring_id: str) -> None:
    rec = await _get_owned(db, user_id, recurring_id)
    await db.delete(rec)
    await db.commit()
