"""Background scheduler for proactive Saxo token refresh.

Runs every 5 minutes. For each user with Saxo enabled and a refresh token,
triggers a refresh if the access token is within 10 minutes of expiring.
This keeps tokens alive without waiting for user-initiated API calls — which
is the only thing that would otherwise refresh under the reactive path.

Started from the FastAPI lifespan in `app.main`.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, and_

from app.core.database import async_session
from app.models.settings import UserSetting

logger = logging.getLogger("app.brokers.saxo.scheduler")

_task: asyncio.Task | None = None

_TICK_SECONDS = 300               # Run every 5 minutes
_PROACTIVE_REFRESH_BUFFER = 600   # Refresh if < 10 min remaining


async def _users_to_refresh() -> list[str]:
    """Return user_ids with Saxo enabled + a refresh token + approaching expiry."""
    async with async_session() as db:
        # Grab saxo_enabled + saxo_refresh_token + saxo_token_expires_at + saxo_needs_reauth
        result = await db.execute(
            select(UserSetting.user_id, UserSetting.key, UserSetting.value).where(
                UserSetting.key.in_([
                    "saxo_enabled",
                    "saxo_refresh_token",
                    "saxo_token_expires_at",
                    "saxo_needs_reauth",
                ])
            )
        )
        by_user: dict[str, dict[str, str]] = {}
        for user_id, key, value in result.all():
            by_user.setdefault(user_id, {})[key] = value or ""

    now = int(time.time())
    users: list[str] = []
    for user_id, kv in by_user.items():
        if kv.get("saxo_enabled") != "1":
            continue
        if not kv.get("saxo_refresh_token"):
            continue
        if kv.get("saxo_needs_reauth") == "1":
            continue  # Nothing we can do — user must re-auth via the UI
        try:
            expires_at = int(kv.get("saxo_token_expires_at") or "0")
        except (ValueError, TypeError):
            expires_at = 0
        # If token is already past-expiry or within the buffer, refresh.
        if expires_at - now <= _PROACTIVE_REFRESH_BUFFER:
            users.append(user_id)
    return users


async def _refresh_one(user_id: str) -> None:
    """Trigger the adapter's refresh for a single user. Swallows errors —
    the adapter already records them to `saxo_last_error` / `saxo_needs_reauth`."""
    from app.brokers import get_adapter
    adapter = get_adapter("saxo")
    async with async_session() as db:
        try:
            # _token_and_env triggers _refresh() when the current access is near expiry.
            await adapter._token_and_env(db, user_id)
            logger.info("saxo scheduler refreshed user=%s", user_id)
        except RuntimeError as e:
            # needs_auth — adapter already recorded the error and flipped the flag.
            logger.info("saxo scheduler refresh_failed user=%s reason=%s", user_id, e)
        except Exception as e:
            logger.warning("saxo scheduler refresh_error user=%s %s: %s",
                           user_id, type(e).__name__, e)


async def _loop() -> None:
    """Every TICK_SECONDS, find near-expiry tokens and refresh them."""
    logger.info("Saxo refresh scheduler started")
    while True:
        try:
            users = await _users_to_refresh()
            for uid in users:
                await _refresh_one(uid)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("saxo scheduler tick error: %s", e)
        await asyncio.sleep(_TICK_SECONDS)


def start_scheduler() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop_scheduler() -> None:
    global _task
    if _task is not None and not _task.done():
        _task.cancel()
        _task = None
