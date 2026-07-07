"""Credit-card settlement auto-reset — detection, shared balance math,
idempotency across re-imports, and correctness across two consecutive
settlement cycles with card purchases in between.

Exercises the *real* import pipeline (services.csv_import.import_transactions)
against a synthetic camt.053 file, since settlement detection is wired in
there (piggybacking on its existing dedup) rather than called directly.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.services import account_service, settlement, stats_service
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants
from sqlalchemy import select, and_


def _camt053(amount: str, booking_date: str, ref: str, creditor: str = "Cembra Money Bank AG") -> str:
    """Minimal (no-namespace) camt.053 XML with a single outgoing (DBIT)
    ICDT entry — enough for services/camt053.parse_camt053 to extract a
    negative bank transaction whose merchant is the creditor name."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document>
  <BkToCstmrStmt>
    <Stmt>
      <Acct>
        <Ownr><Nm>Test User</Nm></Ownr>
        <Ccy>CHF</Ccy>
      </Acct>
      <Ntry>
        <Amt>{amount}</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>{booking_date}</Dt></BookgDt>
        <ValDt><Dt>{booking_date}</Dt></ValDt>
        <AcctSvcrRef>{ref}</AcctSvcrRef>
        <BkTxCd>
          <Domn>
            <Cd>PMNT</Cd>
            <Fmly>
              <Cd>ICDT</Cd>
              <SubFmlyCd>OTHR</SubFmlyCd>
            </Fmly>
          </Domn>
        </BkTxCd>
        <NtryDtls>
          <TxDtls>
            <Refs><AcctSvcrRef>{ref}</AcctSvcrRef></Refs>
            <RltdPties>
              <Cdtr><Nm>{creditor}</Nm></Cdtr>
            </RltdPties>
            <RmtInf><Ustrd>Kreditkartenabrechnung Cumulus</Ustrd></RmtInf>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""


async def _setup(db, user_id):
    bank = Account(user_id=user_id, name="Valiant Bank", type="bank", currency="CHF")
    card = Account(user_id=user_id, name="Cumulus Card", type="credit_card", currency="CHF")
    db.add_all([bank, card])
    await db.flush()
    await seed_merchants(db, user_id)
    await db.commit()
    return bank, card


async def _add_card_purchase(db, user_id, card_id, d: date, amount: float, merchant="Shop"):
    t = Transaction(user_id=user_id, account_id=card_id, date=d, merchant=merchant, amount=amount, currency="CHF")
    db.add(t)
    await db.flush()
    await db.commit()
    return t


async def test_settlement_detected_from_camt053_import(db, user_id):
    bank, card = await _setup(db, user_id)

    # Card has CHF 1000 of purchases, no anchor yet -> naive sum balance = -1000
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 5), -400, "Migros")
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 20), -600, "Coop")

    xml = _camt053("1000.00", "2026-01-31", "REF-JAN")
    result = await import_transactions(db, user_id, bank.id, xml, use_ai=False)

    assert result["imported"] == 1
    assert len(result["settlements"]) == 1
    settle = result["settlements"][0]
    assert settle["skipped"] is False
    assert settle["settled_amount"] == pytest.approx(1000.0)
    assert settle["card_account_id"] == card.id

    # Import log surfaces the human-readable settlement line
    assert any("Cumulus" in l["msg"] and "1000.00" in l["msg"] for l in result["log"])

    # Bank txn categorized Transfer
    bank_txn = (await db.execute(
        select(Transaction).where(Transaction.account_id == bank.id)
    )).scalar_one()
    transfer_cat = (await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == "Transfer"))
    )).scalar_one()
    assert bank_txn.category_id == transfer_cat.id

    # Offsetting "Statement payment" created on the card, dated the settlement date
    offset = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == card.id, Transaction.merchant == "Statement payment",
        ))
    )).scalar_one()
    assert offset.amount == pytest.approx(1000.0)
    assert offset.date == date(2026, 1, 31)
    assert offset.category_id == transfer_cat.id

    # Card balance reads exactly 0 right after settlement (shared anchor-aware fn)
    await db.refresh(card)
    balance = await account_service.compute_account_balance(db, user_id, card)
    assert balance == 0
    assert card.balance == 0
    assert card.balance_date.date() == date(2026, 1, 31)


async def test_two_consecutive_settlement_cycles_with_purchases_between(db, user_id):
    bank, card = await _setup(db, user_id)

    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 5), -400)
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 20), -600)

    r1 = await import_transactions(db, user_id, bank.id, _camt053("1000.00", "2026-01-31", "REF-JAN"), use_ai=False)
    assert r1["settlements"][0]["settled_amount"] == pytest.approx(1000.0)
    await db.refresh(card)
    assert await account_service.compute_account_balance(db, user_id, card) == 0

    # New purchases after the January anchor
    await _add_card_purchase(db, user_id, card.id, date(2026, 2, 3), -200)
    await _add_card_purchase(db, user_id, card.id, date(2026, 2, 18), -150)
    await db.refresh(card)
    assert await account_service.compute_account_balance(db, user_id, card) == pytest.approx(-350)

    r2 = await import_transactions(db, user_id, bank.id, _camt053("350.00", "2026-02-28", "REF-FEB"), use_ai=False)
    assert r2["settlements"][0]["settled_amount"] == pytest.approx(350.0)

    await db.refresh(card)
    balance_after_2 = await account_service.compute_account_balance(db, user_id, card)
    assert balance_after_2 == 0
    assert card.balance_date.date() == date(2026, 2, 28)

    # No double counting across the previous anchor: exactly 2 offsetting txns total
    offsets = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == card.id, Transaction.merchant == "Statement payment",
        ))
    )).scalars().all()
    assert len(offsets) == 2
    assert sorted(o.amount for o in offsets) == [350.0, 1000.0]


async def test_reimporting_same_bank_file_does_not_double_settle(db, user_id):
    bank, card = await _setup(db, user_id)
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 5), -1000)

    xml = _camt053("1000.00", "2026-01-31", "REF-JAN")
    r1 = await import_transactions(db, user_id, bank.id, xml, use_ai=False)
    assert r1["imported"] == 1
    assert len(r1["settlements"]) == 1

    # Re-import the identical file — existing dedup (by AcctSvcrRef) skips the
    # row entirely, so settlement detection never even runs on it again.
    r2 = await import_transactions(db, user_id, bank.id, xml, use_ai=False)
    assert r2["imported"] == 0
    assert r2["skipped"] == 1
    assert r2["settlements"] == []

    offsets = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == card.id, Transaction.merchant == "Statement payment",
        ))
    )).scalars().all()
    assert len(offsets) == 1

    bank_txns = (await db.execute(select(Transaction).where(Transaction.account_id == bank.id))).scalars().all()
    assert len(bank_txns) == 1


async def test_settlement_skips_when_card_balance_already_zero(db, user_id):
    bank, card = await _setup(db, user_id)
    # No purchases at all -> balance is already 0 (naive sum, no anchor)
    xml = _camt053("0.00", "2026-01-31", "REF-ZERO")
    # A zero-amount bank txn wouldn't be negative so let's use a tiny negative
    # settlement instead against a card with 0 existing balance.
    xml = _camt053("5.00", "2026-01-31", "REF-ZERO")
    result = await import_transactions(db, user_id, bank.id, xml, use_ai=False)
    assert len(result["settlements"]) == 1
    assert result["settlements"][0]["skipped"] is True
    assert result["settlements"][0]["settled_amount"] == 0.0

    # No offsetting transaction was created
    offsets = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == card.id, Transaction.merchant == "Statement payment",
        ))
    )).scalars().all()
    assert offsets == []


async def test_custom_settlement_patterns_used_when_configured(db, user_id):
    bank, card = await _setup(db, user_id)
    await account_service.update_settlement_patterns(db, user_id, card.id, ["mycard issuer co"])
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 5), -500)

    # Default patterns ("cembra"/"cumulus"/viseca) must NOT match now that a
    # custom pattern list is set and doesn't include them.
    xml_default = _camt053("500.00", "2026-01-31", "REF-1", creditor="Cembra Money Bank AG")
    result = await import_transactions(db, user_id, bank.id, xml_default, use_ai=False)
    assert result["settlements"] == []

    # But the account's own custom pattern does match
    xml_custom = _camt053("500.00", "2026-02-01", "REF-2", creditor="MyCard Issuer Co")
    result2 = await import_transactions(db, user_id, bank.id, xml_custom, use_ai=False)
    assert len(result2["settlements"]) == 1
    assert result2["settlements"][0]["settled_amount"] == pytest.approx(500.0)


async def test_settlement_transactions_excluded_from_stats(db, user_id):
    """Transfer-categorized settlement/offset entries must not pollute
    income/expense stats (stats_service already excludes category 'Transfer';
    this locks in that the settlement flow relies on that exclusion)."""
    bank, card = await _setup(db, user_id)
    await _add_card_purchase(db, user_id, card.id, date(2026, 1, 5), -1000)

    xml = _camt053("1000.00", "2026-01-31", "REF-JAN")
    await import_transactions(db, user_id, bank.id, xml, use_ai=False)

    stats = await stats_service.monthly_stats(db, user_id, year=2026, month=1)
    # Only the original CHF 1000 card purchase counts as a real expense —
    # neither the CHF 1000 bank payment (Transfer) nor the CHF 1000 card
    # offset (Transfer) should add to expenses/income.
    assert stats["summary"]["expenses"] == pytest.approx(1000.0)
    assert stats["summary"]["income"] == pytest.approx(0.0)
