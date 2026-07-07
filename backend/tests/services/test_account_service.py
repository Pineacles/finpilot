"""account_service: shared anchor-aware balance computation + settlement pattern CRUD."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.account import Account
from app.models.finance import Transaction
from app.services import account_service
from app.services.account_service import AccountNotFoundError


async def _make_account(db, user_id: str, type_: str = "bank", name: str = "Bank", **kwargs) -> Account:
    acct = Account(user_id=user_id, name=name, type=type_, currency="CHF", **kwargs)
    db.add(acct)
    await db.flush()
    return acct


async def _add_txn(db, user_id: str, account_id: str, d: date, amount: float, merchant: str = "X"):
    t = Transaction(user_id=user_id, account_id=account_id, date=d, merchant=merchant, amount=amount, currency="CHF")
    db.add(t)
    await db.flush()
    return t


async def test_balance_no_anchor_naive_sum(db, user_id):
    acct = await _make_account(db, user_id)
    await _add_txn(db, user_id, acct.id, date(2026, 1, 1), -50)
    await _add_txn(db, user_id, acct.id, date(2026, 1, 2), 100)
    await db.commit()

    balance = await account_service.compute_account_balance(db, user_id, acct)
    assert balance == 50


async def test_balance_anchor_plus_txns_after_date(db, user_id):
    acct = await _make_account(
        db, user_id, balance=1000.0, balance_date=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    # Before/on anchor date -> excluded
    await _add_txn(db, user_id, acct.id, date(2025, 12, 31), -500)
    await _add_txn(db, user_id, acct.id, date(2026, 1, 1), -999)
    # After anchor date -> included
    await _add_txn(db, user_id, acct.id, date(2026, 1, 2), -100)
    await _add_txn(db, user_id, acct.id, date(2026, 1, 3), 20)
    await db.commit()

    balance = await account_service.compute_account_balance(db, user_id, acct)
    assert balance == 1000 - 100 + 20


async def test_balance_anchor_no_date_is_just_anchor(db, user_id):
    acct = await _make_account(db, user_id, balance=250.0)
    await _add_txn(db, user_id, acct.id, date(2026, 1, 1), -1000)
    await db.commit()

    balance = await account_service.compute_account_balance(db, user_id, acct)
    assert balance == 250.0


async def test_get_credit_card_accounts_scoped(db, user_id):
    cc = await _make_account(db, user_id, type_="credit_card", name="Cumulus")
    await _make_account(db, user_id, type_="bank", name="Valiant")
    await _make_account(db, "other-user", type_="credit_card", name="Other Cumulus")
    await db.commit()

    cards = await account_service.get_credit_card_accounts(db, user_id)
    assert [c.id for c in cards] == [cc.id]


async def test_update_settlement_patterns(db, user_id):
    cc = await _make_account(db, user_id, type_="credit_card", name="Cumulus")
    await db.commit()

    updated = await account_service.update_settlement_patterns(
        db, user_id, cc.id, ["Cembra AG", " Cumulus Card "]
    )
    assert updated.settlement_patterns == ["cembra ag", "cumulus card"]

    # Clearing goes back to None (defaults apply)
    cleared = await account_service.update_settlement_patterns(db, user_id, cc.id, None)
    assert cleared.settlement_patterns is None


async def test_update_settlement_patterns_rejects_non_credit_card(db, user_id):
    bank = await _make_account(db, user_id, type_="bank", name="Valiant")
    await db.commit()
    with pytest.raises(ValueError):
        await account_service.update_settlement_patterns(db, user_id, bank.id, ["cembra"])


async def test_update_settlement_patterns_scoped_to_owner(db, user_id):
    cc = await _make_account(db, "other-user", type_="credit_card", name="Cumulus")
    await db.commit()
    with pytest.raises(AccountNotFoundError):
        await account_service.update_settlement_patterns(db, user_id, cc.id, ["cembra"])
