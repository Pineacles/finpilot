"""AI auto-trading service.

Implements the gate flow for request-order, plus approve/reject/expire helpers.
All Saxo calls go through the existing adapter; this module never touches the
Saxo HTTP layer directly.
"""
from __future__ import annotations

import logging
import uuid
import zoneinfo

logger = logging.getLogger(__name__)
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers import get_adapter
from app.brokers.base import TradingDisabledError
from app.brokers.saxo.client import SaxoHTTPError
from app.brokers.saxo.instruments import InstrumentNotFound
from app.models.stock import PendingOrder, StockPosition
from app.models.account import Account
from app.services import settings as settings_svc

# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULTS = {
    "trading_ai_enabled": "0",
    "trading_mode": "off",
    "trading_allowed_actions": "place,modify,cancel",
    "trading_symbol_whitelist": "",
    "trading_symbol_blacklist": "",
    "trading_order_max_chf": "5000",
    "trading_daily_count_max": "20",
    "trading_daily_chf_max": "50000",
    "trading_position_size_max_pct": "5",
    "trading_per_symbol_max_pct": "3",
    "trading_semi_approval_timeout_s": "1800",
    "trading_timezone": "Europe/Zurich",
}


async def _get(db: AsyncSession, user_id: str, key: str) -> str:
    val = await settings_svc.get_setting(db, user_id, key)
    return val or DEFAULTS.get(key, "")


# ── Public entrypoint: request-order gate ────────────────────────────────────

class GateError(Exception):
    """Structured error with HTTP status code and machine-readable code."""
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


async def request_order(
    db: AsyncSession,
    user_id: str,
    *,
    action: str,
    account_key: str,
    symbol: str | None = None,
    buy_sell: str | None = None,
    amount: float | None = None,
    order_type: str | None = None,
    duration: str | None = None,
    limit_price: float | None = None,
    stop_price: float | None = None,
    target_order_id: str | None = None,
    buy_assessment_id: str | None = None,
    rationale: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Full gate flow. Returns dict {pending_order_id, status, mode, broker_order_id?}."""

    # 1. Kill switch
    ai_enabled = await _get(db, user_id, "trading_ai_enabled")
    if ai_enabled != "1":
        raise GateError(403, "ai_trading_disabled", "AI trading is not enabled.")

    # 2. Mode
    mode = await _get(db, user_id, "trading_mode")
    if mode == "off":
        raise GateError(400, "trading_mode_off", "Trading mode is set to off.")

    # 3. Action allowed
    allowed_actions = [a.strip() for a in (await _get(db, user_id, "trading_allowed_actions")).split(",") if a.strip()]
    if action not in allowed_actions:
        raise GateError(403, "action_not_allowed", f"Action '{action}' is not in allowed_actions.")

    # 4. Idempotency
    ikey = idempotency_key or str(uuid.uuid4())
    existing = await db.execute(
        select(PendingOrder).where(and_(
            PendingOrder.user_id == user_id,
            PendingOrder.idempotency_key == ikey,
        ))
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        return _row_to_response(existing_row)

    # 5. Symbol whitelist/blacklist (skip for cancel)
    if action != "cancel" and symbol:
        sym_upper = symbol.upper()
        whitelist_raw = await _get(db, user_id, "trading_symbol_whitelist")
        blacklist_raw = await _get(db, user_id, "trading_symbol_blacklist")
        if whitelist_raw:
            whitelist = {s.strip().upper() for s in whitelist_raw.split(",") if s.strip()}
            if sym_upper not in whitelist:
                raise GateError(400, "symbol_not_in_whitelist", f"Symbol {sym_upper} is not in the whitelist.")
        if blacklist_raw:
            blacklist = {s.strip().upper() for s in blacklist_raw.split(",") if s.strip()}
            if sym_upper in blacklist:
                raise GateError(400, "symbol_in_blacklist", f"Symbol {sym_upper} is blacklisted.")

    # 6. Estimate CHF notional (place/modify only)
    estimated_chf: float | None = None
    estimated_fees_chf: float | None = None
    order_currency: str | None = None

    if action in ("place", "modify") and symbol and amount:
        estimated_chf, estimated_fees_chf, order_currency = await _estimate_notional_chf(
            db, user_id, account_key=account_key, symbol=symbol,
            buy_sell=buy_sell or "Buy", amount=amount,
            order_type=order_type or "Market", duration=duration or "DayOrder",
            limit_price=limit_price, stop_price=stop_price,
        )

    # 7. Per-order CHF cap
    order_max_chf = float(await _get(db, user_id, "trading_order_max_chf") or "5000")
    if estimated_chf is not None and estimated_chf > order_max_chf:
        raise GateError(400, "order_cap_exceeded",
                        f"Estimated notional {estimated_chf:.2f} CHF exceeds per-order cap {order_max_chf:.2f} CHF.")

    # 8. Daily caps
    tz_name = await _get(db, user_id, "trading_timezone")
    try:
        user_tz = zoneinfo.ZoneInfo(tz_name)
    except Exception as _exc:
        logger.warning("Invalid trading_timezone %r, falling back to Europe/Zurich: %s", tz_name, _exc)
        user_tz = zoneinfo.ZoneInfo("Europe/Zurich")

    local_now = datetime.now(user_tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc = local_midnight.astimezone(timezone.utc)

    # Non-terminal statuses count toward daily limits
    non_terminal = ("pending_approval", "approved", "placed")

    count_result = await db.execute(
        select(func.count()).where(and_(
            PendingOrder.user_id == user_id,
            PendingOrder.created_at >= midnight_utc,
            PendingOrder.status.in_(non_terminal),
        ))
    )
    daily_count = count_result.scalar() or 0
    daily_count_max = int(await _get(db, user_id, "trading_daily_count_max") or "20")
    if daily_count >= daily_count_max:
        raise GateError(400, "daily_count_exceeded",
                        f"Daily order count limit {daily_count_max} reached.")

    sum_result = await db.execute(
        select(func.coalesce(func.sum(PendingOrder.estimated_cash_required_chf), 0.0)).where(and_(
            PendingOrder.user_id == user_id,
            PendingOrder.created_at >= midnight_utc,
            PendingOrder.status.in_(non_terminal),
        ))
    )
    daily_chf_used = float(sum_result.scalar() or 0.0)
    daily_chf_max = float(await _get(db, user_id, "trading_daily_chf_max") or "50000")
    this_chf = estimated_chf or 0.0
    if daily_chf_used + this_chf > daily_chf_max:
        raise GateError(400, "daily_chf_exceeded",
                        f"Daily CHF limit {daily_chf_max:.2f} would be exceeded.")

    # 9. Per-symbol / position-size cap (Buy place only)
    if action == "place" and buy_sell == "Buy" and symbol and amount and estimated_chf:
        await _check_position_caps(db, user_id, symbol=symbol, amount=amount,
                                   estimated_price_chf=estimated_chf / amount if amount else 0)

    # 10. Route by mode
    now = datetime.now(timezone.utc)
    expires_at: datetime | None = None

    if mode == "semi":
        timeout_s = int(await _get(db, user_id, "trading_semi_approval_timeout_s") or "1800")
        expires_at = now + timedelta(seconds=timeout_s)
        initial_status = "pending_approval"
    else:  # auto
        initial_status = "approved"

    row = PendingOrder(
        id=str(uuid.uuid4()),
        user_id=user_id,
        account_key=account_key,
        symbol=symbol,
        action=action,
        target_order_id=target_order_id,
        buy_sell=buy_sell,
        amount=amount,
        order_type=order_type,
        duration=duration,
        limit_price=limit_price,
        stop_price=stop_price,
        asset_type_saxo="Stock",
        mode=mode,
        status=initial_status,
        buy_assessment_id=buy_assessment_id,
        rationale=rationale,
        estimated_cash_required_chf=estimated_chf,
        estimated_fees_chf=estimated_fees_chf,
        currency=order_currency,
        idempotency_key=ikey,
        expires_at=expires_at,
        created_at=now,
    )
    db.add(row)
    await db.flush()

    if mode == "auto":
        await _execute_order(db, row)

    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


# ── Approve ───────────────────────────────────────────────────────────────────

async def approve_order(db: AsyncSession, user_id: str, order_id: str) -> dict[str, Any]:
    row = await _get_row(db, user_id, order_id)
    if row.status != "pending_approval":
        raise GateError(409, "wrong_status", f"Order is '{row.status}', not 'pending_approval'.")

    now = datetime.now(timezone.utc)
    if row.expires_at and row.expires_at < now:
        row.status = "expired"
        await db.commit()
        raise GateError(410, "order_expired", "Order has expired.")

    # Re-precheck (prices may have moved)
    if row.action in ("place", "modify") and row.symbol and row.amount:
        try:
            adapter = get_adapter("saxo")
            precheck = await adapter.precheck_order(
                db, user_id,
                account_key=row.account_key,
                symbol=row.symbol,
                buy_sell=row.buy_sell or "Buy",
                amount=row.amount,
                order_type=row.order_type or "Market",
                duration=row.duration or "DayOrder",
                limit_price=row.limit_price,
                stop_price=row.stop_price,
                asset_type=row.asset_type_saxo or "Stock",
            )
            if not precheck.ok and precheck.error_message:
                row.status = "failed"
                row.rejected_reason = f"precheck_failed:{precheck.error_message}"
                await db.commit()
                raise GateError(400, "precheck_failed", precheck.error_message)
        except (TradingDisabledError, InstrumentNotFound, SaxoHTTPError, RuntimeError):
            pass  # non-definitive — proceed anyway

    row.approved_at = now
    await _execute_order(db, row)
    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


# ── Reject ────────────────────────────────────────────────────────────────────

async def reject_order(db: AsyncSession, user_id: str, order_id: str, reason: str | None = None) -> dict[str, Any]:
    row = await _get_row(db, user_id, order_id)
    if row.status != "pending_approval":
        raise GateError(409, "wrong_status", f"Order is '{row.status}', not 'pending_approval'.")
    row.status = "rejected"
    row.rejected_at = datetime.now(timezone.utc)
    row.rejected_reason = reason
    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


# ── Expire stale ──────────────────────────────────────────────────────────────

async def expire_stale(db: AsyncSession, user_id: str) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PendingOrder).where(and_(
            PendingOrder.user_id == user_id,
            PendingOrder.status == "pending_approval",
            PendingOrder.expires_at < now,
        ))
    )
    rows = result.scalars().all()
    for r in rows:
        r.status = "expired"
    await db.commit()
    return len(rows)


# ── Expire single ─────────────────────────────────────────────────────────────

async def expire_order(db: AsyncSession, user_id: str, order_id: str) -> dict[str, Any]:
    row = await _get_row(db, user_id, order_id)
    if row.status not in ("pending_approval",):
        raise GateError(409, "wrong_status", f"Order is '{row.status}', cannot expire.")
    row.status = "expired"
    await db.commit()
    await db.refresh(row)
    return _row_to_response(row)


# ── List ──────────────────────────────────────────────────────────────────────

async def list_orders(
    db: AsyncSession,
    user_id: str,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    q = select(PendingOrder).where(PendingOrder.user_id == user_id)
    if status:
        q = q.where(PendingOrder.status == status)
    q = q.order_by(PendingOrder.created_at.desc()).limit(limit)
    result = await db.execute(q)
    return [_row_to_response(r) for r in result.scalars().all()]


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _get_row(db: AsyncSession, user_id: str, order_id: str) -> PendingOrder:
    result = await db.execute(
        select(PendingOrder).where(and_(
            PendingOrder.id == order_id,
            PendingOrder.user_id == user_id,
        ))
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise GateError(404, "not_found", f"Pending order {order_id} not found.")
    return row


async def _execute_order(db: AsyncSession, row: PendingOrder) -> None:
    """Call the Saxo adapter. Update row.status in-place. Does NOT commit."""
    adapter = get_adapter("saxo")
    try:
        if row.action == "place":
            ack = await adapter.place_order(
                db, row.user_id,
                account_key=row.account_key,
                symbol=row.symbol or "",
                buy_sell=row.buy_sell or "Buy",
                amount=row.amount or 1,
                order_type=row.order_type or "Market",
                duration=row.duration or "DayOrder",
                limit_price=row.limit_price,
                stop_price=row.stop_price,
                asset_type=row.asset_type_saxo or "Stock",
            )
            row.broker_order_id = ack.order_id
            row.broker_response = ack.raw
        elif row.action == "modify":
            await adapter.modify_order(
                db, row.user_id,
                order_id=row.target_order_id or "",
                account_key=row.account_key,
                amount=row.amount,
                limit_price=row.limit_price,
                stop_price=row.stop_price,
                duration=row.duration,
            )
        elif row.action == "cancel":
            await adapter.cancel_order(
                db, row.user_id,
                order_id=row.target_order_id or "",
                account_key=row.account_key,
            )
        row.status = "placed"
        row.placed_at = datetime.now(timezone.utc)
    except (TradingDisabledError, InstrumentNotFound, SaxoHTTPError, RuntimeError) as exc:
        row.status = "failed"
        row.rejected_reason = str(exc)[:500]


async def _estimate_notional_chf(
    db: AsyncSession,
    user_id: str,
    *,
    account_key: str,
    symbol: str,
    buy_sell: str,
    amount: float,
    order_type: str,
    duration: str,
    limit_price: float | None,
    stop_price: float | None,
) -> tuple[float, float, str | None]:
    """Try precheck first; fall back to rough estimate. Returns (notional_chf, fees_chf, currency)."""
    adapter = get_adapter("saxo")
    try:
        precheck = await adapter.precheck_order(
            db, user_id,
            account_key=account_key,
            symbol=symbol,
            buy_sell=buy_sell,
            amount=amount,
            order_type=order_type,
            duration=duration,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        cash = precheck.estimated_cash_required or 0.0
        fees = precheck.estimated_fees or 0.0
        currency = precheck.currency
        fx = await _get_fx(currency, "CHF")
        return cash * fx, fees * fx, currency
    except Exception as _exc:
        logger.warning("Order precheck failed for %s, falling back to estimate: %s", symbol, _exc)

    # Fallback: use limit price or 0
    price = limit_price or 0.0
    notional = amount * price
    return notional, 0.0, None


async def _get_fx(from_currency: str | None, to_currency: str) -> float:
    """Best-effort FX rate. Falls back to 1.0 if unavailable."""
    if not from_currency or from_currency == to_currency:
        return 1.0
    try:
        from app.services.portfolio_analytics import get_fx_rate  # type: ignore
        return await get_fx_rate(from_currency, to_currency)
    except Exception as _exc:
        logger.warning("portfolio_analytics FX rate unavailable (%s→%s): %s", from_currency, to_currency, _exc)
    try:
        from app.services.benchmark import get_fx_rate as bget_fx  # type: ignore
        return await bget_fx(from_currency, to_currency)
    except Exception as _exc:
        logger.warning("benchmark FX rate unavailable (%s→%s): %s; defaulting to 1.0", from_currency, to_currency, _exc)
        return 1.0


async def _check_position_caps(
    db: AsyncSession,
    user_id: str,
    *,
    symbol: str,
    amount: float,
    estimated_price_chf: float,
) -> None:
    """Check per-symbol and position-size caps. Raises GateError on breach."""
    position_size_max_pct = float(await _get(db, user_id, "trading_position_size_max_pct") or "5")
    per_symbol_max_pct = float(await _get(db, user_id, "trading_per_symbol_max_pct") or "3")

    # Portfolio total: sum positions * last_price, converted to CHF, + cash
    pos_result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = pos_result.scalars().all()

    total_value_chf = 0.0
    existing_symbol_value_chf = 0.0
    for p in positions:
        price = p.last_price or p.avg_cost_price
        fx = await _get_fx(p.currency, "CHF")
        val_chf = p.quantity * price * fx
        total_value_chf += val_chf
        if p.symbol.upper() == symbol.upper():
            existing_symbol_value_chf += val_chf

    # Add cash from accounts
    acct_result = await db.execute(
        select(Account).where(Account.user_id == user_id)
    )
    for acct in acct_result.scalars().all():
        if acct.balance:
            fx = await _get_fx(acct.currency, "CHF")
            total_value_chf += float(acct.balance) * fx

    if total_value_chf <= 0:
        return  # can't compute — skip caps

    new_value_chf = existing_symbol_value_chf + amount * estimated_price_chf
    projected_pct = new_value_chf / total_value_chf * 100

    if projected_pct > per_symbol_max_pct:
        raise GateError(
            400, "per_symbol_cap_exceeded",
            f"Projected symbol allocation {projected_pct:.1f}% exceeds per-symbol cap {per_symbol_max_pct:.1f}%."
        )
    if projected_pct > position_size_max_pct:
        raise GateError(
            400, "position_size_cap_exceeded",
            f"Projected position size {projected_pct:.1f}% exceeds position-size cap {position_size_max_pct:.1f}%."
        )


def _row_to_response(row: PendingOrder) -> dict[str, Any]:
    return {
        "pending_order_id": row.id,
        "user_id": row.user_id,
        "account_key": row.account_key,
        "symbol": row.symbol,
        "action": row.action,
        "target_order_id": row.target_order_id,
        "buy_sell": row.buy_sell,
        "amount": row.amount,
        "order_type": row.order_type,
        "duration": row.duration,
        "limit_price": row.limit_price,
        "stop_price": row.stop_price,
        "mode": row.mode,
        "status": row.status,
        "buy_assessment_id": row.buy_assessment_id,
        "rationale": row.rationale,
        "estimated_cash_required_chf": row.estimated_cash_required_chf,
        "estimated_fees_chf": row.estimated_fees_chf,
        "currency": row.currency,
        "idempotency_key": row.idempotency_key,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "placed_at": row.placed_at.isoformat() if row.placed_at else None,
        "rejected_at": row.rejected_at.isoformat() if row.rejected_at else None,
        "rejected_reason": row.rejected_reason,
        "broker_order_id": row.broker_order_id,
        "broker_response": row.broker_response,
    }
