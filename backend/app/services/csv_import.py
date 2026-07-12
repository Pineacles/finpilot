"""Import Swiss bank statements: CSV and camt.053 XML.

CSV: Valiant Bank format (Datum;Buchungstext;Betrag;Saldo;Valuta)
  - Limited detail: "Vergütung" entries are batched without recipient info
  - TWINT shows merchant/person name

camt.053 XML: ISO 20022 (preferred)
  - Individual entries with creditor/debtor name and address
  - Much better for e-banking payments (each "Vergütung" is broken out)
"""
import csv
import io
import logging
import re
from datetime import date, datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Transaction, Category
from app.models.account import Account
from app.services.categorize import categorize_transaction, batch_categorize_with_ai
from app.services.seed_merchants import seed_merchants
from app.services.camt053 import parse_camt053, parse_statement_period
from app.services import classifier
from app.services import settlement as settlement_service

logger = logging.getLogger(__name__)


def parse_valiant_csv(content: str) -> list[dict]:
    """Parse Valiant Bank CSV export."""
    lines = content.strip().split("\n")

    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith("Datum;Buchungstext;Betrag"):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Could not find header row (Datum;Buchungstext;Betrag;Saldo;Valuta)")

    reader = csv.reader(lines[header_idx + 1:], delimiter=";")
    transactions = []

    for row in reader:
        if len(row) < 3 or not row[0].strip():
            continue

        date_str = row[0].strip()
        description = row[1].strip()
        amount_str = row[2].strip()

        if not date_str or not description or not amount_str:
            continue

        try:
            if len(date_str.split(".")[-1]) == 2:
                txn_date = datetime.strptime(date_str, "%d.%m.%y").date()
            else:
                txn_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue

        try:
            amount = float(amount_str.replace("'", "").replace(",", "."))
        except ValueError:
            continue

        transactions.append({
            "date": txn_date,
            "description": description,
            "amount": amount,
            "currency": "CHF",
            "counterparty": "",
        })

    return transactions


def parse_viseca_csv(content: str) -> list[dict]:
    """Parse Viseca One CSV/TSV export from my.viseca.ch."""
    lines = content.strip().split("\n")
    if not lines:
        return []

    # Detect delimiter: tab, semicolon, or comma
    header = lines[0]
    if "\t" in header:
        delimiter = "\t"
    elif ";" in header:
        delimiter = ";"
    elif "," in header and header.count(",") >= 5:
        delimiter = ","
    else:
        # No standard delimiter: log for debugging
        import logging
        logging.getLogger(__name__).warning(
            f"Viseca CSV: no tab/semicolon/comma found in header. "
            f"First 100 chars: {repr(header[:100])}"
        )
        # Last resort: treat multiple spaces as delimiter
        lines = [re.sub(r"  +", "\t", line) for line in lines]
        delimiter = "\t"

    reader = csv.DictReader(lines, delimiter=delimiter)
    transactions = []

    for row in reader:
        txn_id = row.get("TransactionId", "").strip()
        date_str = row.get("Date", "").strip()
        amount_str = row.get("Amount", "").strip()
        currency = row.get("Currency", "CHF").strip()
        merchant = row.get("MerchantName", "").strip()
        place = row.get("MerchantPlace", "").strip()
        details = row.get("Details", "").strip()
        state = row.get("StateType", "").strip()
        orig_amount_str = row.get("OriginalAmount", "").strip()
        orig_currency = row.get("OriginalCurrency", "").strip()
        txn_type = row.get("Type", "").strip()

        # Skip non-booked transactions
        if state and state not in ("BOOKED", "BILLED"):
            continue

        if not date_str or not amount_str:
            continue

        # Parse date: "18/02/2026 00:12" or "18/02/2026"
        try:
            txn_date = datetime.strptime(date_str.split(" ")[0], "%d/%m/%Y").date()
        except ValueError:
            try:
                txn_date = datetime.strptime(date_str.split(" ")[0], "%Y-%m-%d").date()
            except ValueError:
                continue

        try:
            raw_amount = float(amount_str.replace("'", "").replace(",", "."))
        except ValueError:
            continue

        # Negative amounts in Viseca = payments you made to pay off the bill
        # Positive amounts = purchases (expenses)
        if raw_amount < 0:
            # Bill payment ("Ihre Zahlung - Danke"): this is a credit (positive in our system)
            amount = abs(raw_amount)
        else:
            # Purchase: expense (negative in our system)
            amount = -abs(raw_amount)

        orig_amount = None
        if orig_amount_str:
            try:
                orig_amount = float(orig_amount_str.replace("'", "").replace(",", "."))
            except ValueError:
                pass

        # Use Details for richer description, MerchantName as merchant
        description = details or merchant
        if place:
            description = f"{description} - {place}"

        # Determine merchant name and payment type for special rows
        payment_type = "CCRD"
        merchant_name = merchant or details or "Unknown"

        # Viseca fees and bill payments (no CardId, no merchant)
        if "ihre zahlung" in (details or "").lower():
            merchant_name = "Viseca Bill Payment"
            payment_type = "transfer"
        elif "verzugszins" in (details or "").lower():
            merchant_name = "Viseca Late Interest"
            payment_type = "fee"
        elif "bearbeitungsgebühr" in (details or "").lower() or "rechnungsgebühr" in (details or "").lower():
            merchant_name = "Viseca Fee"
            payment_type = "fee"

        transactions.append({
            "date": txn_date,
            "description": description,
            "merchant": merchant_name,
            "amount": amount,
            "currency": currency,
            "original_amount": orig_amount,
            "original_currency": orig_currency if orig_currency != currency else None,
            "reference": txn_id,
            "counterparty": merchant_name,
            "payment_type": payment_type,
        })

    return transactions


def parse_postfinance_csv(content: str) -> list[dict]:
    """Parse PostFinance CSV export (semicolon-separated, metadata header rows).

    Format:
      - Lines 1-6: metadata (Datum von, Datum bis, Kategorie, Konto, Währung, blank)
      - Line 7: actual column header: Datum;Bewegungstyp;Avisierungstext;Gutschrift in CHF;Lastschrift in CHF;Label;Kategorie
      - Lines 8+: data
    """
    lines = content.strip().split("\n")

    # Find the header row containing "Avisierungstext"
    header_idx = None
    for i, line in enumerate(lines):
        if "Avisierungstext" in line:
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("PostFinance CSV: could not find header row with 'Avisierungstext'")

    data_lines = [lines[header_idx]] + lines[header_idx + 1:]
    reader = csv.DictReader(data_lines, delimiter=";")
    transactions = []

    for row in reader:
        date_str = (row.get("Datum") or "").strip()
        description = (row.get("Avisierungstext") or "").strip().strip('"')
        credit_str = (row.get("Gutschrift in CHF") or "").strip()
        debit_str = (row.get("Lastschrift in CHF") or "").strip()
        pf_category = (row.get("Kategorie") or "").strip()

        if not date_str or (not credit_str and not debit_str):
            continue

        # Parse date: DD.MM.YYYY
        try:
            txn_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue

        # Amount: credit is positive, debit is negative
        amount = 0.0
        try:
            if credit_str:
                amount = float(credit_str.replace("'", "").replace(",", "."))
            elif debit_str:
                amount = float(debit_str.replace("'", "").replace(",", "."))
                if amount > 0:
                    amount = -amount  # ensure debit is negative
        except ValueError:
            continue

        # Extract merchant from description
        merchant = description
        # Common PostFinance patterns:
        # "KAUF/DIENSTLEISTUNG VOM DD.MM.YYYY KARTEN NR. XXXXNNNN MERCHANT_NAME LOCATION (CH)"
        # "PF PAY KAUF/ONLINE-SHOPPING VOM DD.MM.YYYY MERCHANT_NAME ..."
        # "TWINT GELD EMPFANGEN/GESENDET VOM DD.MM.YYYY ..."
        kauf_match = re.search(r"KARTEN NR\.\s*\S+\s+(.+?)(?:\s+\(CH\)|\s+WAREN\s)", description)
        if kauf_match:
            merchant = kauf_match.group(1).strip()
        else:
            pfpay_match = re.search(r"PF PAY KAUF/\S+\s+VOM\s+\S+\s+(.+?)(?:\s+N/A|\s+PAYMENT)", description)
            if pfpay_match:
                merchant = pfpay_match.group(1).strip()
            elif "TWINT" in description:
                twint_match = re.search(r"(?:VON|AN)\s+TELEFON-NR\.\s*\S+\s+(.+?)(?:\s+MITTEILUNGEN:|\s*$)", description)
                if twint_match:
                    merchant = twint_match.group(1).strip()
                else:
                    merchant = "TWINT"

        # Build a reference for dedup using hash of full description
        import hashlib
        desc_hash = hashlib.md5(description.encode()).hexdigest()[:12]
        ref = f"pf-{date_str}-{amount}-{desc_hash}"

        transactions.append({
            "date": txn_date,
            "description": description,
            "merchant": merchant,
            "amount": amount,
            "currency": "CHF",
            "original_amount": None,
            "original_currency": None,
            "reference": ref,
            "counterparty": merchant,
            "payment_type": "",
            "pf_category": pf_category,  # PostFinance's own category (useful as hint)
        })

    return transactions


def detect_format(content: str) -> str:
    """Detect file format."""
    stripped = content.strip()
    if stripped.startswith("<?xml") or stripped.startswith("<Document") or "<BkToCstmrStmt>" in stripped:
        return "camt053"
    if "TransactionId" in content and "MerchantName" in content:
        return "viseca"
    if "Avisierungstext" in content and ("Gutschrift" in content or "Lastschrift" in content):
        return "postfinance"
    if "Buchungstext" in content and "Betrag" in content:
        return "valiant"
    if "Datum" in content and "Saldo" in content:
        return "valiant"
    return "unknown"


async def import_transactions(
    db: AsyncSession,
    user_id: str,
    account_id: str,
    content: str,
    use_ai: bool = True,
    pre_parsed: list[dict] | None = None,
    opening_balance: float | None = None,
    source_format: str | None = None,
) -> dict:
    """Import transactions from CSV, PDF, or camt.053 with auto-categorization."""
    log: list[dict] = []

    def _log(msg: str, detail: str = ""):
        log.append({"msg": msg, "detail": detail})

    if pre_parsed is not None:
        # Pre-parsed transactions (e.g. from PDF, or the generic column-mapper)
        raw_transactions = pre_parsed
        fmt = source_format or "postfinance_pdf"
        _log(f"Detected format: {fmt}")
    else:
        fmt = detect_format(content)
        _log(f"Detected format: {fmt}")

        if fmt == "viseca":
            raw_transactions = parse_viseca_csv(content)
        elif fmt == "camt053":
            raw_transactions = parse_camt053(content)
        elif fmt == "valiant":
            raw_transactions = parse_valiant_csv(content)
        elif fmt == "postfinance":
            raw_transactions = parse_postfinance_csv(content)
        else:
            raise ValueError("Unsupported file format. Use Valiant CSV, PostFinance CSV/PDF, or camt.053 XML.")

    _log(f"Parsed {len(raw_transactions)} transactions from file")

    # If we have an opening balance, add it as the first transaction
    if opening_balance is not None and raw_transactions:
        earliest_date = min(t["date"] for t in raw_transactions)
        from datetime import timedelta
        # Find Transfer category
        from app.models.finance import Category
        cat_result = await db.execute(
            select(Category).where(and_(Category.user_id == user_id, Category.name == "Transfer"))
        )
        transfer_cat = cat_result.scalar_one_or_none()

        opening_txn = Transaction(
            user_id=user_id,
            account_id=account_id,
            date=earliest_date - timedelta(days=1),
            merchant="Opening Balance",
            amount=opening_balance,
            currency="CHF",
            category_id=transfer_cat.id if transfer_cat else None,
            notes="Opening balance from PostFinance statement",
        )
        db.add(opening_txn)
        await db.flush()
        _log(f"Added opening balance: CHF {opening_balance:.2f}")

    imported = 0
    skipped = 0
    uncategorized_txns = []
    imported_txns = []

    # Build a set of existing references for fast dedup
    existing_refs = set()
    result = await db.execute(
        select(Transaction.viseca_transaction_id).where(
            Transaction.user_id == user_id,
            Transaction.viseca_transaction_id.isnot(None),
        )
    )
    existing_refs = {r[0] for r in result.all()}
    if existing_refs:
        _log(f"Loaded {len(existing_refs)} existing references for dedup")

    # Categorization stats per method
    method_counts: dict[str, int] = {}

    for raw in raw_transactions:
        desc = raw["description"]
        ref = raw.get("reference", "")
        has_ref = bool(ref) and ref != "NOTPROVIDED"

        # Primary dedup: by reference (AcctSvcrRef / viseca_transaction_id)
        if has_ref and ref in existing_refs:
            skipped += 1
            continue

        # Secondary dedup: date + amount + merchant (catches re-imports).
        # A row with an unseen bank reference can still duplicate a row
        # imported earlier from a reference-less source (Valiant CSV), but
        # if the existing row carries a DIFFERENT reference it is a distinct
        # transaction (e.g. two identical TWINT payments the same day), so
        # a referenced row only fuzzy-matches reference-less rows.
        merchant_hint = raw.get("merchant", desc[:30])
        fuzzy_conditions = [
            Transaction.user_id == user_id,
            Transaction.date == raw["date"],
            Transaction.amount == raw["amount"],
            Transaction.merchant == merchant_hint,
        ]
        if has_ref:
            fuzzy_conditions.append(Transaction.viseca_transaction_id.is_(None))
        existing = await db.execute(select(Transaction).where(and_(*fuzzy_conditions)))
        fuzzy_dup = existing.scalars().first()
        if fuzzy_dup:
            if has_ref:
                # Attach the reference so future imports hit the primary dedup
                fuzzy_dup.viseca_transaction_id = ref
                existing_refs.add(ref)
            skipped += 1
            continue

        # Tertiary dedup: date + amount + description notes (catches same txn with different merchant extraction)
        if desc:
            notes_conditions = [
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.date == raw["date"],
                Transaction.amount == raw["amount"],
                Transaction.notes.ilike(f"%{desc[:30]}%"),
            ]
            if has_ref:
                notes_conditions.append(Transaction.viseca_transaction_id.is_(None))
            existing2 = await db.execute(select(Transaction).where(and_(*notes_conditions)))
            notes_dup = existing2.scalars().first()
            if notes_dup:
                if has_ref:
                    notes_dup.viseca_transaction_id = ref
                    existing_refs.add(ref)
                skipped += 1
                continue

        # Categorize with full context
        cat_id, merchant_name, method, confidence = await categorize_transaction(
            db, user_id, desc, raw["amount"],
            counterparty=raw.get("counterparty", ""),
            payment_method=raw.get("payment_type", ""),
        )

        method_counts[method] = method_counts.get(method, 0) + 1

        # Store the full original description as notes for reference
        notes_parts = []
        if desc and desc != merchant_name:
            notes_parts.append(desc)
        addr = raw.get("counterparty_address", "")
        if addr:
            notes_parts.append(addr)
        notes = " | ".join(notes_parts) if notes_parts else None
        if notes and len(notes) > 490:
            notes = notes[:490]

        # Check for pending transaction from email notification (match by date + amount)
        pending_result = await db.execute(
            select(Transaction).where(and_(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.date == raw["date"],
                Transaction.amount == raw["amount"],
                Transaction.merchant == "Pending",
            ))
        )
        pending_txn = pending_result.scalar_one_or_none()

        txn = None
        if pending_txn:
            # Upgrade pending transaction with real details
            pending_txn.merchant = merchant_name
            pending_txn.category_id = cat_id
            pending_txn.viseca_transaction_id = ref if has_ref else None
            pending_txn.notes = notes
            txn = pending_txn
            imported += 1
            imported_txns.append(pending_txn)
            method_counts["upgraded"] = method_counts.get("upgraded", 0) + 1
        else:
            txn = Transaction(
                user_id=user_id,
                account_id=account_id,
                date=raw["date"],
                merchant=merchant_name,
                amount=raw["amount"],
                currency=raw.get("currency", "CHF"),
                original_amount=raw.get("original_amount"),
                original_currency=raw.get("original_currency"),
                category_id=cat_id,
                viseca_transaction_id=ref if has_ref else None,
                notes=notes,
            )
            db.add(txn)
            try:
                await db.flush()
            except Exception:
                # Duplicate reference: skip gracefully
                await db.rollback()
                skipped += 1
                continue
            imported += 1
            imported_txns.append(txn)

        if not cat_id and txn:
            uncategorized_txns.append({
                "id": txn.id,
                "description": desc,
                "amount": raw["amount"],
                "merchant": merchant_name,
            })

    # ── Prune stale placeholders inside the statement period ───────────
    # The statement is authoritative for the period it covers. Email
    # notifications create "Pending" placeholders whose booking date rarely
    # matches the email date (so the exact-match upgrade above misses most),
    # and older imports can leave "Unknown" rows the bank later dropped.
    # Any placeholder in the covered period that this statement does not
    # corroborate (its reference is absent from the statement) is stale and
    # removed. Rows created or upgraded by this very import are kept, as is
    # any referenced row the statement confirms (a real booked transaction
    # whose merchant extraction merely failed).
    period_start = period_end = None
    if fmt == "camt053" and content:
        period_start, period_end = parse_statement_period(content)
    if raw_transactions:
        row_dates = [t["date"] for t in raw_transactions]
        period_start = period_start or min(row_dates)
        period_end = period_end or max(row_dates)

    pruned = 0
    if period_start and period_end:
        statement_refs = {
            t.get("reference") for t in raw_transactions
            if t.get("reference") and t.get("reference") != "NOTPROVIDED"
        }
        imported_ids = {t.id for t in imported_txns}
        placeholder_result = await db.execute(
            select(Transaction).where(and_(
                Transaction.user_id == user_id,
                Transaction.account_id == account_id,
                Transaction.date >= period_start,
                Transaction.date <= period_end,
                Transaction.merchant.in_(("Pending", "Unknown")),
            ))
        )
        for placeholder in placeholder_result.scalars().all():
            if placeholder.id in imported_ids:
                continue
            if placeholder.viseca_transaction_id and placeholder.viseca_transaction_id in statement_refs:
                continue
            await db.delete(placeholder)
            pruned += 1

    if pruned:
        _log(
            f"Pruned {pruned} stale placeholder transactions (Pending/Unknown) "
            f"not present in the statement period {period_start} to {period_end}"
        )

    if skipped:
        _log(f"Skipped {skipped} duplicate transactions")

    _log(f"Imported {imported} transactions")

    # Log categorization breakdown
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        label = {"keyword": "Keyword match", "merchant_db": "Merchant DB", "history": "History", "classifier": "ML Classifier", "unmatched": "Unmatched", "upgraded": "Upgraded from email"}.get(method, method)
        _log(f"  {label}: {count}", "categorized" if method != "unmatched" else "pending")

    # Batch AI categorization for unknowns, deduplicated by merchant
    ai_categorized = 0
    if use_ai and uncategorized_txns:
        # Group by merchant: only send 1 per unique merchant to AI
        merchant_groups: dict[str, list[dict]] = {}
        for t in uncategorized_txns:
            key = t["merchant"].lower()
            merchant_groups.setdefault(key, []).append(t)

        unique_merchants = []
        for key, group in merchant_groups.items():
            unique_merchants.append(group[0])  # representative

        total_uncat = len(uncategorized_txns)
        unique_count = len(unique_merchants)
        _log(
            f"AI categorization: {total_uncat} uncategorized → {unique_count} unique merchants",
            f"saved {total_uncat - unique_count} AI calls by dedup" if total_uncat > unique_count else "",
        )

        ai_results = await batch_categorize_with_ai(db, user_id, unique_merchants)

        # Build merchant → category mapping from AI results
        merchant_cat_map: dict[str, dict] = {}
        for r in ai_results:
            if r["category_id"] and r["confidence"] >= 0.6:
                # Find the merchant name from the representative txn
                for t in unique_merchants:
                    if t["id"] == r["id"]:
                        merchant_cat_map[t["merchant"].lower()] = r
                        break

        # Apply to ALL transactions with matching merchant
        for t in uncategorized_txns:
            r = merchant_cat_map.get(t["merchant"].lower())
            if r:
                result = await db.execute(
                    select(Transaction).where(Transaction.id == t["id"])
                )
                txn = result.scalar_one_or_none()
                if txn:
                    txn.category_id = r["category_id"]
                    ai_categorized += 1

        # Log AI results per merchant
        ai_matched = 0
        ai_failed = 0
        for r in ai_results:
            conf = r.get("confidence", 0)
            # Find merchant name for this result
            m_name = next((t["merchant"] for t in unique_merchants if t["id"] == r["id"]), "?")
            cat_name = r.get("category_name", "?")
            group_size = len(merchant_groups.get(m_name.lower(), []))
            if r.get("category_id") and conf >= 0.6:
                ai_matched += 1
                suffix = f" (×{group_size})" if group_size > 1 else ""
                _log(f"  ✓ {m_name} → {cat_name} ({conf:.0%}){suffix}")
            else:
                ai_failed += 1
                _log(f"  ✗ {m_name} → {cat_name} ({conf:.0%})", "low confidence or unknown category")

        _log(f"AI: {ai_matched} merchants matched ({ai_categorized} txns), {ai_failed} unresolved")
    else:
        _log("AI: skipped (no uncategorized or AI disabled)")

    # ── Credit-card settlement auto-reset ───────────────────────────
    # Piggybacks on the dedup above: only transactions newly inserted (or
    # upgraded from a "Pending" placeholder) in *this* import are examined,
    # never existing rows, so re-importing the same file is a no-op here
    # too (nothing new to settle).
    settlement_results: list[dict] = []
    if imported_txns:
        account_result = await db.execute(select(Account).where(Account.id == account_id))
        source_account = account_result.scalar_one_or_none()
        if source_account is not None:
            settlement_results = await settlement_service.detect_and_settle(
                db, user_id, source_account, imported_txns,
            )
            for r in settlement_results:
                if r["skipped"]:
                    _log(
                        f"Settlement match on {r['card_account_name']} but balance already CHF 0.00: no reset needed",
                        "settlement",
                    )
                else:
                    _log(
                        f"Detected {r['card_account_name']} settlement of CHF {r['settled_amount']:.2f} "
                        f"→ credit card reset to 0",
                        "settlement",
                    )

    await db.commit()

    categorized = sum(1 for t in imported_txns if t.category_id) + ai_categorized
    still_uncategorized = imported - categorized

    # Train/retrain ML classifier on all categorized data. The import itself
    # is already committed at this point; classifier training is an
    # optimization and must never turn a successful import into an error.
    _log("Training ML classifier on categorized data...")
    try:
        train_result = await classifier.train_classifier(db, user_id)
        if train_result["status"] == "trained":
            _log(f"  Classifier trained: {train_result['samples']} samples, {train_result['categories']} categories")
        else:
            _log(f"  Classifier: {train_result.get('reason', 'skipped')}")
    except Exception as e:
        logger.warning(f"Classifier training failed after import: {e}")
        _log(f"  Classifier training failed (import unaffected): {e}")

    _log(f"Done: {categorized} categorized, {still_uncategorized} uncategorized")

    return {
        "format": fmt,
        "imported": imported,
        "skipped": skipped,
        "categorized": categorized,
        "uncategorized": still_uncategorized,
        "pruned": pruned,
        "total_rows": len(raw_transactions),
        "log": log,
        "settlements": settlement_results,
    }
