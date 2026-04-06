"""Saxo Bank OpenAPI integration service.

Supports two auth flows:
1. Certificate-Based Auth (persistent, for server-to-server) — preferred
2. OAuth2 Authorization Code (for initial setup / manual token grant)

The service stores tokens in the database via sync_logs and refreshes automatically.
"""
import json
import time
from datetime import datetime, date, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.account import Account
from app.models.stock import StockPosition, StockTransaction, PortfolioSnapshot
from app.models.sync import SyncLog

# Token cache (in-memory, refreshed as needed)
_token_cache: dict = {"access_token": None, "expires_at": 0, "refresh_token": None}


class SaxoClient:
    def __init__(self):
        self.base_url = settings.SAXO_API_URL
        self.app_key = settings.SAXO_APP_KEY
        self.app_secret = settings.SAXO_APP_SECRET
        self.token_url = settings.SAXO_TOKEN_URL
        self.client = httpx.AsyncClient(timeout=30)

    async def _get_headers(self) -> dict:
        token = await self._get_valid_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def _get_valid_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        if _token_cache["access_token"] and _token_cache["expires_at"] > time.time() + 60:
            return _token_cache["access_token"]

        if _token_cache["refresh_token"]:
            return await self._refresh_token()

        # If using certificate-based auth
        if settings.SAXO_CERT_PATH and Path(settings.SAXO_CERT_PATH).exists():
            return await self._cert_auth()

        raise RuntimeError(
            "No valid Saxo token available. "
            "Either set SAXO_CERT_PATH for certificate auth, "
            "or call /api/sync/saxo/authorize to start OAuth flow."
        )

    async def _cert_auth(self) -> str:
        """Authenticate using client certificate."""
        resp = await self.client.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.app_key,
                "client_secret": self.app_secret,
            },
            cert=settings.SAXO_CERT_PATH,
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 1200)
        _token_cache["refresh_token"] = data.get("refresh_token")
        return data["access_token"]

    async def _refresh_token(self) -> str:
        """Refresh the access token."""
        resp = await self.client.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": _token_cache["refresh_token"],
                "client_id": self.app_key,
                "client_secret": self.app_secret,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 1200)
        _token_cache["refresh_token"] = data.get("refresh_token", _token_cache["refresh_token"])
        return data["access_token"]

    def set_tokens(self, access_token: str, refresh_token: str, expires_in: int = 1200):
        """Manually set tokens (from OAuth callback)."""
        _token_cache["access_token"] = access_token
        _token_cache["refresh_token"] = refresh_token
        _token_cache["expires_at"] = time.time() + expires_in

    async def get_accounts(self) -> dict:
        headers = await self._get_headers()
        resp = await self.client.get(f"{self.base_url}/port/v1/accounts/me", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_balances(self, account_key: str | None = None) -> dict:
        headers = await self._get_headers()
        url = f"{self.base_url}/port/v1/balances/me"
        if account_key:
            url = f"{self.base_url}/port/v1/balances?AccountKey={account_key}&ClientKey=me"
        resp = await self.client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_positions(self) -> list[dict]:
        headers = await self._get_headers()
        resp = await self.client.get(
            f"{self.base_url}/port/v1/positions/me",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("Data", [])

    async def get_orders(self) -> list[dict]:
        headers = await self._get_headers()
        resp = await self.client.get(
            f"{self.base_url}/port/v1/orders/me",
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("Data", [])

    async def get_performance(self, from_date: str, to_date: str) -> dict:
        headers = await self._get_headers()
        resp = await self.client.get(
            f"{self.base_url}/hist/v4/performance/timeseries",
            headers=headers,
            params={
                "AccountKey": settings.SAXO_ACCOUNT_KEY or "me",
                "FromDate": from_date,
                "ToDate": to_date,
                "FieldGroups": "AccountValue,ProfitLoss",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()


saxo_client = SaxoClient()


async def sync_saxo_positions(db: AsyncSession, user_id: str, account_id: str) -> int:
    """Sync positions from Saxo Bank into local DB. Returns count of synced records."""
    try:
        positions = await saxo_client.get_positions()
        balances = await saxo_client.get_balances()

        synced = 0
        for pos in positions:
            display = pos.get("DisplayAndFormat", {})
            net_pos = pos.get("NetPositionBase", {})
            net_pos_view = pos.get("NetPositionView", {})

            symbol = display.get("Symbol", "UNKNOWN")
            name = display.get("Description", symbol)
            quantity = net_pos.get("Amount", 0)
            avg_price = net_pos.get("AverageOpenPrice", 0)
            currency = display.get("Currency", "USD")
            current_price = net_pos_view.get("MarketValue", 0) / quantity if quantity else 0
            pnl = net_pos_view.get("ProfitLossOnTrade", 0)

            # Upsert by symbol + account
            result = await db.execute(
                select(StockPosition).where(
                    and_(
                        StockPosition.user_id == user_id,
                        StockPosition.account_id == account_id,
                        StockPosition.symbol == symbol,
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.quantity = quantity
                existing.avg_cost_price = avg_price
                existing.last_price = current_price
                existing.last_price_at = datetime.now(timezone.utc)
                existing.unrealized_pnl = pnl
                existing.name = name
            else:
                db.add(StockPosition(
                    user_id=user_id,
                    account_id=account_id,
                    symbol=symbol,
                    name=name,
                    quantity=quantity,
                    avg_cost_price=avg_price,
                    currency=currency,
                    last_price=current_price,
                    last_price_at=datetime.now(timezone.utc),
                    unrealized_pnl=pnl,
                ))
            synced += 1

        # Log sync
        db.add(SyncLog(
            user_id=user_id,
            source="saxo",
            status="success",
            records_synced=synced,
        ))
        await db.commit()
        return synced

    except Exception as e:
        db.add(SyncLog(
            user_id=user_id,
            source="saxo",
            status="failed",
            records_synced=0,
            error_message=str(e)[:500],
        ))
        await db.commit()
        raise


async def create_portfolio_snapshot(db: AsyncSession, user_id: str) -> PortfolioSnapshot:
    """Create a daily snapshot of portfolio value."""
    result = await db.execute(
        select(StockPosition).where(StockPosition.user_id == user_id)
    )
    positions = result.scalars().all()

    total_value = sum((p.last_price or 0) * p.quantity for p in positions)
    total_cost = sum(p.avg_cost_price * p.quantity for p in positions)
    total_pnl = total_value - total_cost

    today = date.today()
    # Upsert for today
    result = await db.execute(
        select(PortfolioSnapshot).where(
            and_(
                PortfolioSnapshot.user_id == user_id,
                PortfolioSnapshot.snapshot_date == today,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.total_value = total_value
        existing.total_cost = total_cost
        existing.total_pnl = total_pnl
        snapshot = existing
    else:
        snapshot = PortfolioSnapshot(
            user_id=user_id,
            total_value=total_value,
            total_cost=total_cost,
            total_pnl=total_pnl,
            snapshot_date=today,
        )
        db.add(snapshot)

    await db.commit()
    await db.refresh(snapshot)
    return snapshot
