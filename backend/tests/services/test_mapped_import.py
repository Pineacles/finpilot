"""Generic CSV column-mapper: Swiss amount parsing, preview sniffing, mapped
parsing (amount_col and debit/credit split), and end-to-end import through
the shared pipeline (dedup + settlement all apply identically)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select, and_

from app.models.account import Account
from app.models.finance import Transaction
from app.services import mapped_import
from app.services.csv_import import import_transactions
from app.services.seed_merchants import seed_merchants


# ── Swiss amount parsing ─────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("1'234.50", 1234.50),
    ("1234.50", 1234.50),
    ("-1'234.50", -1234.50),
    ("(123.45)", -123.45),
    ("123.45-", -123.45),
    ("+50.00", 50.00),
])
def test_parse_swiss_amount_dot_decimal(raw, expected):
    assert mapped_import.parse_swiss_amount(raw, ".") == pytest.approx(expected)


@pytest.mark.parametrize("raw,expected", [
    ("1'234,50", 1234.50),
    ("1.234,50", 1234.50),
    ("-1'234,50", -1234.50),
    ("(1.234,50)", -1234.50),
])
def test_parse_swiss_amount_comma_decimal(raw, expected):
    assert mapped_import.parse_swiss_amount(raw, ",") == pytest.approx(expected)


def test_parse_swiss_amount_empty_raises():
    with pytest.raises(ValueError):
        mapped_import.parse_swiss_amount("", ".")


# ── Preview / delimiter sniffing ──────────────────────────────────────

def test_preview_csv_semicolon():
    content = "Date;Amount;Description\n01.02.2026;-50.00;Migros\n02.02.2026;1200.00;Salary\n".encode("utf-8")
    preview = mapped_import.preview_csv(content)
    assert preview["columns"] == ["Date", "Amount", "Description"]
    assert preview["delimiter"] == ";"
    assert len(preview["rows"]) == 2
    assert preview["rows"][0]["Description"] == "Migros"


def test_preview_csv_comma_and_truncates_to_max_rows():
    header = "Date,Amount,Description\n"
    rows = "".join(f"0{i%9+1}.02.2026,-{i}.00,Shop{i}\n" for i in range(15))
    content = (header + rows).encode("utf-8")
    preview = mapped_import.preview_csv(content, max_rows=10)
    assert preview["delimiter"] == ","
    assert len(preview["rows"]) == 10


# ── Mapped parsing ────────────────────────────────────────────────────

def test_parse_mapped_csv_single_amount_column():
    content = (
        "Datum;Betrag;Text\n"
        "15.03.2026;-1'234.50;Kreditkartenabrechnung Cumulus\n"
        "16.03.2026;250.00;Gutschrift\n"
    ).encode("utf-8")
    mapping = mapped_import.ColumnMapping(
        date_col="Datum", amount_col="Betrag", description_col="Text",
        date_format="%d.%m.%Y", decimal_separator=".",
    )
    txns = mapped_import.parse_mapped_csv(content, mapping)
    assert len(txns) == 2
    assert txns[0]["date"] == date(2026, 3, 15)
    assert txns[0]["amount"] == pytest.approx(-1234.50)
    assert txns[0]["merchant"] == "Kreditkartenabrechnung Cumulus"
    assert txns[1]["amount"] == pytest.approx(250.0)


def test_parse_mapped_csv_debit_credit_split_and_invert():
    content = (
        "Date,Debit,Credit,Details\n"
        "01.04.2026,120.00,,Coop\n"
        "02.04.2026,,500.00,Salary\n"
    ).encode("utf-8")
    mapping = mapped_import.ColumnMapping(
        date_col="Date", debit_col="Debit", credit_col="Credit", description_col="Details",
        date_format="%d.%m.%Y",
    )
    txns = mapped_import.parse_mapped_csv(content, mapping)
    assert txns[0]["amount"] == pytest.approx(-120.0)  # debit -> negative
    assert txns[1]["amount"] == pytest.approx(500.0)  # credit -> positive

    inverted_mapping = mapped_import.ColumnMapping(
        date_col="Date", debit_col="Debit", credit_col="Credit", description_col="Details",
        date_format="%d.%m.%Y", invert_amount=True,
    )
    inverted = mapped_import.parse_mapped_csv(content, inverted_mapping)
    assert inverted[0]["amount"] == pytest.approx(120.0)
    assert inverted[1]["amount"] == pytest.approx(-500.0)


def test_parse_mapped_csv_requires_amount_or_debit_credit():
    with pytest.raises(ValueError):
        mapped_import.ColumnMapping(date_col="Date")


def test_parse_mapped_csv_skips_bad_rows():
    content = (
        "Date,Amount,Details\n"
        "not-a-date,10.00,Bad\n"
        "01.04.2026,,Empty amount\n"
        "02.04.2026,not-a-number,Bad amount\n"
        "03.04.2026,-10.00,Good\n"
    ).encode("utf-8")
    mapping = mapped_import.ColumnMapping(date_col="Date", amount_col="Amount", description_col="Details", date_format="%d.%m.%Y")
    txns = mapped_import.parse_mapped_csv(content, mapping)
    assert len(txns) == 1
    assert txns[0]["merchant"] == "Good"


# ── End-to-end: mapped import through the shared pipeline ────────────

async def test_mapped_csv_import_full_pipeline_and_dedup(db, user_id):
    bank = Account(user_id=user_id, name="Unknown Bank", type="bank", currency="CHF")
    db.add(bank)
    await db.flush()
    await seed_merchants(db, user_id)
    await db.commit()

    content = (
        "Datum;Betrag;Text\n"
        "15.03.2026;-1'234.50;Cumulus Card Payment\n"
        "16.03.2026;250.00;Salary Inc\n"
    ).encode("utf-8")
    mapping = mapped_import.ColumnMapping(
        date_col="Datum", amount_col="Betrag", description_col="Text",
        date_format="%d.%m.%Y", decimal_separator=".",
    )
    raw_transactions = mapped_import.parse_mapped_csv(content, mapping)

    result = await import_transactions(
        db, user_id, bank.id, "", use_ai=False, pre_parsed=raw_transactions, source_format="mapped_csv",
    )
    assert result["format"] == "mapped_csv"
    assert result["imported"] == 2

    # Re-importing the identical mapped rows dedups via the existing
    # date+amount+merchant / notes secondary checks — no duplicate rows.
    raw_transactions_2 = mapped_import.parse_mapped_csv(content, mapping)
    result2 = await import_transactions(
        db, user_id, bank.id, "", use_ai=False, pre_parsed=raw_transactions_2, source_format="mapped_csv",
    )
    assert result2["imported"] == 0
    assert result2["skipped"] == 2

    all_txns = (await db.execute(select(Transaction).where(Transaction.account_id == bank.id))).scalars().all()
    assert len(all_txns) == 2
