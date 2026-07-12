"""Low-level HTTP transport for the Saxo adapter.

Responsibilities:
    - enforce per-user rate limiting (~60 req/min)
    - enforce 10s timeout and a single retry on 5xx / transport error
    - emit redacted INFO logs per call
    - never log Authorization, refresh tokens, app secrets, or payload bodies

Higher-level concerns (auth state, PKCE, DTO mapping) live elsewhere.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("app.brokers.saxo")

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_RATE_LIMIT_PER_MIN = 60
_RATE_WINDOW_SECONDS = 60.0
_RETRY_BACKOFF_SECONDS = (0.5, 1.5)  # (first_wait,); retry count fixed at 1


class SaxoHTTPError(RuntimeError):
    """Raised on non-retryable HTTP failure. `status` is None on network error."""

    def __init__(self, status: int | None, method: str, path: str, detail: str):
        super().__init__(f"saxo {method} {path} → {status or 'network'}: {detail}")
        self.status = status
        self.method = method
        self.path = path
        self.detail = detail


@dataclass
class _RateLimiter:
    """Trailing-window limiter. One instance per user-token to bound concurrency."""

    window_seconds: float = _RATE_WINDOW_SECONDS
    max_requests: int = _RATE_LIMIT_PER_MIN

    def __post_init__(self) -> None:
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] > self.window_seconds:
                self._calls.popleft()
            if len(self._calls) >= self.max_requests:
                wait_for = self.window_seconds - (now - self._calls[0])
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                    now = time.monotonic()
                    while self._calls and now - self._calls[0] > self.window_seconds:
                        self._calls.popleft()
            self._calls.append(time.monotonic())


class SaxoHTTPClient:
    """Thin wrapper over httpx.AsyncClient with rate limit + retry + redacted logs.

    One instance per (user, environment). The instance holds no secrets directly:
    tokens are passed in on each call by the adapter.
    """

    def __init__(self, *, base_url: str, token_url: str):
        self._base_url = base_url.rstrip("/")
        self._token_url = token_url
        self._client = httpx.AsyncClient(timeout=_TIMEOUT)
        self._limiter = _RateLimiter()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def token_url(self) -> str:
        return self._token_url

    async def close(self) -> None:
        await self._client.aclose()

    async def authed_get(self, path: str, *, access_token: str, params: dict | None = None) -> dict:
        return await self._request("GET", path, access_token=access_token, params=params)

    async def authed_post(
        self, path: str, *, access_token: str, json: dict, params: dict | None = None
    ) -> dict:
        return await self._request(
            "POST", path, access_token=access_token, params=params, json_body=json
        )

    async def authed_patch(
        self, path: str, *, access_token: str, json: dict, params: dict | None = None
    ) -> dict:
        return await self._request(
            "PATCH", path, access_token=access_token, params=params, json_body=json
        )

    async def authed_delete(
        self, path: str, *, access_token: str, params: dict | None = None
    ) -> dict:
        return await self._request("DELETE", path, access_token=access_token, params=params)

    async def token_post(self, *, form: dict[str, str]) -> dict:
        """POST to the token endpoint. Does NOT retry (token exchanges must not
        double-fire: a refresh token rotates on first use)."""
        await self._limiter.acquire()
        start = time.monotonic()
        try:
            resp = await self._client.post(self._token_url, data=form)
        except httpx.HTTPError as exc:
            duration = _ms(start)
            logger.info("saxo method=POST path=/token status=network duration_ms=%s", duration)
            raise SaxoHTTPError(None, "POST", "/token", str(exc)) from None
        duration = _ms(start)
        logger.info("saxo method=POST path=/token status=%s duration_ms=%s", resp.status_code, duration)
        if resp.status_code >= 400:
            raise SaxoHTTPError(resp.status_code, "POST", "/token", _safe_detail(resp))
        return resp.json()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {access_token}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        async def _once() -> httpx.Response:
            await self._limiter.acquire()
            return await self._client.request(
                method, url, headers=headers, params=params, json=json_body
            )

        start = time.monotonic()
        # Only retry idempotent methods; never retry POST/PATCH/DELETE since an
        # order might fire twice.
        can_retry = method.upper() in {"GET", "HEAD"}
        try:
            resp = await _once()
            if resp.status_code >= 500 and can_retry:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS[0])
                resp = await _once()
        except httpx.HTTPError as exc:
            if not can_retry:
                duration = _ms(start)
                logger.info("saxo method=%s path=%s status=network duration_ms=%s", method, path, duration)
                raise SaxoHTTPError(None, method, path, str(exc)) from None
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS[0])
            try:
                resp = await _once()
            except httpx.HTTPError as exc2:
                duration = _ms(start)
                logger.info("saxo method=%s path=%s status=network duration_ms=%s", method, path, duration)
                raise SaxoHTTPError(None, method, path, str(exc2)) from None

        duration = _ms(start)
        logger.info("saxo method=%s path=%s status=%s duration_ms=%s", method, path, resp.status_code, duration)
        if resp.status_code >= 400:
            raise SaxoHTTPError(resp.status_code, method, path, _safe_detail(resp))
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {}


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _safe_detail(resp: httpx.Response) -> str:
    """Non-leaky error detail: status+error code only, no raw body echo."""
    try:
        data = resp.json()
        code = data.get("ErrorCode") or data.get("error") or ""
        return str(code)[:120] if code else f"http_{resp.status_code}"
    except ValueError:
        return f"http_{resp.status_code}"
