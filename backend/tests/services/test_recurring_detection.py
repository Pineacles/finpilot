"""recurring_detection: grouping/frequency/amount heuristics + DB-backed exclusion."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.account import Account
from app.models.finance import RecurringExpense, Transaction
from app.services import recurring_detection
from app.services.recurring_detection import detect_from_transactions, detect_recurring_expenses


def _txn(user_id, account_id, d, amount, merchant="Netflix", currency="CHF"):
    return Transaction(
        user_id=user_id, account_id=account_id, date=d, merchant=merchant,
        amount=amount, currency=currency,
    )


async def _make_account(db, user_id: str, name: str = "Bank") -> Account:
    acct = Account(user_id=user_id, name=name, type="bank", currency="CHF")
    db.add(acct)
    await db.flush()
    return acct


# ── Pure detect_from_transactions tests (no DB) ─────────────────────────

def test_monthly_recurring_detected():
    txns = [
        _txn("u1", "a1", date(2026, 1, 15), -15.90),
        _txn("u1", "a1", date(2026, 2, 14), -15.90),
        _txn("u1", "a1", date(2026, 3, 16), -15.90),
        _txn("u1", "a1", date(2026, 4, 15), -15.90),
    ]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.merchant == "Netflix"
    assert s.frequency == "monthly"
    assert s.occurrences == 4
    assert abs(s.amount - 15.90) < 0.01
    assert s.next_due_date == date(2026, 5, 15)


def test_weekly_recurring_detected():
    start = date(2026, 1, 5)
    txns = [_txn("u1", "a1", start + timedelta(weeks=i), -9.99, merchant="Spotify") for i in range(4)]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1
    assert suggestions[0].frequency == "weekly"
    assert suggestions[0].next_due_date == start + timedelta(weeks=4)


def test_yearly_recurring_detected():
    txns = [
        _txn("u1", "a1", date(2023, 6, 1), -120.0, merchant="Domain Renewal"),
        _txn("u1", "a1", date(2024, 6, 3), -120.0, merchant="Domain Renewal"),
        _txn("u1", "a1", date(2025, 5, 28), -120.0, merchant="Domain Renewal"),
    ]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1
    assert suggestions[0].frequency == "yearly"


def test_amount_tolerance_pct_within_bounds():
    # 10% tolerance around mean; these vary by less than 10%
    amounts = [-100.0, -105.0, -95.0, -102.0]
    txns = [_txn("u1", "a1", date(2026, i + 1, 1), amounts[i]) for i in range(4)]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1


def test_amount_tolerance_exceeded_no_suggestion():
    # Amounts vary far more than 10%/2 CHF tolerance -> not recurring
    amounts = [-10.0, -50.0, -10.0, -60.0]
    txns = [_txn("u1", "a1", date(2026, i + 1, 1), amounts[i]) for i in range(4)]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert suggestions == []


def test_small_amount_abs_tolerance():
    # Small amounts: 10% would be tiny, so the 2 CHF absolute floor applies
    amounts = [-5.0, -6.5, -5.0, -6.9]  # within 2 CHF of mean (~5.85)
    txns = [_txn("u1", "a1", date(2026, i + 1, 1), amounts[i]) for i in range(4)]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1


def test_irregular_dates_no_false_positive():
    txns = [
        _txn("u1", "a1", date(2026, 1, 3), -20.0, merchant="Random Shop"),
        _txn("u1", "a1", date(2026, 1, 20), -20.0, merchant="Random Shop"),
        _txn("u1", "a1", date(2026, 3, 1), -20.0, merchant="Random Shop"),
        _txn("u1", "a1", date(2026, 3, 25), -20.0, merchant="Random Shop"),
    ]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert suggestions == []


def test_fewer_than_min_occurrences_no_suggestion():
    txns = [
        _txn("u1", "a1", date(2026, 1, 15), -15.90),
        _txn("u1", "a1", date(2026, 2, 14), -15.90),
    ]
    assert detect_from_transactions(txns, existing_merchants=set()) == []


def test_income_transactions_excluded():
    txns = [
        _txn("u1", "a1", date(2026, i + 1, 25), 5000.0, merchant="Employer AG")
        for i in range(4)
    ]
    assert detect_from_transactions(txns, existing_merchants=set()) == []


def test_existing_merchant_excluded():
    txns = [
        _txn("u1", "a1", date(2026, 1, 15), -15.90),
        _txn("u1", "a1", date(2026, 2, 14), -15.90),
        _txn("u1", "a1", date(2026, 3, 16), -15.90),
    ]
    suggestions = detect_from_transactions(txns, existing_merchants={"netflix"})
    assert suggestions == []


def test_merchant_normalization_groups_case_insensitively():
    txns = [
        _txn("u1", "a1", date(2026, 1, 15), -15.90, merchant="Netflix"),
        _txn("u1", "a1", date(2026, 2, 14), -15.90, merchant=" netflix "),
        _txn("u1", "a1", date(2026, 3, 16), -15.90, merchant="NETFLIX"),
    ]
    suggestions = detect_from_transactions(txns, existing_merchants=set())
    assert len(suggestions) == 1
    assert suggestions[0].occurrences == 3


# ── DB-backed detect_recurring_expenses ─────────────────────────────────

async def test_detect_recurring_expenses_excludes_tracked_and_scopes_by_user(db, user_id):
    acct = await _make_account(db, user_id)
    other_acct = await _make_account(db, "other-user", name="Other Bank")
    await db.flush()

    for i in range(4):
        db.add(_txn(user_id, acct.id, date(2026, i + 1, 15), -15.90, merchant="Netflix"))
        db.add(_txn(user_id, acct.id, date(2026, i + 1, 5), -8.0, merchant="Coffee Club"))
    # Another user's matching pattern must not leak into this user's suggestions
    for i in range(4):
        db.add(_txn("other-user", other_acct.id, date(2026, i + 1, 1), -99.0, merchant="Other Sub"))
    # Already tracked -> should be excluded from suggestions
    db.add(RecurringExpense(
        user_id=user_id, name="Netflix", amount=15.90, currency="CHF",
        frequency="monthly", next_due_date=date(2026, 5, 15),
    ))
    await db.commit()

    suggestions = await detect_recurring_expenses(db, user_id)
    merchants = {s.merchant for s in suggestions}
    assert "Netflix" not in merchants  # already tracked
    assert "Coffee Club" in merchants
    assert "Other Sub" not in merchants  # belongs to a different user
