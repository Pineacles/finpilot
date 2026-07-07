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
import json
import logging
import random
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.base import (
    AuthState,
    BrokerAccount,
    BrokerAdapter,
    BrokerBalance,
    BrokerPosition,
    ConnectionStatus,
)
from app.brokers.saxo import config as saxo_config
from app.brokers.saxo import instruments as saxo_instruments
from app.brokers.saxo import mapping
from app.brokers.saxo import oauth as saxo_oauth
from app.brokers.saxo.client import SaxoHTTPClient, SaxoHTTPError
from app.brokers.saxo.oauth import build_authorize_url
from app.services import settings as settings_svc

logger = logging.getLogger("app.brokers.saxo")

_ACCESS_TOKEN_SKEW_SECONDS = 300  # 5-minute early-refresh buffer
_REFRESH_MAX_ATTEMPTS = 3
_REFRESH_BACKOFF_BASE_SECONDS = 2.0  # 2s, 8s, 32s (+ small jitter)


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
        needs_reauth = await settings_svc.get_setting(db, user_id, "saxo_needs_reauth")
        if needs_reauth == "1" or (not access and not refresh):
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
            "saxo_needs_reauth",
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
        """Refresh the access token with retry + classification.

        Transient errors (5xx, network, 429) retry with exponential backoff.
        Permanent errors (400/401/403 with invalid_grant etc.) delete stored
        tokens and flip `saxo_needs_reauth=1` so the UI can prompt Reconnect.
        """
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

            last_error = ""
            for attempt in range(1, _REFRESH_MAX_ATTEMPTS + 1):
                try:
                    body = await client.token_post(form={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": app_key,
                        "client_secret": app_secret,
                    })
                except SaxoHTTPError as exc:
                    oauth_error = _extract_oauth_error(exc.detail)
                    permanent = saxo_oauth.classify_refresh_error(
                        http_status=exc.status, oauth_error=oauth_error,
                    )
                    last_error = f"{exc.status or 'net'}:{oauth_error or exc.detail[:40]}"
                    logger.warning(
                        "saxo refresh attempt=%s user=%s status=%s permanent=%s oauth=%s",
                        attempt, user_id, exc.status, permanent, oauth_error or "-",
                    )
                    if permanent:
                        # Refresh token is dead — clear and require re-auth.
                        await settings_svc.delete_keys(db, user_id, [
                            "saxo_access_token",
                            "saxo_refresh_token",
                            "saxo_token_expires_at",
                        ])
                        await settings_svc.set_many_atomic(db, user_id, {
                            "saxo_needs_reauth": "1",
                            "saxo_last_error": f"refresh_failed:{last_error}"[:200],
                        })
                        raise RuntimeError("needs_auth") from None
                    if attempt < _REFRESH_MAX_ATTEMPTS:
                        delay = _REFRESH_BACKOFF_BASE_SECONDS * (4 ** (attempt - 1))
                        delay += random.uniform(0, 1.5)
                        await asyncio.sleep(delay)
                        continue
                    # Exhausted retries on transient error — record but keep tokens.
                    await self._record_error(db, user_id, f"refresh_transient_exhausted:{last_error}")
                    raise RuntimeError("needs_auth") from None

                await self._persist_tokens(db, user_id, body, fallback_refresh=refresh_token)
                return body["access_token"]

            # Should be unreachable — the loop always continues or raises.
            raise RuntimeError("needs_auth")

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
            "saxo_needs_reauth": "0",
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


def _extract_oauth_error(detail: str | None) -> str | None:
    """Parse the `error` field out of an OAuth2 token error body.

    `detail` comes from SaxoHTTPClient._safe_detail, which hands back either
    the raw error code or a short `http_NNN`. When Saxo's token endpoint
    returns a JSON body we can also see it in detail — try both shapes.
    """
    if not detail:
        return None
    s = detail.strip()
    if not s:
        return None
    if s.startswith("{"):
        try:
            obj = json.loads(s)
            err = obj.get("error") if isinstance(obj, dict) else None
            if isinstance(err, str):
                return err
        except Exception:
            return None
        return None
    if s.startswith("http_"):
        return None
    # Plain `invalid_grant`, `invalid_client`, etc.
    return s.split()[0] if " " in s else s


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
