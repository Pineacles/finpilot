"""SaxoAdapter — implements BrokerAdapter against Saxo Bank OpenAPI.

Design notes:
    - All per-user state (credentials, tokens, PKCE verifiers) lives in the
      `user_settings` table. The adapter holds no mutable user state on `self`.
    - Every public call reads `saxo_enabled` first. When false, the call returns
      the "disabled" sentinel without touching the network or emitting logs.
    - Token refresh is serialized per user by an `asyncio.Lock`. Refresh tokens
      rotate on every use — the new access+refresh+expiry are persisted in a
      single `set_many_atomic()` commit. A crash mid-flight leaves the user
      with the old (now-invalid) refresh token; the next call will fail refresh
      and flip to NEEDS_AUTH rather than loop forever.
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import (
    AuthState,
    BrokerAccount,
    BrokerAdapter,
    BrokerBalance,
    BrokerPosition,
    ConnectionStatus,
    TradingDisabledError,
)
from app.brokers.saxo import config as saxo_config
from app.brokers.saxo import instruments as saxo_instruments
from app.brokers.saxo import mapping
from app.brokers.saxo.client import SaxoHTTPClient, SaxoHTTPError
from app.brokers.saxo.oauth import build_authorize_url
from app.brokers.saxo.orders import (
    BuySell,
    Duration,
    OrderAck,
    OrderRequest,
    OrderSummary,
    OrderType,
    PrecheckResult,
)
from app.services import settings as settings_svc

logger = logging.getLogger("app.brokers.saxo")

_ACCESS_TOKEN_SKEW_SECONDS = 60


class SaxoAdapter(BrokerAdapter):
    name = "saxo"

    def __init__(self) -> None:
        # One client per (environment, base_url) shared across users. Token-bucket
        # rate limiter inside the client caps at 60 rpm per client, which matches
        # Saxo's per-token budget well enough for a single-user deployment.
        self._clients: dict[str, SaxoHTTPClient] = {}
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    # ─── flag / config gates ──────────────────────────────────────────────
    async def is_enabled(self, db: AsyncSession, user_id: str) -> bool:
        value = await settings_svc.get_setting(db, user_id, "saxo_enabled")
        return _truthy(value)

    async def is_configured(self, db: AsyncSession, user_id: str) -> bool:
        app_key = await settings_svc.get_setting(db, user_id, "saxo_app_key")
        app_secret = await settings_svc.get_setting(db, user_id, "saxo_app_secret")
        redirect = await settings_svc.get_setting(db, user_id, "saxo_redirect_url")
        return bool(app_key and app_secret and redirect)

    # ─── auth lifecycle ───────────────────────────────────────────────────
    async def status(self, db: AsyncSession, user_id: str) -> ConnectionStatus:
        if not await self.is_enabled(db, user_id):
            return ConnectionStatus(state=AuthState.DISABLED)
        env_name = await self._env_name(db, user_id)
        if not await self.is_configured(db, user_id):
            return ConnectionStatus(state=AuthState.SETUP_REQUIRED, environment=env_name)
        access = await settings_svc.get_setting(db, user_id, "saxo_access_token")
        refresh = await settings_svc.get_setting(db, user_id, "saxo_refresh_token")
        last_error = await settings_svc.get_setting(db, user_id, "saxo_last_error")
        if not access and not refresh:
            state = AuthState.NEEDS_AUTH
        else:
            state = AuthState.CONNECTED
        return ConnectionStatus(state=state, environment=env_name, last_error=last_error or None)

    async def authenticate(self, db: AsyncSession, user_id: str) -> ConnectionStatus:
        """Start a fresh OAuth authorize flow. Returns a status whose `detail`
        carries the authorize URL for the UI to open in the browser."""
        if not await self.is_enabled(db, user_id):
            return ConnectionStatus(state=AuthState.DISABLED)
        if not await self.is_configured(db, user_id):
            return ConnectionStatus(state=AuthState.SETUP_REQUIRED)

        env = saxo_config.resolve(await self._env_name(db, user_id))
        app_key = await settings_svc.get_setting(db, user_id, "saxo_app_key")
        redirect = await settings_svc.get_setting(db, user_id, "saxo_redirect_url")

        built = build_authorize_url(
            authorize_endpoint=env.authorize_url,
            app_key=app_key,
            redirect_url=redirect,
        )
        await settings_svc.set_many_atomic(db, user_id, {
            "saxo_pkce_verifier": built.verifier,
            "saxo_oauth_state": built.state,
            "saxo_last_error": "",
        })
        logger.info("saxo auth=start user=%s env=%s", user_id, env.name)
        return ConnectionStatus(
            state=AuthState.CONNECTING,
            environment=env.name,
            detail=built.url,
        )

    async def complete_oauth(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        code: str,
        state: str,
    ) -> ConnectionStatus:
        """Callback handler: exchange the authorization code for tokens."""
        if not await self.is_enabled(db, user_id):
            return ConnectionStatus(state=AuthState.DISABLED)

        stored_state = await settings_svc.get_setting(db, user_id, "saxo_oauth_state")
        verifier = await settings_svc.get_setting(db, user_id, "saxo_pkce_verifier")
        if not stored_state or not verifier or stored_state != state:
            await self._record_error(db, user_id, "invalid oauth state")
            return ConnectionStatus(state=AuthState.ERROR, last_error="invalid_state")

        env_name = await self._env_name(db, user_id)
        env = saxo_config.resolve(env_name)
        app_key = await settings_svc.get_setting(db, user_id, "saxo_app_key")
        app_secret = await settings_svc.get_setting(db, user_id, "saxo_app_secret")
        redirect = await settings_svc.get_setting(db, user_id, "saxo_redirect_url")

        client = self._client_for(env.api_base, env.token_url)
        try:
            body = await client.token_post(form={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": app_key,
                "client_secret": app_secret,
                "code_verifier": verifier,
            })
        except SaxoHTTPError as exc:
            await self._record_error(db, user_id, f"token_exchange_failed:{exc.status}")
            return ConnectionStatus(state=AuthState.ERROR, environment=env_name, last_error="token_exchange_failed")

        await self._persist_tokens(db, user_id, body)
        await settings_svc.delete_keys(db, user_id, ["saxo_pkce_verifier", "saxo_oauth_state"])
        logger.info("saxo auth=complete user=%s env=%s", user_id, env.name)
        return ConnectionStatus(state=AuthState.CONNECTED, environment=env.name)

    async def disconnect(self, db: AsyncSession, user_id: str) -> None:
        await settings_svc.delete_keys(db, user_id, [
            "saxo_access_token",
            "saxo_refresh_token",
            "saxo_token_expires_at",
            "saxo_pkce_verifier",
            "saxo_oauth_state",
            "saxo_last_error",
        ])
        logger.info("saxo auth=disconnect user=%s", user_id)

    # ─── read operations ──────────────────────────────────────────────────
    async def health_check(self, db: AsyncSession, user_id: str) -> bool:
        if not await self.is_enabled(db, user_id):
            return False
        try:
            token, env = await self._token_and_env(db, user_id)
        except RuntimeError:
            return False
        if not token:
            return False
        client = self._client_for(env.api_base, env.token_url)
        try:
            await client.authed_get("/root/v1/diagnostics/get", access_token=token)
            return True
        except SaxoHTTPError:
            return False

    async def get_accounts(self, db: AsyncSession, user_id: str) -> list[BrokerAccount]:
        if not await self.is_enabled(db, user_id):
            return []
        token, env = await self._token_and_env(db, user_id)
        client = self._client_for(env.api_base, env.token_url)
        body = await client.authed_get("/port/v1/accounts/me", access_token=token)
        return mapping.accounts_from_saxo(body, env.name)

    async def get_balances(self, db: AsyncSession, user_id: str, account_key: str) -> BrokerBalance:
        if not await self.is_enabled(db, user_id):
            return BrokerBalance(account_external_id=account_key, cash=0.0, currency="")
        token, env = await self._token_and_env(db, user_id)
        client = self._client_for(env.api_base, env.token_url)
        client_key = await self._resolve_client_key(client, token, account_key)
        body = await client.authed_get(
            "/port/v1/balances",
            access_token=token,
            params={"ClientKey": client_key, "AccountKey": account_key},
        )
        return mapping.balance_from_saxo(body, account_external_id=account_key)

    async def get_positions(self, db: AsyncSession, user_id: str, account_key: str) -> list[BrokerPosition]:
        if not await self.is_enabled(db, user_id):
            return []
        token, env = await self._token_and_env(db, user_id)
        client = self._client_for(env.api_base, env.token_url)
        client_key = await self._resolve_client_key(client, token, account_key)
        body = await client.authed_get(
            "/port/v1/positions",
            access_token=token,
            params={
                "ClientKey": client_key,
                "AccountKey": account_key,
                "FieldGroups": "DisplayAndFormat,PositionBase,PositionView",
            },
        )
        return mapping.positions_from_saxo(body, account_external_id=account_key)

    # ─── live prices ──────────────────────────────────────────────────────
    async def get_live_prices(
        self, db: AsyncSession, user_id: str, *, symbols: list[str]
    ) -> dict[str, dict]:
        """Return Saxo-native live quotes keyed by symbol. Empty dict when disabled
        or the symbols can't be resolved. Missing symbols are simply omitted."""
        if not symbols or not await self.is_enabled(db, user_id):
            return {}
        try:
            token, env = await self._token_and_env(db, user_id)
        except RuntimeError:
            return {}
        client = self._client_for(env.api_base, env.token_url)

        out: dict[str, dict] = {}
        uic_to_symbol: dict[int, str] = {}
        for symbol in {s.upper() for s in symbols}:
            try:
                inst = await saxo_instruments.lookup(client, access_token=token, symbol=symbol)
            except (saxo_instruments.InstrumentNotFound, SaxoHTTPError):
                continue
            uic_to_symbol[inst.uic] = symbol

        if not uic_to_symbol:
            return out

        uic_csv = ",".join(str(u) for u in uic_to_symbol.keys())
        try:
            body = await client.authed_get(
                "/trade/v1/infoprices/list",
                access_token=token,
                params={
                    "Uics": uic_csv,
                    "AssetType": "Stock",
                    "FieldGroups": "PriceInfo,Quote,PriceInfoDetails",
                },
            )
        except SaxoHTTPError:
            return out

        for row in body.get("Data", []) if isinstance(body, dict) else []:
            uic = int(row.get("Uic") or 0)
            symbol = uic_to_symbol.get(uic)
            if not symbol:
                continue
            quote = row.get("Quote") or {}
            price_info = row.get("PriceInfo") or {}
            last = quote.get("Mid") or quote.get("Ask") or quote.get("Bid") or price_info.get("LastTraded")
            net_change = price_info.get("NetChange")
            pct_change = price_info.get("PercentChange")
            if last is None:
                continue
            out[symbol] = {
                "price": float(last),
                "change": float(net_change) if net_change is not None else 0.0,
                "change_pct": float(pct_change) if pct_change is not None else 0.0,
                "source": "saxo",
            }
        return out

    # ─── trading ──────────────────────────────────────────────────────────
    async def precheck_order(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        account_key: str,
        symbol: str,
        buy_sell: BuySell,
        amount: float,
        order_type: OrderType = "Market",
        duration: Duration = "DayOrder",
        limit_price: float | None = None,
        stop_price: float | None = None,
        asset_type: str = "Stock",
    ) -> PrecheckResult:
        token, env, client = await self._trading_gate(db, user_id)
        instrument = await saxo_instruments.lookup(
            client, access_token=token, symbol=symbol, asset_type=asset_type
        )
        order = OrderRequest(
            account_key=account_key,
            uic=instrument.uic,
            asset_type=instrument.asset_type,
            buy_sell=buy_sell,
            amount=amount,
            order_type=order_type,
            duration=duration,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        body = await client.authed_post(
            "/trade/v2/orders/precheck",
            access_token=token,
            json=order.to_payload(),
        )
        return PrecheckResult.from_saxo(body)

    async def place_order(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        account_key: str,
        symbol: str,
        buy_sell: BuySell,
        amount: float,
        order_type: OrderType = "Market",
        duration: Duration = "DayOrder",
        limit_price: float | None = None,
        stop_price: float | None = None,
        asset_type: str = "Stock",
    ) -> OrderAck:
        token, env, client = await self._trading_gate(db, user_id)
        instrument = await saxo_instruments.lookup(
            client, access_token=token, symbol=symbol, asset_type=asset_type
        )
        order = OrderRequest(
            account_key=account_key,
            uic=instrument.uic,
            asset_type=instrument.asset_type,
            buy_sell=buy_sell,
            amount=amount,
            order_type=order_type,
            duration=duration,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        body = await client.authed_post(
            "/trade/v2/orders",
            access_token=token,
            json=order.to_payload(),
        )
        return OrderAck.from_saxo(body)

    async def cancel_order(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        order_id: str,
        account_key: str,
    ) -> None:
        token, env, client = await self._trading_gate(db, user_id)
        await client.authed_delete(
            f"/trade/v2/orders/{order_id}",
            access_token=token,
            params={"AccountKey": account_key},
        )

    async def modify_order(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        order_id: str,
        account_key: str,
        amount: float | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        duration: Duration | None = None,
    ) -> None:
        """Saxo's PATCH /trade/v2/orders requires the full order payload (OrderId,
        Uic, AssetType, OrderType, BuySell, Amount, price, duration). We fetch
        the current order, merge the caller's changes, and send the complete
        payload. One extra round-trip but simpler ergonomics."""
        token, env, client = await self._trading_gate(db, user_id)
        client_key = await self._resolve_client_key(client, token, account_key)
        body = await client.authed_get(
            "/port/v1/orders/me",
            access_token=token,
            params={"ClientKey": client_key, "AccountKey": account_key},
        )
        current = next(
            (
                r for r in (body.get("Data", []) if isinstance(body, dict) else [])
                if str(r.get("OrderId")) == str(order_id)
            ),
            None,
        )
        if current is None:
            raise RuntimeError(f"order {order_id} not found on account {account_key}")

        current_duration = (current.get("Duration") or {}).get("DurationType") or "DayOrder"
        payload: dict = {
            "OrderId": order_id,
            "AccountKey": account_key,
            "Uic": current["Uic"],
            "AssetType": current.get("AssetType", "Stock"),
            "OrderType": current.get("OpenOrderType") or current.get("OrderType", "Limit"),
            "BuySell": current["BuySell"],
            "Amount": amount if amount is not None else current.get("Amount"),
            "OrderDuration": {"DurationType": duration or current_duration},
        }
        existing_price = current.get("Price") or current.get("OrderPrice")
        new_limit = limit_price if limit_price is not None else existing_price
        if new_limit is not None:
            payload["OrderPrice"] = new_limit
        if stop_price is not None:
            payload["StopLimitPrice"] = stop_price
        await client.authed_patch(
            "/trade/v2/orders",
            access_token=token,
            json=payload,
        )

    async def get_orders(
        self, db: AsyncSession, user_id: str, account_key: str
    ) -> list[OrderSummary]:
        if not await self.is_enabled(db, user_id):
            return []
        try:
            token, env = await self._token_and_env(db, user_id)
        except RuntimeError:
            return []
        client = self._client_for(env.api_base, env.token_url)
        client_key = await self._resolve_client_key(client, token, account_key)
        body = await client.authed_get(
            "/port/v1/orders/me",
            access_token=token,
            params={
                "ClientKey": client_key,
                "AccountKey": account_key,
                "FieldGroups": "DisplayAndFormat",
            },
        )
        return [OrderSummary.from_saxo(r) for r in (body.get("Data", []) if isinstance(body, dict) else [])]

    async def _trading_gate(self, db: AsyncSession, user_id: str):
        """Return (token, env, client) if trading is permitted; otherwise raise."""
        if not await self.is_enabled(db, user_id):
            raise TradingDisabledError("Saxo is disabled for this user.")
        trading_flag = await settings_svc.get_setting(db, user_id, "saxo_trading_enabled")
        if not _truthy(trading_flag):
            raise TradingDisabledError("Saxo trading is not enabled for this user.")
        try:
            token, env = await self._token_and_env(db, user_id)
        except RuntimeError:
            raise RuntimeError("needs_auth") from None
        client = self._client_for(env.api_base, env.token_url)
        return token, env, client

    # ─── internals ────────────────────────────────────────────────────────
    async def _env_name(self, db: AsyncSession, user_id: str) -> str:
        raw = await settings_svc.get_setting(db, user_id, "saxo_environment")
        return (raw or "sim").strip().lower()

    def _client_for(self, base_url: str, token_url: str) -> SaxoHTTPClient:
        key = f"{base_url}|{token_url}"
        client = self._clients.get(key)
        if client is None:
            client = SaxoHTTPClient(base_url=base_url, token_url=token_url)
            self._clients[key] = client
        return client

    def _refresh_lock(self, user_id: str) -> asyncio.Lock:
        lock = self._refresh_locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._refresh_locks[user_id] = lock
        return lock

    async def _token_and_env(self, db: AsyncSession, user_id: str):
        """Return (access_token, environment). Refreshes the access token if expired.

        Raises `RuntimeError("needs_auth")` if the user has no refresh token or
        the refresh attempt fails — the caller should map that to AuthState.NEEDS_AUTH.
        """
        env = saxo_config.resolve(await self._env_name(db, user_id))
        expires_at = _as_int(await settings_svc.get_setting(db, user_id, "saxo_token_expires_at"))
        access = await settings_svc.get_setting(db, user_id, "saxo_access_token")
        if access and expires_at > time.time() + _ACCESS_TOKEN_SKEW_SECONDS:
            return access, env
        return await self._refresh(db, user_id, env), env

    async def _refresh(self, db: AsyncSession, user_id: str, env) -> str:
        async with self._refresh_lock(user_id):
            # Recheck inside the lock — another coroutine may have refreshed.
            expires_at = _as_int(await settings_svc.get_setting(db, user_id, "saxo_token_expires_at"))
            access = await settings_svc.get_setting(db, user_id, "saxo_access_token")
            if access and expires_at > time.time() + _ACCESS_TOKEN_SKEW_SECONDS:
                return access

            refresh_token = await settings_svc.get_setting(db, user_id, "saxo_refresh_token")
            if not refresh_token:
                raise RuntimeError("needs_auth")

            app_key = await settings_svc.get_setting(db, user_id, "saxo_app_key")
            app_secret = await settings_svc.get_setting(db, user_id, "saxo_app_secret")
            client = self._client_for(env.api_base, env.token_url)
            try:
                body = await client.token_post(form={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": app_key,
                    "client_secret": app_secret,
                })
            except SaxoHTTPError as exc:
                # Saxo invalidated the refresh token — force re-auth.
                await settings_svc.delete_keys(db, user_id, [
                    "saxo_access_token",
                    "saxo_refresh_token",
                    "saxo_token_expires_at",
                ])
                await self._record_error(db, user_id, f"refresh_failed:{exc.status}")
                raise RuntimeError("needs_auth") from None

            await self._persist_tokens(db, user_id, body, fallback_refresh=refresh_token)
            return body["access_token"]

    async def _persist_tokens(
        self,
        db: AsyncSession,
        user_id: str,
        body: dict,
        *,
        fallback_refresh: str | None = None,
    ) -> None:
        access = body["access_token"]
        refresh = body.get("refresh_token") or fallback_refresh or ""
        expires_in = int(body.get("expires_in") or 1200)
        expires_at = int(time.time()) + expires_in
        await settings_svc.set_many_atomic(db, user_id, {
            "saxo_access_token": access,
            "saxo_refresh_token": refresh,
            "saxo_token_expires_at": str(expires_at),
            "saxo_last_error": "",
        })

    async def _record_error(self, db: AsyncSession, user_id: str, detail: str) -> None:
        await settings_svc.set_many_atomic(db, user_id, {"saxo_last_error": detail[:200]})

    async def _resolve_client_key(self, client: SaxoHTTPClient, token: str, account_key: str) -> str:
        """Saxo account queries need both `ClientKey` and `AccountKey`. We derive
        ClientKey from /accounts/me on demand; cached values get stale on Saxo's
        side if the account binding changes, so we just fetch fresh each call."""
        body = await client.authed_get("/port/v1/accounts/me", access_token=token)
        for account in body.get("Data", []):
            if account.get("AccountKey") == account_key:
                return account.get("ClientKey") or "me"
        return "me"


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
