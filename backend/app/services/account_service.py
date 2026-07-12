"""Shared account balance computation.

`compute_account_balance` is the single source of truth for "what is this
account's balance right now", used by both the dashboard overview
(api/endpoints/dashboard.py) and the credit-card settlement auto-reset
(services/settlement.py) so the two can never diverge on the anchor-aware
math (anchor balance + sum of transactions dated strictly *after* the
anchor date; a naive full-history sum only when no anchor has ever been set).
"""
from datetime import datetime, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.finance import Transaction


class AccountNotFoundError(Exception):
    def __init__(self, account_id: str):
        self.account_id = account_id
        super().__init__(f"Account not found: {account_id}")


async def compute_account_balance(db: AsyncSession, user_id: str, account: Account) -> float:
    """Anchor-aware balance for one account.

    - If an anchor balance + balance_date is set: anchor + sum(amount) of
      transactions dated strictly after balance_date.
    - If only an anchor balance is set (no date): just the anchor.
    - If no anchor at all: naive sum of every transaction on the account.
    """
    if account.balance is not None and account.balance_date is not None:
        anchor_date = account.balance_date.date() if isinstance(account.balance_date, datetime) else account.balance_date
        delta_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(
                    Transaction.user_id == user_id,
                    Transaction.account_id == account.id,
                    Transaction.date > anchor_date,
                )
            )
        )
        return account.balance + float(delta_result.scalar())
    elif account.balance is not None:
        return account.balance
    else:
        bal_result = await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                and_(Transaction.user_id == user_id, Transaction.account_id == account.id)
            )
        )
        return float(bal_result.scalar())


async def get_accounts(db: AsyncSession, user_id: str) -> list[Account]:
    result = await db.execute(select(Account).where(Account.user_id == user_id))
    return list(result.scalars().all())


async def get_credit_card_accounts(db: AsyncSession, user_id: str) -> list[Account]:
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.type == "credit_card"))
    )
    return list(result.scalars().all())


async def get_account(db: AsyncSession, user_id: str, account_id: str) -> Account:
    result = await db.execute(
        select(Account).where(and_(Account.id == account_id, Account.user_id == user_id))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise AccountNotFoundError(account_id)
    return account


async def update_settlement_patterns(
    db: AsyncSession, user_id: str, account_id: str, patterns: list[str] | None
) -> Account:
    """Set (or clear, with None/[]) the issuer-match keywords for a
    credit_card account. Patterns are lower-cased and stripped for
    case-insensitive matching in services/settlement.py."""
    account = await get_account(db, user_id, account_id)
    if account.type != "credit_card":
        raise ValueError("settlement_patterns can only be set on credit_card accounts")

    cleaned = [p.strip().lower() for p in (patterns or []) if p and p.strip()]
    account.settlement_patterns = cleaned or None
    await db.commit()
    await db.refresh(account)
    return account


async def set_account_balance(
    db: AsyncSession, user_id: str, account_id: str, balance: float
) -> tuple[float | None, Account]:
    """Set the actual balance anchor for an account (manual correction,
    e.g. reconciling against the real bank statement). Returns
    (previous_balance, account) so callers can report the change.
    Raises AccountNotFoundError if the account doesn't exist / isn't owned
    by user_id."""
    account = await get_account(db, user_id, account_id)
    previous = account.balance
    account.balance = balance
    account.balance_date = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(account)
    return previous, account


async def list_accounts_with_balances(db: AsyncSession, user_id: str) -> list[dict]:
    """Every account with its computed (anchor-aware) balance: the
    "what accounts exist and what do they hold" view shared by the dashboard
    and the agent surface."""
    accounts = await get_accounts(db, user_id)
    out = []
    for acct in accounts:
        balance = await compute_account_balance(db, user_id, acct)
        out.append({
            "id": acct.id,
            "name": acct.name,
            "type": acct.type,
            "currency": acct.currency,
            "balance": balance,
            "balance_date": acct.balance_date.isoformat() if acct.balance_date else None,
            "settlement_patterns": acct.settlement_patterns,
        })
    return out
