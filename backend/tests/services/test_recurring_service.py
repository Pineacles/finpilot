"""recurring_service: CRUD + per-user scoping for recurring expenses."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.finance import Category
from app.schemas.finance import RecurringExpenseCreate, RecurringExpenseUpdate
from app.services import recurring_service
from app.services.recurring_service import RecurringNotFoundError


async def _make_category(db, user_id: str, name: str = "Subscriptions") -> Category:
    cat = Category(user_id=user_id, name=name, type="expense")
    db.add(cat)
    await db.flush()
    return cat


async def test_create_and_list_recurring(db, user_id):
    cat = await _make_category(db, user_id)
    await db.commit()

    created = await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, currency="CHF", frequency="monthly",
        next_due_date=date(2026, 8, 1), category_id=cat.id,
    ))
    assert created.name == "Netflix"
    assert created.active is True

    listed = await recurring_service.list_recurring(db, user_id)
    assert len(listed) == 1
    assert listed[0].category_name == "Subscriptions"


async def test_list_recurring_scoped_to_user(db, user_id):
    await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))
    await recurring_service.create_recurring(db, "other-user", RecurringExpenseCreate(
        name="Spotify", amount=9.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))

    mine = await recurring_service.list_recurring(db, user_id)
    assert len(mine) == 1
    assert mine[0].name == "Netflix"


async def test_update_recurring(db, user_id):
    rec = await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))
    updated = await recurring_service.update_recurring(
        db, user_id, rec.id, RecurringExpenseUpdate(amount=17.90, active=False),
    )
    assert updated.amount == 17.90
    assert updated.active is False
    assert updated.name == "Netflix"  # untouched fields preserved


async def test_update_recurring_not_found_raises(db, user_id):
    with pytest.raises(RecurringNotFoundError):
        await recurring_service.update_recurring(db, user_id, "nope", RecurringExpenseUpdate(amount=1.0))


async def test_update_recurring_scoped_to_owner(db, user_id):
    rec = await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))
    with pytest.raises(RecurringNotFoundError):
        await recurring_service.update_recurring(db, "someone-else", rec.id, RecurringExpenseUpdate(amount=1.0))


async def test_delete_recurring(db, user_id):
    rec = await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))
    await recurring_service.delete_recurring(db, user_id, rec.id)
    assert await recurring_service.list_recurring(db, user_id) == []


async def test_delete_recurring_scoped_to_owner(db, user_id):
    rec = await recurring_service.create_recurring(db, user_id, RecurringExpenseCreate(
        name="Netflix", amount=15.90, frequency="monthly", next_due_date=date(2026, 8, 1),
    ))
    with pytest.raises(RecurringNotFoundError):
        await recurring_service.delete_recurring(db, "someone-else", rec.id)
    # Still there: a mismatched-owner delete must not remove it
    assert len(await recurring_service.list_recurring(db, user_id)) == 1


async def test_delete_recurring_not_found_raises(db, user_id):
    with pytest.raises(RecurringNotFoundError):
        await recurring_service.delete_recurring(db, user_id, "nope")
