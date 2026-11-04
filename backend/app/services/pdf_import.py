"""Parse PostFinance PDF bank statements (Kontoauszug).

Strategy: extract text line by line, then for lines with amounts, use word-level
x-coordinates to classify amounts as Gutschrift (credit) or Lastschrift (debit).
"""
import io
import re
import logging
from datetime import datetime
from collections import defaultdict

import pdfplumber

logger = logging.getLogger(__name__)

_DATE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{2})\s+(.+)")
_TXN_START = ("KAUF/", "LASTSCHRIFT", "PF PAY", "TWINT GELD", "GUTSCHRIFT",
              "PREIS FÜR", "PREIS FUR", "VERGÜTUNG")

# X thresholds for credit vs debit (from PDF layout)
X_CREDIT_ZONE = 340  # Gutschrift column center
X_DEBIT_ZONE = 420   # Lastschrift column center
X_AMOUNT_MIN = 300   # anything past this is an amount column


def parse_postfinance_pdf(raw_bytes: bytes) -> dict:
    pdf = pdfplumber.open(io.BytesIO(raw_bytes))

    # Step 1: Build per-page amount classification map
    # For each page, for each text-row top position, find if amounts are in credit or debit column
    amount_signs: dict[int, dict[float, str]] = {}  # page_idx -> {top -> "credit"|"debit"}

    for page_idx, page in enumerate(pdf.pages):
        words = page.extract_words(keep_blank_chars=True, x_tolerance=2, y_tolerance=2)
        amount_signs[page_idx] = {}
        for w in words:
            txt = w["text"].strip()
            if not txt:
                continue
            # Check if this looks like an amount (digits with possible space/dot)
            cleaned = txt.replace(" ", "").replace("'", "")
            if re.match(r"^\d+\.\d{2}$", cleaned) and w["x0"] > X_AMOUNT_MIN:
                top_key = round(w["top"])
                if w["x0"] < X_DEBIT_ZONE - 20:  # credit column
                    amount_signs[page_idx][top_key] = "credit"
                else:  # debit column
                    amount_signs[page_idx][top_key] = "debit"

    # Step 2: Extract text and parse line by line
    all_text_lines: list[tuple[int, str]] = []  # (page_idx, line)
    for page_idx, page in enumerate(pdf.pages):
        text = page.extract_text()
        if text:
            for line in text.split("\n"):
                all_text_lines.append((page_idx, line.strip()))

    # Step 3: Parse into transactions
    transactions_raw: list[dict] = []
    opening_balance = None
    closing_balance = None
    current_date = None
    in_table = False

    for page_idx, line in all_text_lines:
        if not line:
            continue

        # Detect table start
        if "Gutschrift" in line and "Lastschrift" in line and "Valuta" in line:
            in_table = True
            continue

        if not in_table:
            continue

        # Skip noise
        if line in ("00.630000", "ED", "65600") or line.startswith("Seite "):
            continue
        if "PostFinance" in line and "AG" in line:
            continue
        if line.startswith("Datum ") and ("IBAN" not in line):
            continue
        if line.startswith("IBAN ") or line.startswith("Kontonummer "):
            continue
        if line.startswith("Bitte überprüfen") or line.startswith("Freundliche"):
            continue

        # Check if line starts with a date
        date_match = _DATE_RE.match(line)

        if date_match:
            date_str = date_match.group(1)
            rest = date_match.group(2).strip()

            # Kontostand
            if "Kontostand" in rest:
                saldo = _extract_last_amount(rest)
                if saldo is not None:
                    if opening_balance is None:
                        opening_balance = saldo
                    closing_balance = saldo
                current_date = date_str
                continue

            # Total
            if rest.startswith("Total"):
                continue

            current_date = date_str

            # Check if this date line also starts a transaction
            starts_txn = any(rest.startswith(kw) for kw in _TXN_START)

            if starts_txn:
                amount, sign = _extract_amount_with_sign(rest, page_idx, amount_signs)
                transactions_raw.append({
                    "date_str": date_str,
                    "lines": [rest],
                    "amount": amount,
                    "sign": sign,
                })
            else:
                # Date line with a transaction that doesn't match keywords
                # (e.g., some direct descriptions)
                amount, sign = _extract_amount_with_sign(rest, page_idx, amount_signs)
                if amount is not None:
                    transactions_raw.append({
                        "date_str": date_str,
                        "lines": [rest],
                        "amount": amount,
                        "sign": sign,
                    })
                else:
                    # Might be a transaction with amount on a continuation line
                    transactions_raw.append({
                        "date_str": date_str,
                        "lines": [rest],
                        "amount": None,
                        "sign": None,
                    })

        elif any(line.startswith(kw) for kw in _TXN_START):
            # New transaction WITHOUT a date prefix (same date as previous)
            amount, sign = _extract_amount_with_sign(line, page_idx, amount_signs)
            transactions_raw.append({
                "date_str": current_date,
                "lines": [line],
                "amount": amount,
                "sign": sign,
            })
        elif transactions_raw:
            # Continuation line for current transaction
            transactions_raw[-1]["lines"].append(line)
            # If current txn has no amount, try to extract from this line
            if transactions_raw[-1]["amount"] is None:
                amount, sign = _extract_amount_with_sign(line, page_idx, amount_signs)
                if amount is not None:
                    transactions_raw[-1]["amount"] = amount
                    transactions_raw[-1]["sign"] = sign

    # Step 4: Convert to final format
    final = []
    for txn in transactions_raw:
        if txn["amount"] is None or txn["date_str"] is None:
            continue

        try:
            txn_date = datetime.strptime(txn["date_str"], "%d.%m.%y").date()
        except ValueError:
            continue

        # Apply sign
        amount = txn["amount"]
        if txn["sign"] == "credit":
            amount = abs(amount)
        elif txn["sign"] == "debit":
            amount = -abs(amount)
        else:
            # Fallback: guess from keywords
            full = " ".join(txn["lines"])
            if any(kw in full for kw in ("GUTSCHRIFT", "GELD EMPFANGEN", "LOHN", "GEHALT")):
                amount = abs(amount)
            else:
                amount = -abs(amount)

        full_desc = " ".join(txn["lines"])
        # Clean up: remove extracted amounts from description
        full_desc = re.sub(r"\s+\d[\d\s']*\.\d{2}\s+\d{2}\.\d{2}\.\d{2}.*$", "", full_desc).strip()

        merchant = _extract_merchant(full_desc)
        import hashlib
        desc_hash = hashlib.md5(full_desc.encode()).hexdigest()[:12]
        ref = f"pf-pdf-{txn_date.isoformat()}-{amount}-{desc_hash}"

        final.append({
            "date": txn_date,
            "description": full_desc,
            "merchant": merchant,
            "amount": amount,
            "currency": "CHF",
            "original_amount": None,
            "original_currency": None,
            "reference": ref,
            "counterparty": merchant,
            "payment_type": "",
        })

    logger.info(f"PostFinance PDF: {len(final)} txns parsed")

    return {
        "transactions": final,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
    }


def _extract_amount_with_sign(text: str, page_idx: int,
                               amount_signs: dict[int, dict[float, str]]) -> tuple[float | None, str | None]:
    """Extract the first amount from the line and determine credit/debit from x-position data."""
    # Find amounts in the text: patterns like 202.90, 1 147.36, 935.00
    amounts = re.findall(r"(?:^|\s)(\d[\d\s']*\.\d{2})(?:\s|$)", text)
    if not amounts:
        return None, None

    # Take the first amount that's purely numeric (not a date like 28.02.26)
    for a in amounts:
        cleaned = a.strip().replace(" ", "").replace("'", "")
        # Skip if it looks like a date (XX.XX.XX)
        if re.match(r"^\d{2}\.\d{2}\.\d{2}$", cleaned):
            continue
        try:
            val = float(cleaned)
        except ValueError:
            continue

        # Determine sign from the x-position map
        page_signs = amount_signs.get(page_idx, {})
        # Find a matching sign entry (approximate top match)
        sign = None
        for top, s in page_signs.items():
            # Can't precisely match, just return the first amount we find
            # and use keyword-based sign detection as fallback
            pass

        return val, sign

    return None, None


def _extract_last_amount(text: str) -> float | None:
    """Extract the last number from a line (used for Saldo/Kontostand)."""
    amounts = re.findall(r"(\d[\d\s']*\.\d{2})", text)
    if not amounts:
        return None
    cleaned = amounts[-1].strip().replace(" ", "").replace("'", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_merchant(text: str) -> str:
    """Extract merchant name from PostFinance transaction description."""
    m = re.search(r"KARTEN NR\.\s*\S+\s+(.+?)(?:\s+\(CH\)|\s+WAREN\s|\s*$)", text)
    if m:
        return m.group(1).strip()

    m = re.search(r"(?:PF PAY\s+)?KAUF/\S+\s+VOM\s+\S+\s+(.+?)(?:\s+N/A|\s+PAYMENT\s+ID|\s*$)", text)
    if m:
        return m.group(1).strip()

    if "LASTSCHRIFT" in text:
        m = re.search(r"LASTSCHRIFT\s+\S+\s+(.+?)(?:\s+\d{4}\s|\s+SENDER\s)", text)
        if m:
            return m.group(1).strip()

    if "TWINT" in text:
        m = re.search(r"(?:VON|AN)\s+TELEFON-NR\.\s*\S+\s+(.+?)(?:\s+MITTEILUNGEN:|\s*$)", text)
        if m:
            return m.group(1).strip()
        return "TWINT"

    if text.startswith("PREIS"):
        return text[:60]

    if "GUTSCHRIFT" in text or "AUFTRAGGEBER:" in text:
        m = re.search(r"AUFTRAGGEBER:\s+(.+?)(?:\s+REFERENZEN:|\s+\d{4}\s|\s*$)", text)
        if m:
            return m.group(1).strip()

    return text[:60]


# ── PostFinance Credit Card (Kreditkartenrechnung) ───────────────

def parse_postfinance_cc_pdf(raw_bytes: bytes) -> dict:
    """Parse a PostFinance credit card statement PDF."""
    pdf = pdfplumber.open(io.BytesIO(raw_bytes))
    all_text = ""
    for page in pdf.pages:
        text = page.extract_text()
        if text:
            all_text += text + "\n"
    pdf.close()

    lines = all_text.split("\n")

    # Extract summary: "1'035.05 0.00 64.98 1'100.05 301.00 1.65"
    saldo_old = None
    saldo_new = None
    for line in lines:
        amounts = re.findall(r"[\d']+\.\d{2}", line)
        if len(amounts) >= 4 and saldo_old is None:
            try:
                saldo_old = float(amounts[0].replace("'", ""))
                saldo_new = float(amounts[3].replace("'", ""))
            except ValueError:
                pass

    # Parse transactions
    in_txns = False
    transactions = []
    txn_re = re.compile(r"^(\d{2}\.\d{2}\.\d{2})\s+(?:(\d{2}\.\d{2}\.\d{2})\s+)?(.+?)\s+(-?[\d']+\.\d{2})$")

    for line in lines:
        line = line.strip()
        if "Buchung" in line and "Einkauf" in line and "Detail" in line:
            in_txns = True
            continue
        if not in_txns:
            continue
        if line.startswith("Total ") or line.startswith("¹") or line.startswith("Seite "):
            continue

        m = txn_re.match(line)
        if m:
            buchung = m.group(1)
            detail = m.group(3).strip()
            amount_str = m.group(4).replace("'", "")
            try:
                amount_chf = float(amount_str)
            except ValueError:
                continue
            try:
                txn_date = datetime.strptime(buchung, "%d.%m.%y").date()
            except ValueError:
                continue

            # Clean: remove trailing currency + original amount
            detail_clean = re.sub(r"\s+[A-Z]{3}\s+[\d'.]+$", "", detail).strip()

            # CC: positive = expense → store as negative; negative (with -) = refund → store as positive
            amount_chf = -amount_chf

            import hashlib
            desc_hash = hashlib.md5(detail.encode()).hexdigest()[:12]
            ref = f"pf-cc-{buchung}-{amount_chf}-{desc_hash}"
            transactions.append({
                "date": txn_date,
                "description": detail,
                "merchant": detail_clean,
                "amount": amount_chf,
                "currency": "CHF",
                "original_amount": None,
                "original_currency": None,
                "reference": ref,
                "counterparty": detail_clean,
                "payment_type": "CCRD",
            })

    logger.info(f"PostFinance CC PDF: {len(transactions)} txns, old={saldo_old}, new={saldo_new}")
    return {
        "transactions": transactions,
        "opening_balance": None,
        "closing_balance": saldo_new,
        "is_credit_card": True,
    }


# ── Auto-detect and dispatch ─────────────────────────────────────

def parse_postfinance_pdf_auto(raw_bytes: bytes) -> dict:
    """Auto-detect PostFinance PDF type (bank statement vs credit card) and parse."""
    pdf = pdfplumber.open(io.BytesIO(raw_bytes))
    sample = ""
    for page in pdf.pages[:2]:
        text = page.extract_text()
        if text:
            sample += text
    pdf.close()

    if "Kreditkartenrechnung" in sample or "Mastercard" in sample or "Kartenkonto" in sample:
        logger.info("Detected PostFinance Credit Card PDF")
        return parse_postfinance_cc_pdf(raw_bytes)
    else:
        logger.info("Detected PostFinance Bank Statement PDF")
        return parse_postfinance_pdf(raw_bytes)
