"""Recurring transaction detection.

Groups a user's transaction history by normalized merchant name and flags
groups that look like a recurring bill/subscription: at least 3 occurrences
at a roughly regular interval (weekly/monthly/yearly, within tolerance) and
similar amounts. Used to power "suggested" upcoming payments — the user (or
their agent) can accept a suggestion to turn it into a tracked
RecurringExpense, or dismiss it.

Detection is expense-only (Transaction.amount < 0): a "recurring expense" is
a recurring bill, not incoming salary etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean

from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.finance import RecurringExpense, Transaction

# (frequency name, nominal gap in days, tolerance in days)
_FREQUENCIES: list[tuple[str, int, int]] = [
    ("weekly", 7, 2),
    ("monthly", 30, 5),
    ("yearly", 365, 15),
]

AMOUNT_PCT_TOLERANCE = 0.10
AMOUNT_ABS_TOLERANCE = 2.0
MIN_OCCURRENCES = 3


@dataclass
class RecurringSuggestion:
    merchant: str
    amount: float
    currency: str
    frequency: str
    next_due_date: date
    last_date: date
    occurrences: int


def normalize_merchant(name: str) -> str:
    """Case/whitespace-insensitive key used to group transactions by merchant
    and to compare against existing RecurringExpense.name entries."""
    return name.strip().lower()


def _amounts_similar(amounts: list[float]) -> bool:
    if not amounts:
        return False
    avg = mean(amounts)
    tolerance = max(abs(avg) * AMOUNT_PCT_TOLERANCE, AMOUNT_ABS_TOLERANCE)
    return all(abs(a - avg) <= tolerance for a in amounts)


def _matching_frequency(gaps: list[int]) -> str | None:
    """Return a frequency name if every gap (days between consecutive
    occurrences, sorted ascending) falls within tolerance of the same
    candidate frequency; otherwise None (irregular — no suggestion)."""
    if not gaps:
        return None
    for name, nominal, tolerance in _FREQUENCIES:
        if all(abs(g - nominal) <= tolerance for g in gaps):
            return name
    return None


def _next_due_date(last: date, frequency: str) -> date:
    if frequency == "weekly":
        return last + relativedelta(weeks=1)
    if frequency == "yearly":
        return last + relativedelta(years=1)
    return last + relativedelta(months=1)


def detect_from_transactions(
    transactions: list[Transaction],
    existing_merchants: set[str],
) -> list[RecurringSuggestion]:
    """Pure grouping/detection over an already-fetched transaction list.

    `existing_merchants` is a set of normalized merchant names already
    tracked by a RecurringExpense — those groups are skipped so accepted
    recurring expenses aren't suggested again.
    """
    groups: dict[str, list[Transaction]] = {}
    for t in transactions:
        if t.amount >= 0:
            continue  # expenses only
        key = normalize_merchant(t.merchant)
        groups.setdefault(key, []).append(t)

    suggestions: list[RecurringSuggestion] = []
    for key, txns in groups.items():
        if key in existing_merchants:
            continue
        if len(txns) < MIN_OCCURRENCES:
            continue

        txns_sorted = sorted(txns, key=lambda t: t.date)
        dates = [t.date for t in txns_sorted]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

        frequency = _matching_frequency(gaps)
        if not frequency:
            continue

        amounts = [t.amount for t in txns_sorted]
        if not _amounts_similar(amounts):
            continue

        last = dates[-1]
        suggestions.append(RecurringSuggestion(
            merchant=txns_sorted[-1].merchant,
            amount=round(abs(mean(amounts)), 2),
            currency=txns_sorted[-1].currency,
            frequency=frequency,
            next_due_date=_next_due_date(last, frequency),
            last_date=last,
            occurrences=len(txns_sorted),
        ))

    suggestions.sort(key=lambda s: s.next_due_date)
    return suggestions


async def detect_recurring_expenses(db: AsyncSession, user_id: str) -> list[RecurringSuggestion]:
    """DB-backed entry point: fetch this user's transactions and already
    tracked RecurringExpenses, return detected suggestions excluding
    merchants already covered by an existing RecurringExpense."""
    txn_result = await db.execute(
        select(Transaction).where(Transaction.user_id == user_id)
    )
    transactions = list(txn_result.scalars().all())

    existing_result = await db.execute(
        select(RecurringExpense).where(RecurringExpense.user_id == user_id)
    )
    existing_merchants = {normalize_merchant(r.name) for r in existing_result.scalars().all()}

    return detect_from_transactions(transactions, existing_merchants)
