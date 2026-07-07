"""Credit-card settlement auto-reset.

The user's credit card is Migros Cumulus, issued by Cembra; the bank
(Valiant) sees the monthly card-bill payment as one outgoing transaction.
When a bank-statement import contains such a payment, this module:

  1. categorizes the bank-side transaction as "Transfer" (already excluded
     from stats — see services/stats_service.py),
  2. matches it to the user's credit_card account via configurable
     `settlement_patterns` (Account.settlement_patterns; defaults to
     DEFAULT_SETTLEMENT_PATTERNS when unset),
  3. computes that card's *current* balance using the exact anchor-aware
     algorithm in services/account_service.compute_account_balance (shared
     with the dashboard overview, so the two can never diverge),
  4. creates an offsetting "Statement payment" transaction on the card
     account (amount = -balance) dated on the settlement date, and moves
     the card's balance anchor to 0 as of that date.

Because the offsetting transaction is dated *on* the settlement date and
compute_account_balance only sums transactions dated *strictly after* the
anchor date, the offsetting transaction itself is correctly excluded from
the post-reset balance — the card reads exactly 0 right after settlement,
and later purchases accumulate again from a clean anchor.

This is only ever invoked (from services/csv_import.import_transactions)
with the list of transactions *newly inserted* in the current import batch
— it never rescans existing rows. Idempotency therefore piggybacks entirely
on the existing import dedup: re-importing the same bank file inserts
nothing new, so this function isn't even called with anything to settle.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.finance import Category, Transaction
from app.services.account_service import compute_account_balance

logger = logging.getLogger(__name__)

# Default issuer-match keywords (lower-cased). Used for any credit_card
# account that has no custom Account.settlement_patterns configured.
DEFAULT_SETTLEMENT_PATTERNS: list[str] = [
    "cembra",
    "cumulus",
    "migros bank cumulus",
    "viseca payment services",
    "viseca card services",
]

STATEMENT_PAYMENT_MERCHANT = "Statement payment"

# Below this magnitude (CHF) a computed balance is treated as "already 0" —
# guards against float noise from repeated add/subtract.
ZERO_EPSILON = 0.005


def _effective_patterns(account: Account) -> list[str]:
    if account.settlement_patterns:
        return [p.lower() for p in account.settlement_patterns if p]
    return DEFAULT_SETTLEMENT_PATTERNS


def _matches_issuer(haystack: str, account: Account) -> bool:
    patterns = _effective_patterns(account)
    return any(p in haystack for p in patterns)


async def _get_transfer_category(db: AsyncSession, user_id: str) -> Category | None:
    result = await db.execute(
        select(Category).where(and_(Category.user_id == user_id, Category.name == "Transfer"))
    )
    return result.scalar_one_or_none()


async def detect_and_settle(
    db: AsyncSession,
    user_id: str,
    source_account: Account,
    new_transactions: list[Transaction],
) -> list[dict]:
    """Scan `new_transactions` (rows just inserted/upgraded by this import
    batch, on `source_account`) for credit-card settlement payments.

    Returns a list of result dicts, one per detected settlement, suitable
    for surfacing in the import response log. Never raises for a "balance
    already 0" case — that's logged and reported with skipped=True.
    """
    results: list[dict] = []
    if not new_transactions or source_account.type != "bank":
        return results

    card_result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.type == "credit_card"))
    )
    cards = list(card_result.scalars().all())
    if not cards:
        return results

    transfer_cat = await _get_transfer_category(db, user_id)

    for txn in new_transactions:
        if txn.amount is None or txn.amount >= 0:
            continue  # settlement payments are outgoing (negative) on the bank side

        haystack = f"{txn.merchant or ''} {txn.notes or ''}".lower()

        matched_card = next((c for c in cards if _matches_issuer(haystack, c)), None)
        if not matched_card:
            continue

        if transfer_cat:
            txn.category_id = transfer_cat.id

        balance = await compute_account_balance(db, user_id, matched_card)

        if abs(balance) < ZERO_EPSILON:
            logger.info(
                "Settlement match on card %s (txn %s) but balance already ~0 (%.2f) — skipping reset",
                matched_card.name, txn.id, balance,
            )
            results.append({
                "card_account_id": matched_card.id,
                "card_account_name": matched_card.name,
                "settled_amount": 0.0,
                "settlement_date": txn.date.isoformat(),
                "skipped": True,
            })
            continue

        offset_txn = Transaction(
            user_id=user_id,
            account_id=matched_card.id,
            date=txn.date,
            merchant=STATEMENT_PAYMENT_MERCHANT,
            amount=-balance,
            currency=matched_card.currency,
            category_id=transfer_cat.id if transfer_cat else None,
            notes=f"Auto-settlement from bank payment on {txn.date.isoformat()}",
        )
        db.add(offset_txn)
        await db.flush()

        matched_card.balance = 0.0
        matched_card.balance_date = datetime.combine(txn.date, datetime.min.time(), tzinfo=timezone.utc)

        results.append({
            "card_account_id": matched_card.id,
            "card_account_name": matched_card.name,
            "settled_amount": round(abs(balance), 2),
            "settlement_date": txn.date.isoformat(),
            "skipped": False,
        })

    return results
