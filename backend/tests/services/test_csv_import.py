"""CSV bank-statement import: Valiant and PostFinance parsing, format
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


# ── camt.053: referenced twins, ref-attach, placeholder pruning ─────────

def _camt(entries: list[dict], fr: str = "2026-03-01", to: str = "2026-03-31") -> str:
    """Minimal camt.053 statement with card-payment (CCRD/POSD) entries."""
    ntries = ""
    for e in entries:
        ind = "DBIT" if e["amount"] < 0 else "CRDT"
        ntries += (
            f'<Ntry><Amt Ccy="CHF">{abs(e["amount"]):.2f}</Amt><CdtDbtInd>{ind}</CdtDbtInd>'
            f'<Sts>BOOK</Sts><BookgDt><Dt>{e["date"]}</Dt></BookgDt><ValDt><Dt>{e["date"]}</Dt></ValDt>'
            f'<AcctSvcrRef>{e["ref"]}</AcctSvcrRef>'
            "<BkTxCd><Domn><Cd>PMNT</Cd><Fmly><Cd>CCRD</Cd><SubFmlyCd>POSD</SubFmlyCd></Fmly></Domn></BkTxCd>"
            f'<NtryDtls><TxDtls><Refs><AcctSvcrRef>{e["ref"]}</AcctSvcrRef></Refs>'
            f'<RmtInf><Ustrd>{e["desc"]}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.04"><BkToCstmrStmt>'
        "<GrpHdr><MsgId>MSG1</MsgId></GrpHdr><Stmt><Id>STMT1</Id>"
        f"<FrToDt><FrDtTm>{fr}T00:00:00</FrDtTm><ToDtTm>{to}T23:59:59</ToDtTm></FrToDt>"
        "<Acct><Id><IBAN>CH0000000000000000000</IBAN></Id><Ccy>CHF</Ccy>"
        "<Ownr><Nm>Test Owner</Nm></Ownr></Acct>"
        f"{ntries}</Stmt></BkToCstmrStmt></Document>"
    )


async def test_twin_transactions_with_distinct_references_both_import(db, user_id):
    """Two identical-looking payments (same day, amount, merchant) with
    different bank references are distinct transactions, not duplicates."""
    bank = await _bank(db, user_id)

    twins = _camt([
        {"date": "2026-03-10", "amount": -1.00, "ref": "ZV1/100/1",
         "desc": "TWINT Belastung Waschcenter 1 0400001111111111"},
        {"date": "2026-03-10", "amount": -1.00, "ref": "ZV1/200/1",
         "desc": "TWINT Belastung Waschcenter 1 0400002222222222"},
    ])
    result = await import_transactions(db, user_id, bank.id, twins, use_ai=False)

    assert result["format"] == "camt053"
    assert result["imported"] == 2
    assert result["skipped"] == 0


async def test_referenced_row_attaches_ref_to_existing_referenceless_duplicate(db, user_id):
    """A statement row that fuzzy-matches a row imported from a
    reference-less source (Valiant CSV) is skipped, and the bank reference
    is attached so future imports dedup by reference."""
    bank = await _bank(db, user_id)

    old = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 3, 10),
        merchant="Waschcenter 1", amount=-1.00, currency="CHF",
    )
    db.add(old)
    await db.commit()

    stmt = _camt([
        {"date": "2026-03-10", "amount": -1.00, "ref": "ZV1/100/1",
         "desc": "TWINT Belastung Waschcenter 1 0400001111111111"},
    ])
    result = await import_transactions(db, user_id, bank.id, stmt, use_ai=False)

    assert result["imported"] == 0
    assert result["skipped"] == 1
    await db.refresh(old)
    assert old.viseca_transaction_id == "ZV1/100/1"


async def test_statement_prunes_stale_placeholders_even_when_all_rows_skip(db, user_id):
    """Live regression: re-importing a statement skipped all rows, so the old
    purge (keyed on newly imported dates) never ran and Gmail "Pending"
    placeholders survived forever. The statement is authoritative for its
    FrToDt period: uncorroborated Pending/Unknown rows in it must go."""
    bank = await _bank(db, user_id)

    stmt = _camt(
        [{"date": "2026-03-10", "amount": -25.00, "ref": "ZV1/100/1",
          "desc": "TWINT Belastung Waschcenter 1 0400001111111111"}],
        fr="2026-03-01", to="2026-03-31",
    )
    first = await import_transactions(db, user_id, bank.id, stmt, use_ai=False)
    assert first["imported"] == 1

    in_period_pending = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 3, 12),
        merchant="Pending", amount=-30.00, currency="CHF",
        notes="Email notification | debit CHF 30.00",
    )
    stale_unknown = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 3, 15),
        merchant="Unknown", amount=-9.90, currency="CHF",
        viseca_transaction_id="ZV9/999/1",  # not in the statement
    )
    corroborated_unknown = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 3, 20),
        merchant="Unknown", amount=-5.00, currency="CHF",
        viseca_transaction_id="ZV1/300/1",  # confirmed by the statement below
    )
    out_of_period_pending = Transaction(
        user_id=user_id, account_id=bank.id, date=date(2026, 4, 2),
        merchant="Pending", amount=-12.00, currency="CHF",
    )
    db.add_all([in_period_pending, stale_unknown, corroborated_unknown, out_of_period_pending])
    await db.commit()

    stmt2 = _camt(
        [
            {"date": "2026-03-10", "amount": -25.00, "ref": "ZV1/100/1",
             "desc": "TWINT Belastung Waschcenter 1 0400001111111111"},
            {"date": "2026-03-20", "amount": -5.00, "ref": "ZV1/300/1",
             "desc": "-  - 20.03.2026 12:00 - Karten-Nr. 535445******0000"},
        ],
        fr="2026-03-01", to="2026-03-31",
    )
    second = await import_transactions(db, user_id, bank.id, stmt2, use_ai=False)

    assert second["imported"] == 0  # both rows already known
    assert second["pruned"] == 2  # in-period Pending + stale Unknown

    remaining = (await db.execute(
        select(Transaction).where(and_(
            Transaction.account_id == bank.id,
            Transaction.merchant.in_(("Pending", "Unknown")),
        ))
    )).scalars().all()
    remaining_keys = {(t.merchant, t.date) for t in remaining}
    assert remaining_keys == {
        ("Unknown", date(2026, 3, 20)),  # corroborated by statement ref: kept
        ("Pending", date(2026, 4, 2)),   # outside the statement period: kept
    }


# ── Classifier failures must never fail an import ───────────────────────

async def test_import_succeeds_when_classifier_persistence_denied(db, user_id, monkeypatch, tmp_path):
    """Regression: a root-owned /data/models volume raised PermissionError in
    joblib.dump, which aborted the whole statement import AFTER transactions
    were committed (the UI showed failure for a successful import)."""
    from app.services import classifier as clf

    readonly_dir = tmp_path / "models"
    readonly_dir.mkdir()
    readonly_dir.chmod(0o555)
    monkeypatch.setattr(clf, "MODEL_DIR", readonly_dir)

    bank = await _bank(db, user_id)
    result = await import_transactions(db, user_id, bank.id, VALIANT_CSV, use_ai=False)
    assert result["imported"] == 2


async def test_import_succeeds_when_classifier_training_explodes(db, user_id, monkeypatch):
    """Even an unexpected error inside training must not fail the import."""
    from app.services import classifier as clf

    async def boom(*a, **k):
        raise RuntimeError("classifier exploded")

    monkeypatch.setattr(clf, "train_classifier", boom)

    bank = await _bank(db, user_id)
    result = await import_transactions(db, user_id, bank.id, VALIANT_CSV, use_ai=False)
    assert result["imported"] == 2
