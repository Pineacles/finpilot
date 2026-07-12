"""POST /categorize/ai apply guard: an AI result that names the PARENT of a
transaction's current subcategory must not be applied (models sometimes
answer with the parent name, which would silently degrade an
already-more-specific categorization). Endpoint handlers are called
directly (no HTTP transport), matching tests/api/test_user_settings_endpoints.py.
"""
from __future__ import annotations

from datetime import date

from app.api.endpoints import categorize as categorize_endpoint
from app.api.endpoints.categorize import AICategorizeRequest, ai_categorize
from app.models.account import Account
from app.models.finance import Category, Transaction


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id
        self.api_key = None


async def _setup(db, user_id):
    account = Account(user_id=user_id, name="Bank", type="bank", currency="CHF")
    parent = Category(user_id=user_id, name="Groceries", type="expense")
    db.add_all([account, parent])
    await db.flush()
    child = Category(user_id=user_id, name="Supermarket", type="expense", parent_id=parent.id)
    other = Category(user_id=user_id, name="Dining", type="expense")
    db.add_all([child, other])
    await db.flush()
    txn = Transaction(
        user_id=user_id, account_id=account.id, date=date(2026, 3, 10),
        merchant="Fleisch Discount", amount=-30.0, currency="CHF",
        category_id=child.id,
    )
    db.add(txn)
    await db.commit()
    return txn, parent, child, other


async def test_parent_result_does_not_replace_subcategory(db, user_id, monkeypatch):
    txn, parent, child, other = await _setup(db, user_id)

    async def fake_batch(_db, _uid, txns, custom_rules=None):
        return [{"id": txn.id, "category_id": parent.id,
                 "category_name": parent.name, "confidence": 0.99}], []

    monkeypatch.setattr(categorize_endpoint, "batch_categorize_with_ai", fake_batch)

    result = await ai_categorize(
        AICategorizeRequest(transaction_ids=[txn.id]),
        user=FakeUser(user_id), db=db,
    )

    assert result["categorized"] == 0
    await db.refresh(txn)
    assert txn.category_id == child.id  # unchanged


async def test_unrelated_result_still_applies(db, user_id, monkeypatch):
    txn, parent, child, other = await _setup(db, user_id)

    async def fake_batch(_db, _uid, txns, custom_rules=None):
        return [{"id": txn.id, "category_id": other.id,
                 "category_name": other.name, "confidence": 0.99}], []

    monkeypatch.setattr(categorize_endpoint, "batch_categorize_with_ai", fake_batch)

    result = await ai_categorize(
        AICategorizeRequest(transaction_ids=[txn.id]),
        user=FakeUser(user_id), db=db,
    )

    assert result["categorized"] == 1
    await db.refresh(txn)
    assert txn.category_id == other.id
