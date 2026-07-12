"""Hybrid-C portfolio sync: Saxo data → FinPilot domain tables.

Creates one virtual `Account` row per user on first sync ("Saxo SIM"), then
upserts Saxo positions into `stock_positions` keyed by (user_id, symbol,
account_id). Saxo cash goes into `accounts.balance` on that virtual account;
it's never mixed with the manual CASH StockPosition.

This keeps agent-written (manual) positions cleanly separated from
broker-reported positions. The portfolio page can render them together or
separately by grouping on `account_id`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import BrokerAccount, BrokerBalance, BrokerPosition
from app.models.account import Account
from app.models.stock import StockPosition

SAXO_ACCOUNT_NAME_PREFIX = "Saxo"


@dataclass(frozen=True)
class SyncResult:
    account_id: str
    cash_balance: float | None
    cash_currency: str
    positions_upserted: int
    positions_removed: int
    saxo_account_key: str


async def get_or_create_saxo_account(
    db: AsyncSession,
    *,
    user_id: str,
    environment: str,
    broker_account: BrokerAccount,
) -> Account:
    """Idempotent: one FinPilot `Account` per Saxo (user, environment, external_id)."""
    marker = f"{SAXO_ACCOUNT_NAME_PREFIX} {environment.upper()} [{broker_account.external_id}]"
    result = await db.execute(
        select(Account).where(and_(Account.user_id == user_id, Account.name == marker))
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(
            user_id=user_id,
            name=marker,
            type="brokerage",
            currency=broker_account.currency or "USD",
        )
        db.add(account)
        await db.flush()
    else:
        # Pick up currency changes if Saxo renamed the account.
        if broker_account.currency and account.currency != broker_account.currency:
            account.currency = broker_account.currency
    return account


async def sync_positions(
    db: AsyncSession,
    *,
    user_id: str,
    account: Account,
    broker_positions: list[BrokerPosition],
    broker_balance: BrokerBalance | None,
) -> SyncResult:
    """Upsert broker positions into `stock_positions` rows tagged with
    `account.id`. Positions that are no longer present in Saxo are deleted
    (so closed trades disappear from the UI on the next sync)."""
    existing_result = await db.execute(
        select(StockPosition).where(and_(
            StockPosition.user_id == user_id,
            StockPosition.account_id == account.id,
        ))
    )
    existing = {p.symbol: p for p in existing_result.scalars().all()}

    keep: set[str] = set()
    upserted = 0
    now = datetime.now(timezone.utc)

    for bp in broker_positions:
        keep.add(bp.symbol)
        row = existing.get(bp.symbol)
        if row is None:
            row = StockPosition(
                user_id=user_id,
                account_id=account.id,
                symbol=bp.symbol,
                name=bp.name,
                quantity=bp.quantity,
                avg_cost_price=bp.avg_price,
                currency=bp.currency,
                last_price=bp.market_price,
                last_price_at=now if bp.market_price is not None else None,
                unrealized_pnl=bp.unrealized_pnl,
            )
            db.add(row)
        else:
            row.name = bp.name
            row.quantity = bp.quantity
            row.avg_cost_price = bp.avg_price
            row.currency = bp.currency
            if bp.market_price is not None:
                row.last_price = bp.market_price
                row.last_price_at = now
            if bp.unrealized_pnl is not None:
                row.unrealized_pnl = bp.unrealized_pnl
        upserted += 1

    # Remove stale positions.
    removed = 0
    for symbol, row in existing.items():
        if symbol not in keep:
            await db.delete(row)
            removed += 1

    if broker_balance is not None:
        account.balance = broker_balance.cash
        account.balance_date = now
        if broker_balance.currency:
            account.currency = broker_balance.currency

    await db.commit()

    return SyncResult(
        account_id=account.id,
        cash_balance=broker_balance.cash if broker_balance else None,
        cash_currency=broker_balance.currency if broker_balance else account.currency,
        positions_upserted=upserted,
        positions_removed=removed,
        saxo_account_key="",  # filled by caller
    )
