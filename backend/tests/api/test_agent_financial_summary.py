"""agent_finance_router.financial_summary: Transfer-categorized transactions
must not inflate income/expenses/categories/budget-spent, matching the
dashboard stats (stats_service). Account balances still include transfers,
since a transfer really does move money in or out of the account.

Endpoint handler called directly (no HTTP transport), matching the pattern
in tests/api/test_agent_scoping.py.
"""
from __future__ import annotations

from datetime import date

from app.api.endpoints.agent_finance_router import financial_summary
from app.models.account import Account
from app.models.finance import Budget, Category, Transaction


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


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


async def test_transfer_excluded_from_income_expenses_and_txn_count(db, user_id):
    acct = await _make_account(db, user_id)
    transfer_cat = await _make_category(db, user_id, "Transfer")
    groceries_cat = await _make_category(db, user_id, "Groceries")
    await db.commit()

    today = date.today()
    month_start = today.replace(day=1)

    db.add_all([
        # Viseca settlement: internal money movement, must not count as expense.
        Transaction(
            user_id=user_id, account_id=acct.id, date=month_start,
            merchant="Viseca Bill Payment", amount=-500.0, currency="CHF",
            category_id=transfer_cat.id,
        ),
        # A person-to-person reimbursement categorized Transfer: must not
        # count as income.
        Transaction(
            user_id=user_id, account_id=acct.id, date=month_start,
            merchant="Anna Suter", amount=50.0, currency="CHF",
            category_id=transfer_cat.id,
        ),
        # Real expense and real income, must count.
        Transaction(
            user_id=user_id, account_id=acct.id, date=month_start,
            merchant="Migros", amount=-50.0, currency="CHF",
            category_id=groceries_cat.id,
        ),
        Transaction(
            user_id=user_id, account_id=acct.id, date=month_start,
            merchant="Employer", amount=6000.0, currency="CHF",
        ),
    ])
    await db.commit()

    result = await financial_summary(user=FakeUser(user_id), db=db)

    assert result["income"] == 6000.0
    assert result["expenses"] == 50.0
    assert result["net"] == 5950.0
    assert result["txn_count"] == 2
    assert [c["name"] for c in result["categories"]] == ["Groceries"]


async def test_transfer_excluded_from_budget_spent_all_categories(db, user_id):
    """A budget with category_id=None ("all spending") must still drop
    Transfer rows from its spent total."""
    acct = await _make_account(db, user_id)
    transfer_cat = await _make_category(db, user_id, "Transfer")
    await db.commit()

    today = date.today()
    month_start = today.replace(day=1)

    budget = Budget(
        user_id=user_id, name="Overall", amount=1000.0,
        period="monthly", start_date=month_start, category_id=None,
    )
    db.add(budget)
    db.add(Transaction(
        user_id=user_id, account_id=acct.id, date=month_start,
        merchant="Viseca Bill Payment", amount=-500.0, currency="CHF",
        category_id=transfer_cat.id,
    ))
    db.add(Transaction(
        user_id=user_id, account_id=acct.id, date=month_start,
        merchant="Coop", amount=-30.0, currency="CHF",
    ))
    await db.commit()

    result = await financial_summary(user=FakeUser(user_id), db=db)

    assert len(result["budgets"]) == 1
    assert result["budgets"][0]["spent"] == 30.0


async def test_account_balance_still_includes_transfers(db, user_id):
    """Balances are a raw sum of every transaction on the account: a
    transfer really does move money, unlike income/expense aggregates."""
    acct = await _make_account(db, user_id)
    transfer_cat = await _make_category(db, user_id, "Transfer")
    await db.commit()

    today = date.today()
    month_start = today.replace(day=1)

    db.add(Transaction(
        user_id=user_id, account_id=acct.id, date=month_start,
        merchant="Viseca Bill Payment", amount=-500.0, currency="CHF",
        category_id=transfer_cat.id,
    ))
    await db.commit()

    result = await financial_summary(user=FakeUser(user_id), db=db)

    assert result["accounts"] == [{"name": "Bank", "type": "bank", "balance": -500.0}]
