"""Agent surface (X-API-Key) scoping: requesting another user's resource by
id must return 404, indistinguishable from "does not exist". Never a 403,
which would leak that the id exists for someone else.

Endpoint handlers are called directly (no HTTP transport), matching the
pattern in tests/api/test_watchlist_endpoints.py.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from app.models.finance import Budget, Category, Transaction
from app.models.merchant import Merchant
from app.api.endpoints.agent_finance_router import (
    agent_delete_transaction,
    agent_update_transaction,
    agent_delete_budget,
    agent_update_merchant,
    agent_delete_merchant,
)
from app.schemas.finance import TransactionUpdate
from app.schemas.merchants import MerchantUpdate

OTHER_USER = "user-somebody-else"


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


async def _make_foreign_transaction(db) -> Transaction:
    txn = Transaction(
        user_id=OTHER_USER, account_id="acct-other", date=date(2026, 6, 1),
        merchant="Foreign Shop", amount=-42.0, currency="CHF",
    )
    db.add(txn)
    await db.commit()
    return txn


async def test_delete_foreign_transaction_returns_404(db, user_id):
    txn = await _make_foreign_transaction(db)
    with pytest.raises(HTTPException) as exc_info:
        await agent_delete_transaction(txn.id, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 404


async def test_update_foreign_transaction_returns_404(db, user_id):
    txn = await _make_foreign_transaction(db)
    with pytest.raises(HTTPException) as exc_info:
        await agent_update_transaction(
            txn.id, TransactionUpdate(notes="hijacked"), user=FakeUser(user_id), db=db
        )
    assert exc_info.value.status_code == 404


async def test_delete_foreign_budget_returns_404(db, user_id):
    budget = Budget(
        user_id=OTHER_USER, name="Foreign Budget", amount=500.0,
        period="monthly", start_date=date(2026, 6, 1),
    )
    db.add(budget)
    await db.commit()

    with pytest.raises(HTTPException) as exc_info:
        await agent_delete_budget(budget.id, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 404


async def test_update_and_delete_foreign_merchant_return_404(db, user_id):
    cat = Category(user_id=OTHER_USER, name="Other Cat", type="expense")
    db.add(cat)
    await db.flush()
    merchant = Merchant(
        user_id=OTHER_USER, name="Foreign Merchant", patterns="foreign",
        default_category_id=cat.id, is_system=False,
    )
    db.add(merchant)
    await db.commit()

    with pytest.raises(HTTPException) as update_exc:
        await agent_update_merchant(
            merchant.id, MerchantUpdate(name="stolen"), user=FakeUser(user_id), db=db
        )
    assert update_exc.value.status_code == 404

    with pytest.raises(HTTPException) as delete_exc:
        await agent_delete_merchant(merchant.id, user=FakeUser(user_id), db=db)
    assert delete_exc.value.status_code == 404


async def test_owner_can_still_delete_own_transaction(db, user_id):
    """Control: same call succeeds for the owner. The 404s above are about
    scoping, not broken routes."""
    txn = Transaction(
        user_id=user_id, account_id="acct-mine", date=date(2026, 6, 2),
        merchant="My Shop", amount=-10.0, currency="CHF",
    )
    db.add(txn)
    await db.commit()

    result = await agent_delete_transaction(txn.id, user=FakeUser(user_id), db=db)
    assert result == {"status": "deleted", "id": txn.id}
