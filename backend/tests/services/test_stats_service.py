"""stats_service: transfer-category exclusion from income/expense aggregates.

Regression test for the dead "Viseca Bill Payment" exclusion: that name was
only ever used as a *merchant*, never a *category*, so the old
`Category.name.in_(["Transfer", "Viseca Bill Payment"])` filter silently
never matched the second name. The category that actually gets assigned to
Viseca settlement transactions is "Transfer" — this test locks that in.
"""
from __future__ import annotations

from datetime import date

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.services import stats_service


async def _make_account(db, user_id: str) -> Account:
    acct = Account(user_id=user_id, name="Bank", type="bank", currency="CHF")
    db.add(acct)
    await db.flush()
    return acct


async def _make_category(db, user_id: str, name: str) -> Category:
    cat = Category(user_id=user_id, name=name, type="expense")
    db.add(cat)
    await db.flush()
    return cat


async def test_transfer_category_excluded_from_monthly_income_expense(db, user_id):
    acct = await _make_account(db, user_id)
    transfer_cat = await _make_category(db, user_id, "Transfer")
    groceries_cat = await _make_category(db, user_id, "Groceries")
    await db.commit()

    db.add_all([
        # A large outgoing "Viseca" settlement payment, categorized Transfer —
        # must NOT count as an expense.
        Transaction(
            user_id=user_id, account_id=acct.id, date=date(2026, 1, 10),
            merchant="Viseca Bill Payment", amount=-500.0, currency="CHF",
            category_id=transfer_cat.id,
        ),
        # A real expense — must count.
        Transaction(
            user_id=user_id, account_id=acct.id, date=date(2026, 1, 12),
            merchant="Migros", amount=-50.0, currency="CHF",
            category_id=groceries_cat.id,
        ),
    ])
    await db.commit()

    result = await stats_service.monthly_stats(db, user_id, year=2026, month=1)

    assert result["summary"]["expenses"] == 50.0
    assert result["summary"]["txn_count"] == 1
    # The Transfer-categorized row must not show up in the per-category breakdown either.
    assert [c["name"] for c in result["categories"]] == ["Groceries"]


async def test_transfer_category_excluded_from_yearly_income_expense(db, user_id):
    acct = await _make_account(db, user_id)
    transfer_cat = await _make_category(db, user_id, "Transfer")
    await db.commit()

    db.add_all([
        Transaction(
            user_id=user_id, account_id=acct.id, date=date(2026, 3, 1),
            merchant="Viseca Bill Payment", amount=-500.0, currency="CHF",
            category_id=transfer_cat.id,
        ),
        Transaction(
            user_id=user_id, account_id=acct.id, date=date(2026, 3, 2),
            merchant="Employer", amount=6000.0, currency="CHF",
        ),
    ])
    await db.commit()

    result = await stats_service.yearly_stats(db, user_id, year=2026)

    assert result["summary"]["income"] == 6000.0
    assert result["summary"]["expenses"] == 0.0


async def test_a_category_literally_named_viseca_bill_payment_is_not_special_cased(db, user_id):
    """Belt-and-suspenders: TRANSFER_CATEGORY_NAMES no longer references the
    dead "Viseca Bill Payment" name, so a category that happened to be named
    that would NOT be excluded (it never legitimately occurs as a category in
    practice — merchant names and category names are different concepts)."""
    assert "Viseca Bill Payment" not in stats_service.TRANSFER_CATEGORY_NAMES
    assert stats_service.TRANSFER_CATEGORY_NAMES == ["Transfer"]
