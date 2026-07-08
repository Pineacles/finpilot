"""CSV bank-statement import — Valiant and PostFinance parsing, format
detection, dedup on re-import, unsupported-format errors, and the
"Pending" (email-notification) transaction upgrade path.

Mirrors the conventions in test_settlement.py / test_mapped_import.py:
create Account rows via the ORM, seed_merchants(db, user_id) first, then
drive everything through the real app.services.csv_import.import_transactions
pipeline with use_ai=False (fully offline).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, and_

from app.models.account import Account
from app.models.finance import Transaction
from app.services import csv_import
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants


async def _bank(db, user_id, name="Valiant Bank") -> Account:
    bank = Account(user_id=user_id, name=name, type="bank", currency="CHF")
    db.add(bank)
    await db.flush()
    await seed_merchants(db, user_id)
    await db.commit()
    return bank


VALIANT_CSV = (
    "Datum;Buchungstext;Betrag;Saldo;Valuta\n"
    "15.03.26;Zahlung - Migros Zuerich;-25.90;1234.56;15.03.26\n"
    "16.03.2026;Globex Industries Wage;3'250.75;8250.75;16.03.2026\n"
)


# ── Valiant CSV happy path ─────────────────────────────────────────────

async def test_valiant_csv_happy_path(db, user_id):
    bank = await _bank(db, user_id)

    result = await import_transactions(db, user_id, bank.id, VALIANT_CSV, use_ai=False)

    assert result["format"] == "valiant"
    assert result["imported"] == 2
    assert result["skipped"] == 0

    row1 = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == bank.id, Transaction.date == date(2026, 3, 15),
        ))
    )).scalar_one()
    assert row1.amount == pytest.approx(-25.90)
    # Merchant-DB match: canonical merchant name, not the raw description.
    assert row1.merchant == "Migros"

    row2 = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == bank.id, Transaction.date == date(2026, 3, 16),
        ))
    )).scalar_one()
    assert row2.amount == pytest.approx(3250.75)  # 3'250.75 thousands-sep parsed
    assert row2.merchant == "Globex Industries Wage"


# ── PostFinance CSV happy path ─────────────────────────────────────────

POSTFINANCE_CSV = (
    "Datum von: 01.03.2026\n"
    "Datum bis: 31.03.2026\n"
    "Kategorie: Alle\n"
    "Konto: 01-234567-8\n"
    "Währung: CHF\n"
    "\n"
    "Datum;Bewegungstyp;Avisierungstext;Gutschrift in CHF;Lastschrift in CHF;Label;Kategorie\n"
    "05.03.2026;Gutschrift;Globex Industries Wage;5000.00;;;Lohn\n"
    "10.03.2026;Lastschrift;Kauf Migros Store;;89.50;;Einkauf\n"
)


async def test_postfinance_csv_happy_path(db, user_id):
    bank = await _bank(db, user_id, name="PostFinance")

    result = await import_transactions(db, user_id, bank.id, POSTFINANCE_CSV, use_ai=False)

    assert result["format"] == "postfinance"
    assert result["imported"] == 2

    credit = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == bank.id, Transaction.date == date(2026, 3, 5),
        ))
    )).scalar_one()
    assert credit.amount == pytest.approx(5000.00)
    assert credit.merchant == "Globex Industries Wage"

    debit = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == bank.id, Transaction.date == date(2026, 3, 10),
        ))
    )).scalar_one()
    assert debit.amount == pytest.approx(-89.50)
    # Merchant-DB fuzzy/substring match on "migros" inside the description.
    assert debit.merchant == "Migros"


# ── Dedup on reimport ───────────────────────────────────────────────────

async def test_reimporting_same_valiant_csv_dedups_every_row(db, user_id):
    bank = await _bank(db, user_id)

    r1 = await import_transactions(db, user_id, bank.id, VALIANT_CSV, use_ai=False)
    assert r1["imported"] == 2

    r2 = await import_transactions(db, user_id, bank.id, VALIANT_CSV, use_ai=False)
    assert r2["imported"] == 0
    assert r2["skipped"] == 2

    all_txns = (await db.execute(
        select(Transaction).where(Transaction.account_id == bank.id)
    )).scalars().all()
    assert len(all_txns) == 2


# ── Unknown format ───────────────────────────────────────────────────────

def test_detect_format_unknown_for_garbage_text():
    assert csv_import.detect_format("garbage content, not a bank file") == "unknown"


async def test_import_unknown_format_raises_value_error(db, user_id):
    bank = await _bank(db, user_id)
    with pytest.raises(ValueError):
        await import_transactions(db, user_id, bank.id, "garbage content, not a bank file", use_ai=False)


# ── Pending-transaction upgrade path ────────────────────────────────────

async def test_import_upgrades_matching_pending_transaction_in_place(db, user_id):
    bank = await _bank(db, user_id)

    pending = Transaction(
        user_id=user_id, account_id=bank.id,
        date=date(2026, 3, 15), merchant="Pending", amount=-25.90, currency="CHF",
    )
    db.add(pending)
    await db.flush()
    await db.commit()
    pending_id = pending.id

    single_row_csv = (
        "Datum;Buchungstext;Betrag;Saldo;Valuta\n"
        "15.03.26;Zahlung - Migros Zuerich;-25.90;1234.56;15.03.26\n"
    )
    result = await import_transactions(db, user_id, bank.id, single_row_csv, use_ai=False)
    assert result["imported"] == 1

    all_txns = (await db.execute(
        select(Transaction).where(Transaction.account_id == bank.id)
    )).scalars().all()
    assert len(all_txns) == 1

    upgraded = all_txns[0]
    assert upgraded.id == pending_id  # same row reused, not a new one
    assert upgraded.merchant == "Migros"
    assert upgraded.merchant != "Pending"
    assert upgraded.amount == pytest.approx(-25.90)
