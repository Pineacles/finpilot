"""Import Swiss bank statements — CSV and camt.053 XML.

CSV: Valiant Bank format (Datum;Buchungstext;Betrag;Saldo;Valuta)
  - Limited detail: "Vergütung" entries are batched without recipient info
  - TWINT shows merchant/person name

camt.053 XML: ISO 20022 (preferred)
  - Individual entries with creditor/debtor name and address
  - Much better for e-banking payments (each "Vergütung" is broken out)
"""
import csv
import io
import re
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import Transaction
from app.models.account import Account
from app.services.categorize import categorize_transaction, batch_categorize_with_ai
from app.services.seed_merchants import seed_merchants
from app.services.camt053 import parse_camt053
from app.services import classifier


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


def detect_format(content: str) -> str:
    """Detect file format."""
    stripped = content.strip()
    if stripped.startswith("<?xml") or stripped.startswith("<Document") or "<BkToCstmrStmt>" in stripped:
        return "camt053"
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
) -> dict:
    """Import transactions from CSV or camt.053 with auto-categorization."""
    log: list[dict] = []

    def _log(msg: str, detail: str = ""):
        log.append({"msg": msg, "detail": detail})

    fmt = detect_format(content)
    _log(f"Detected format: {fmt}")

    if fmt == "camt053":
        raw_transactions = parse_camt053(content)
    elif fmt == "valiant":
        raw_transactions = parse_valiant_csv(content)
    else:
        raise ValueError("Unsupported file format. Use Valiant CSV or camt.053 XML.")

    _log(f"Parsed {len(raw_transactions)} transactions from file")

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

        # Primary dedup: by reference (AcctSvcrRef)
        if ref and ref != "NOTPROVIDED" and ref in existing_refs:
            skipped += 1
            continue

        # Secondary dedup: date + amount + description (for CSV imports without refs)
        if not ref or ref == "NOTPROVIDED":
            merchant_hint = raw.get("merchant", desc[:30])
            existing = await db.execute(
                select(Transaction).where(
                    Transaction.user_id == user_id,
                    Transaction.date == raw["date"],
                    Transaction.amount == raw["amount"],
                    Transaction.merchant == merchant_hint,
                )
            )
            if existing.scalar_one_or_none():
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

        txn = Transaction(
            user_id=user_id,
            account_id=account_id,
            date=raw["date"],
            merchant=merchant_name,
            amount=raw["amount"],
            currency=raw.get("currency", "CHF"),
            category_id=cat_id,
            viseca_transaction_id=ref if ref and ref != "NOTPROVIDED" else None,
            notes=" | ".join(notes_parts) if notes_parts else None,
        )
        db.add(txn)
        await db.flush()
        imported += 1
        imported_txns.append(txn)

        if not cat_id:
            uncategorized_txns.append({
                "id": txn.id,
                "description": desc,
                "amount": raw["amount"],
                "merchant": merchant_name,
            })

    if skipped:
        _log(f"Skipped {skipped} duplicate transactions")

    _log(f"Imported {imported} transactions")

    # Log categorization breakdown
    for method, count in sorted(method_counts.items(), key=lambda x: -x[1]):
        label = {"keyword": "Keyword match", "merchant_db": "Merchant DB", "history": "History", "classifier": "ML Classifier", "unmatched": "Unmatched"}.get(method, method)
        _log(f"  {label}: {count}", "categorized" if method != "unmatched" else "pending")

    # Batch AI categorization for unknowns — deduplicated by merchant
    ai_categorized = 0
    if use_ai and uncategorized_txns:
        # Group by merchant — only send 1 per unique merchant to AI
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

    await db.commit()

    categorized = sum(1 for t in imported_txns if t.category_id) + ai_categorized
    still_uncategorized = imported - categorized

    # Train/retrain ML classifier on all categorized data
    _log("Training ML classifier on categorized data...")
    train_result = await classifier.train_classifier(db, user_id)
    if train_result["status"] == "trained":
        _log(f"  Classifier trained: {train_result['samples']} samples, {train_result['categories']} categories")
    else:
        _log(f"  Classifier: {train_result.get('reason', 'skipped')}")

    _log(f"Done: {categorized} categorized, {still_uncategorized} uncategorized")

    return {
        "format": fmt,
        "imported": imported,
        "skipped": skipped,
        "categorized": categorized,
        "uncategorized": still_uncategorized,
        "total_rows": len(raw_transactions),
        "log": log,
    }
