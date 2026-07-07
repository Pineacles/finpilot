"""Broker adapter REST endpoints.

All routes are per-user (JWT-authenticated). The OAuth redirect from Saxo
lands on a Next.js page (`/settings/saxo/callback`), which forwards the code
and state to `POST /api/brokers/saxo/callback` carrying the user's bearer
token. Saxo's dev-app redirect URL must therefore be registered as the
frontend callback URL, not this backend endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.brokers import get_adapter, list_adapters
from app.brokers.base import AuthState
from app.brokers.saxo import config as saxo_config
from app.brokers.saxo import sync as saxo_sync
from app.brokers.saxo.client import SaxoHTTPError
from app.core.database import get_db
from app.models.user import User
from app.schemas.brokers import (
    ConnectResponse,
    StatusResponse,
    CallbackPayload,
    DisconnectResponse,
    HealthResponse,
    BrokersListResponse,
    SaxoAccountsResponse,
    SaxoBalanceResponse,
    SaxoPositionsResponse,
    SaxoSyncResponse,
    SaxoSubPortfolioResponse,
)

router = APIRouter(prefix="/api/brokers", tags=["brokers"])


@router.get("", response_model=BrokersListResponse)
async def list_brokers():
    """Public metadata about all registered broker adapters."""
    return {
        "brokers": [
            {
                "name": d.name,
                "label": d.label,
                "environments": d.environments,
                "trading_available": d.trading_available,
            }
            for d in list_adapters()
        ],
        "saxo_environments": saxo_config.available_environments(),
    }


@router.get("/saxo/status", response_model=StatusResponse)
async def saxo_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    status = await adapter.status(db, user.id)
    return StatusResponse(
        state=status.state.value,
        environment=status.environment,
        detail=None,  # never echo authorize URLs back via status
        last_error=status.last_error,
    )


@router.post("/saxo/connect", response_model=ConnectResponse)
async def saxo_connect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    status = await adapter.authenticate(db, user.id)
    if status.state == AuthState.DISABLED:
        raise HTTPException(status_code=409, detail="Saxo is not enabled.")
    if status.state == AuthState.SETUP_REQUIRED:
        raise HTTPException(status_code=409, detail="Saxo is not configured (AppKey / AppSecret / Redirect URL).")
    if status.state != AuthState.CONNECTING or not status.detail:
        raise HTTPException(status_code=500, detail="Saxo authorize flow could not start.")
    return ConnectResponse(authorize_url=status.detail, environment=status.environment or "sim")


@router.post("/saxo/callback", response_model=StatusResponse)
async def saxo_callback(
    payload: CallbackPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Relay endpoint called by the frontend OAuth callback page."""
    adapter = get_adapter("saxo")
    result = await adapter.complete_oauth(db, user.id, code=payload.code, state=payload.state)
    return StatusResponse(
        state=result.state.value,
        environment=result.environment,
        last_error=result.last_error,
    )


@router.post("/saxo/disconnect", response_model=DisconnectResponse)
async def saxo_disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    await adapter.disconnect(db, user.id)
    return {"status": "ok"}


@router.get("/saxo/health", response_model=HealthResponse)
async def saxo_health(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    ok = await adapter.health_check(db, user.id)
    return {"ok": ok}


@router.get("/saxo/accounts", response_model=SaxoAccountsResponse)
async def saxo_accounts(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    try:
        accounts = await adapter.get_accounts(db, user.id)
    except RuntimeError as exc:
        if str(exc) == "needs_auth":
            raise HTTPException(status_code=409, detail="Saxo needs re-authentication.")
        raise
    return {"accounts": [_account_dict(a) for a in accounts]}


@router.get("/saxo/balances", response_model=SaxoBalanceResponse)
async def saxo_balances(
    account_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    try:
        balance = await adapter.get_balances(db, user.id, account_key)
    except RuntimeError as exc:
        if str(exc) == "needs_auth":
            raise HTTPException(status_code=409, detail="Saxo needs re-authentication.")
        raise
    return _balance_dict(balance)


@router.get("/saxo/positions", response_model=SaxoPositionsResponse)
async def saxo_positions(
    account_key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    adapter = get_adapter("saxo")
    try:
        positions = await adapter.get_positions(db, user.id, account_key)
    except RuntimeError as exc:
        if str(exc) == "needs_auth":
            raise HTTPException(status_code=409, detail="Saxo needs re-authentication.")
        raise
    return {"positions": [_position_dict(p) for p in positions]}


def _handle_saxo_errors(exc: Exception) -> HTTPException | None:
    if isinstance(exc, SaxoHTTPError):
        status = exc.status or 502
        return HTTPException(status_code=status, detail=exc.detail)
    if isinstance(exc, RuntimeError) and str(exc) == "needs_auth":
        return HTTPException(status_code=409, detail="Saxo needs re-authentication.")
    return None


# ── Portfolio sync ──────────────────────────────────────────────────────

async def _run_sync(db: AsyncSession, user_id: str) -> saxo_sync.SyncResult | None:
    """Pull Saxo accounts/balances/positions and upsert into FinPilot tables."""
    adapter = get_adapter("saxo")
    accounts = await adapter.get_accounts(db, user_id)
    if not accounts:
        return None
    saxo_account = accounts[0]  # single-account scope for this release
    environment = saxo_account.environment
    balance = await adapter.get_balances(db, user_id, saxo_account.external_id)
    positions = await adapter.get_positions(db, user_id, saxo_account.external_id)

    local_account = await saxo_sync.get_or_create_saxo_account(
        db, user_id=user_id, environment=environment, broker_account=saxo_account
    )
    result = await saxo_sync.sync_positions(
        db,
        user_id=user_id,
        account=local_account,
        broker_positions=positions,
        broker_balance=balance,
    )
    return result


@router.post("/saxo/sync", response_model=SaxoSyncResponse)
async def saxo_sync_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await _run_sync(db, user.id)
    except Exception as exc:
        mapped = _handle_saxo_errors(exc)
        if mapped:
            raise mapped
        raise
    if result is None:
        return {"status": "noop", "reason": "no_accounts"}
    return {
        "status": "ok",
        "account_id": result.account_id,
        "cash_balance": result.cash_balance,
        "cash_currency": result.cash_currency,
        "positions_upserted": result.positions_upserted,
        "positions_removed": result.positions_removed,
    }


@router.get("/saxo/sub-portfolio", response_model=SaxoSubPortfolioResponse)
async def saxo_sub_portfolio(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Saxo-only slice for the portfolio page's Saxo card. Reads from local DB
    (post-sync), so it's fast and doesn't burn Saxo's rate budget on page load."""
    from sqlalchemy import select, and_
    from app.models.account import Account
    from app.models.stock import StockPosition
    from app.services import settings as settings_svc

    # Gate on user actually having Saxo enabled with valid (non-revoked) tokens.
    saxo_enabled = await settings_svc.get_setting(db, user.id, "saxo_enabled")
    saxo_access_token = await settings_svc.get_setting(db, user.id, "saxo_access_token")
    saxo_refresh_token = await settings_svc.get_setting(db, user.id, "saxo_refresh_token")
    saxo_needs_reauth = await settings_svc.get_setting(db, user.id, "saxo_needs_reauth")

    if (
        saxo_enabled != "1"
        or (not saxo_access_token and not saxo_refresh_token)
        or saxo_needs_reauth == "1"
    ):
        return {"connected": False, "accounts": []}

    result = await db.execute(
        select(Account).where(and_(
            Account.user_id == user.id,
            Account.name.like(f"{saxo_sync.SAXO_ACCOUNT_NAME_PREFIX}%"),
        ))
    )
    accounts = result.scalars().all()
    if not accounts:
        return {"connected": False, "accounts": []}

    account_payloads = []
    for account in accounts:
        pos_result = await db.execute(
            select(StockPosition).where(and_(
                StockPosition.user_id == user.id,
                StockPosition.account_id == account.id,
            ))
        )
        positions = pos_result.scalars().all()
        account_payloads.append({
            "account_id": account.id,
            "name": account.name,
            "currency": account.currency,
            "cash": account.balance or 0,
            "cash_updated_at": account.balance_date.isoformat() if account.balance_date else None,
            "positions": [
                {
                    "id": p.id, "symbol": p.symbol, "name": p.name,
                    "quantity": p.quantity, "avg_cost_price": p.avg_cost_price,
                    "currency": p.currency, "last_price": p.last_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "market_value": (p.last_price or p.avg_cost_price) * p.quantity,
                }
                for p in positions
            ],
        })
    return {"connected": True, "accounts": account_payloads}


def _account_dict(a):
    return {
        "external_id": a.external_id,
        "display_name": a.display_name,
        "currency": a.currency,
        "environment": a.environment,
    }


def _balance_dict(b):
    return {
        "account_external_id": b.account_external_id,
        "cash": b.cash,
        "currency": b.currency,
        "total_value": b.total_value,
        "unrealized_pnl": b.unrealized_pnl,
    }


def _position_dict(p):
    return {
        "account_external_id": p.account_external_id,
        "symbol": p.symbol,
        "name": p.name,
        "quantity": p.quantity,
        "avg_price": p.avg_price,
        "currency": p.currency,
        "market_price": p.market_price,
        "market_value": p.market_value,
        "unrealized_pnl": p.unrealized_pnl,
    }
