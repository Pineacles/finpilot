"""Transaction categorization engine: keyword map, merchant-DB fuzzy
match, income default, history fallback, and the AI batch path's
hermetic early-return when no AI backend is configured.

Follows test_settlement.py / test_mapped_import.py conventions: real ORM
rows via Account/Transaction/Category, seed_merchants(db, user_id) for
the category tree + merchant DB, and no network calls anywhere.
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, and_

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.services import categorize
from app.services.categorize import batch_categorize_with_ai, categorize_transaction
from app.services.seed_merchants import seed_merchants


async def _category(db, user_id, name: str) -> Category:
    result = await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == name))
    )
    return result.scalar_one()


async def test_direct_keyword_match_resolves_rent(db, user_id):
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Miete Wohnung Oktober", -1800.0,
    )

    rent = await _category(db, user_id, "Rent")
    assert method == "keyword"
    assert cat_id == rent.id
    assert confidence == pytest.approx(1.0)


async def test_merchant_db_fuzzy_match_resolves_migros(db, user_id):
    await seed_merchants(db, user_id)

    # Misspelled merchant name (typo: "Migeos"), must not match any
    # DIRECT_CATEGORY_MAP keyword, only the fuzzy merchant-DB pass.
    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Migeos Zuerich Hauptbahnhof", -15.30,
    )

    supermarket = await _category(db, user_id, "Supermarket")
    assert method == "merchant_db"
    assert cat_id == supermarket.id
    assert merchant_name == "Migros"  # canonical seeded merchant name, not the raw text


async def test_positive_amount_defaults_to_income(db, user_id):
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Vergütung Max Muster", 500.0,
    )

    income = await _category(db, user_id, "Income")
    assert method == "keyword"
    assert cat_id == income.id
    assert merchant_name == "Vergütung Max Muster"


async def test_positive_amount_with_gehalt_resolves_salary(db, user_id):
    await seed_merchants(db, user_id)

    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Gehaltszahlung März 2026", 6500.0,
    )

    salary = await _category(db, user_id, "Salary")
    assert method == "keyword"
    assert cat_id == salary.id


async def test_history_fallback_reuses_prior_categorization(db, user_id):
    await seed_merchants(db, user_id)
    bank = Account(user_id=user_id, name="Valiant Bank", type="bank", currency="CHF")
    db.add(bank)
    await db.flush()

    side_income = await _category(db, user_id, "Side Income")
    prior = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 2, 1),
        merchant="Acme Freelance Client", amount=750.0, currency="CHF",
        category_id=side_income.id,
    )
    db.add(prior)
    await db.flush()
    await db.commit()

    # Negative amount and a description that doesn't hit the keyword map or
    # merchant DB: only the exact merchant-name history match should fire.
    cat_id, merchant_name, method, confidence = await categorize_transaction(
        db, user_id, "Payment Acme Freelance Client Invoice 2026-04", -200.0,
        counterparty="Acme Freelance Client",
    )

    assert method == "history"
    assert cat_id == side_income.id
    assert merchant_name == "Acme Freelance Client"


async def test_batch_categorize_with_ai_short_circuits_without_backend(db, user_id, monkeypatch):
    """No ai_endpoint / anthropic_api_key configured -> early return [] before
    any network call. Proves the function never reaches _call_ai when no AI
    backend is configured, regardless of the real environment's settings."""

    async def _no_setting(db_arg, user_id_arg, key):
        return None

    async def _must_not_be_called(*args, **kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr(categorize, "get_setting", _no_setting)
    monkeypatch.setattr(categorize, "_call_ai", _must_not_be_called)

    result = await batch_categorize_with_ai(
        db, user_id,
        [{"id": "x", "merchant": "Some Unknown Shop", "description": "Some Unknown Shop", "amount": -10.0}],
    )

    assert result == []
