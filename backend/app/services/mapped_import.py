"""Generic CSV column-mapper import.

For any CSV export FinPilot doesn't already know how to parse (Cumulus card
exports, a new bank, etc.), the user maps columns once (date/amount/
description, or debit+credit split) via POST /api/import/csv/preview then
POST /api/import/csv/mapped, optionally saving the mapping as a reusable
ImportProfile. The mapped rows are converted into the same `raw transaction
dict` shape the other parsers in services/csv_import.py produce, then handed
to `import_transactions(..., pre_parsed=...)` so dedup, categorization, and
credit-card settlement detection all run identically regardless of source
format.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime

ENCODINGS = ("utf-8-sig", "utf-8", "iso-8859-1", "cp1252")

PREVIEW_ROWS = 10

DELIMITER_CANDIDATES = [";", ",", "\t", "|"]


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Decode raw file bytes, trying encodings in the same order the rest of
    the app uses. Returns (text, encoding_used)."""
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError("Could not decode file")


def sniff_delimiter(sample: str) -> str:
    """Detect the CSV delimiter. Falls back to counting candidate delimiters
    in the header line when csv.Sniffer can't decide (common with single-
    column or unusually-quoted exports)."""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="".join(DELIMITER_CANDIDATES))
        return dialect.delimiter
    except csv.Error:
        pass
    header_line = sample.split("\n", 1)[0]
    counts = {d: header_line.count(d) for d in DELIMITER_CANDIDATES}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def preview_csv(raw: bytes, max_rows: int = PREVIEW_ROWS) -> dict:
    """Sniff delimiter/encoding and return the header + first `max_rows` data
    rows, for the frontend's column-mapping UI."""
    text, encoding = decode_bytes(raw)
    stripped = text.strip()
    if not stripped:
        return {"columns": [], "rows": [], "delimiter": ",", "encoding": encoding}

    delimiter = sniff_delimiter(stripped)
    reader = csv.reader(io.StringIO(stripped), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return {"columns": [], "rows": [], "delimiter": delimiter, "encoding": encoding}

    columns = [c.strip() for c in rows[0]]
    data_rows = []
    for row in rows[1:1 + max_rows]:
        data_rows.append({columns[i]: (row[i] if i < len(row) else "") for i in range(len(columns))})

    return {"columns": columns, "rows": data_rows, "delimiter": delimiter, "encoding": encoding}


_PAREN_NEGATIVE = re.compile(r"^\((.*)\)$")


def parse_swiss_amount(raw: str, decimal_separator: str = ".") -> float:
    """Parse a Swiss-formatted amount string.

    Handles:
      - apostrophe thousands separators: 1'234.50
      - comma decimal separator (decimal_separator=","): 1'234,50 / 1.234,50
      - negative in parentheses: (123.45)
      - negative with trailing minus: 123.45-
      - leading minus: -123.45
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty amount")

    negative = False

    paren = _PAREN_NEGATIVE.match(s)
    if paren:
        negative = True
        s = paren.group(1).strip()

    if s.endswith("-"):
        negative = True
        s = s[:-1].strip()

    if s.startswith("-"):
        negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    s = s.replace("'", "").replace("’", "").replace(" ", "").replace(" ", "")

    if decimal_separator == ",":
        # Thousands "." (if any) then decimal ","
        s = s.replace(".", "").replace(",", ".")
    else:
        # Thousands "," (if any), decimal "."
        s = s.replace(",", "")

    if not s:
        raise ValueError(f"could not parse amount: {raw!r}")

    value = float(s)
    return -value if negative else value


class ColumnMapping:
    """Plain container mirroring app.schemas.import_profile.ColumnMapping,
    kept import-free here so this module has no dependency on pydantic
    schemas; the endpoint layer converts."""

    def __init__(
        self,
        date_col: str,
        amount_col: str | None = None,
        description_col: str | None = None,
        debit_col: str | None = None,
        credit_col: str | None = None,
        date_format: str = "%d.%m.%Y",
        decimal_separator: str = ".",
        invert_amount: bool = False,
        currency: str = "CHF",
    ):
        self.date_col = date_col
        self.amount_col = amount_col
        self.description_col = description_col
        self.debit_col = debit_col
        self.credit_col = credit_col
        self.date_format = date_format
        self.decimal_separator = decimal_separator
        self.invert_amount = invert_amount
        self.currency = currency

        if not amount_col and not (debit_col or credit_col):
            raise ValueError("Provide amount_col, or debit_col/credit_col")


def parse_mapped_csv(raw: bytes, mapping: ColumnMapping) -> list[dict]:
    """Parse an arbitrary CSV using an explicit column mapping into the
    common `raw transaction dict` shape used by services/csv_import.py's
    other parsers (date, description, merchant, amount, currency,
    counterparty)."""
    text, _encoding = decode_bytes(raw)
    stripped = text.strip()
    if not stripped:
        return []

    delimiter = sniff_delimiter(stripped)
    reader = csv.DictReader(io.StringIO(stripped), delimiter=delimiter)

    transactions: list[dict] = []
    for row in reader:
        row = {(k.strip() if k else k): v for k, v in row.items()}

        date_str = (row.get(mapping.date_col) or "").strip()
        if not date_str:
            continue
        try:
            txn_date = datetime.strptime(date_str, mapping.date_format).date()
        except ValueError:
            continue

        try:
            if mapping.debit_col or mapping.credit_col:
                credit_raw = (row.get(mapping.credit_col) or "").strip() if mapping.credit_col else ""
                debit_raw = (row.get(mapping.debit_col) or "").strip() if mapping.debit_col else ""
                if credit_raw:
                    amount = abs(parse_swiss_amount(credit_raw, mapping.decimal_separator))
                elif debit_raw:
                    amount = -abs(parse_swiss_amount(debit_raw, mapping.decimal_separator))
                else:
                    continue
            else:
                amount_raw = (row.get(mapping.amount_col) or "").strip()
                if not amount_raw:
                    continue
                amount = parse_swiss_amount(amount_raw, mapping.decimal_separator)
        except ValueError:
            continue

        if mapping.invert_amount:
            amount = -amount

        description = (row.get(mapping.description_col) or "").strip() if mapping.description_col else ""
        merchant = description or "Unknown"

        transactions.append({
            "date": txn_date,
            "description": description,
            "merchant": merchant,
            "amount": amount,
            "currency": mapping.currency,
            "counterparty": merchant,
        })

    return transactions
