"""transaction_service: CRUD, per-user scoping, bulk-delete, merchant-rule upsert."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.models.merchant import Merchant
from app.schemas.finance import TransactionCreate, TransactionUpdate
from app.services import transaction_service
from app.services.transaction_service import TransactionNotFoundError


async def _make_account(db, user_id: str, name: str = "Bank") -> Account:
    acct = Account(user_id=user_id, name=name, type="bank", currency="CHF")
    db.add(acct)
    await db.flush()
    return acct


async def _make_category(db, user_id: str, name: str = "Groceries") -> Category:
    cat = Category(user_id=user_id, name=name, type="expense")
    db.add(cat)
    await db.flush()
    return cat


async def test_create_and_list_transaction(db, user_id):
    acct = await _make_account(db, user_id)
    cat = await _make_category(db, user_id)
    await db.commit()

    body = TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 5), merchant="Migros",
        amount=-42.5, currency="CHF", category_id=cat.id,
    )
    created = await transaction_service.create_transaction(db, user_id, body)
    assert created.merchant == "Migros"
    assert created.amount == -42.5

    listed = await transaction_service.list_transactions(db, user_id)
    assert len(listed) == 1
    assert listed[0].id == created.id
    assert listed[0].category_name == "Groceries"


async def test_list_transactions_filters_and_scoping(db, user_id):
    acct = await _make_account(db, user_id)
    other_acct = await _make_account(db, "other-user", name="Other Bank")
    await db.commit()

    await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-10, currency="CHF",
    ))
    await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 2, 1), merchant="Coop", amount=-20, currency="CHF",
    ))
    await transaction_service.create_transaction(db, "other-user", TransactionCreate(
        account_id=other_acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-99, currency="CHF",
    ))

    # Scoped to user_id only
    all_txns = await transaction_service.list_transactions(db, user_id)
    assert len(all_txns) == 2

    # search filter
    migros_only = await transaction_service.list_transactions(db, user_id, search="migros")
    assert len(migros_only) == 1
    assert migros_only[0].merchant == "Migros"

    # date range filter
    jan_only = await transaction_service.list_transactions(db, user_id, from_date=date(2026, 1, 1), to_date=date(2026, 1, 31))
    assert len(jan_only) == 1
    assert jan_only[0].merchant == "Migros"


async def test_update_transaction_bulk_applies_to_same_merchant_only(db, user_id):
    acct = await _make_account(db, user_id)
    cat_a = await _make_category(db, user_id, "Uncategorized")
    cat_b = await _make_category(db, user_id, "Transport")
    await db.commit()

    t1 = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 1), merchant="SBB", amount=-10, currency="CHF", category_id=cat_a.id,
    ))
    t2 = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 2), merchant="SBB", amount=-20, currency="CHF", category_id=cat_a.id,
    ))
    t3 = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 3), merchant="Migros", amount=-30, currency="CHF", category_id=cat_a.id,
    ))

    updated = await transaction_service.update_transaction(
        db, user_id, t1.id,
        TransactionUpdate(category_id=cat_b.id, apply_category_to_all=True, apply_merchant_to_all=True),
    )
    assert updated.category_id == cat_b.id

    # t2 (same merchant) got recategorized too; t3 (different merchant) untouched
    listed = {t.id: t for t in await transaction_service.list_transactions(db, user_id)}
    assert listed[t2.id].category_id == cat_b.id
    assert listed[t3.id].category_id == cat_a.id

    # A Merchant rule was upserted for the (user-scoped) merchant name
    from sqlalchemy import select as _select
    row = (await db.execute(_select(Merchant).where(Merchant.name == "SBB"))).scalar_one_or_none()
    assert row is not None
    assert row.user_id == user_id
    assert row.default_category_id == cat_b.id


async def test_update_transaction_not_found_raises(db, user_id):
    with pytest.raises(TransactionNotFoundError):
        await transaction_service.update_transaction(db, user_id, "does-not-exist", TransactionUpdate(notes="x"))


async def test_update_transaction_scoped_to_owner(db, user_id):
    acct = await _make_account(db, user_id)
    await db.commit()
    txn = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-10, currency="CHF",
    ))

    with pytest.raises(TransactionNotFoundError):
        await transaction_service.update_transaction(db, "someone-else", txn.id, TransactionUpdate(notes="hijacked"))


async def test_delete_transaction(db, user_id):
    acct = await _make_account(db, user_id)
    await db.commit()
    txn = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-10, currency="CHF",
    ))

    await transaction_service.delete_transaction(db, user_id, txn.id)
    assert await transaction_service.list_transactions(db, user_id) == []


async def test_delete_transaction_scoped_to_owner(db, user_id):
    acct = await _make_account(db, user_id)
    await db.commit()
    txn = await transaction_service.create_transaction(db, user_id, TransactionCreate(
        account_id=acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-10, currency="CHF",
    ))

    with pytest.raises(TransactionNotFoundError):
        await transaction_service.delete_transaction(db, "someone-else", txn.id)
    # Still there: the wrong-user delete must not have removed it
    assert len(await transaction_service.list_transactions(db, user_id)) == 1


async def test_bulk_delete_transactions_scoped_to_owner(db, user_id):
    acct = await _make_account(db, user_id)
    other_acct = await _make_account(db, "other-user", name="Other Bank")
    await db.commit()

    mine = [
        await transaction_service.create_transaction(db, user_id, TransactionCreate(
            account_id=acct.id, date=date(2026, 1, i + 1), merchant="Migros", amount=-10, currency="CHF",
        ))
        for i in range(3)
    ]
    theirs = await transaction_service.create_transaction(db, "other-user", TransactionCreate(
        account_id=other_acct.id, date=date(2026, 1, 1), merchant="Migros", amount=-99, currency="CHF",
    ))

    ids_to_delete = [t.id for t in mine] + [theirs.id]
    deleted_count = await transaction_service.bulk_delete_transactions(db, user_id, ids_to_delete)

    # Only the 3 owned by user_id were deleted; the other user's row is untouched.
    assert deleted_count == 3
    assert await transaction_service.list_transactions(db, user_id) == []
    assert len(await transaction_service.list_transactions(db, "other-user")) == 1


async def test_bulk_delete_empty_list_is_noop(db, user_id):
    assert await transaction_service.bulk_delete_transactions(db, user_id, []) == 0


async def test_upsert_merchant_rule_is_scoped_per_user(db, user_id):
    """Regression test: the agent router used to look up Merchant by name only
    (no user_id filter), so two different users' rules for a merchant with the
    same name could clobber each other. upsert_merchant_rule must be scoped."""
    acct = await _make_account(db, user_id)
    other_acct = await _make_account(db, "other-user", name="Other Bank")
    cat_mine = await _make_category(db, user_id, "Transport")
    cat_theirs = await _make_category(db, "other-user", "Shopping")
    await db.commit()

    await transaction_service.upsert_merchant_rule(db, "other-user", "SBB", None, cat_theirs.id)
    await db.commit()
    await transaction_service.upsert_merchant_rule(db, user_id, "SBB", None, cat_mine.id)
    await db.commit()

    from sqlalchemy import select as _select
    rows = (await db.execute(_select(Merchant).where(Merchant.name == "SBB"))).scalars().all()
    assert len(rows) == 2
    by_user = {r.user_id: r for r in rows}
    assert by_user[user_id].default_category_id == cat_mine.id
    assert by_user["other-user"].default_category_id == cat_theirs.id
