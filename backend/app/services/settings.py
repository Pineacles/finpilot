"""User settings service — DB-first with env var fallback."""
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.models.settings import UserSetting

# Setting keys and their env var fallbacks
SETTING_KEYS = {
    # Analysis / AI
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "analysis_model": "ANALYSIS_MODEL",
    "analysis_endpoint": None,
    "analysis_auth_header": None,
    # Agent (NanoClaw) — can scrape banks, fetch data, run tasks
    "agent_endpoint": None,  # e.g. https://assistant.example.ch/api/finpilot
    "agent_auth_header": None,
    # Gmail (for bank email notifications)
    "gmail_address": None,
    "gmail_app_password": None,
    "gmail_last_uid": None,
    "gmail_poll_interval": None,
    "gmail_sender_filter": None,
    # Saxo Bank broker adapter — see app/brokers/saxo/
    "saxo_enabled": None,
    "saxo_trading_enabled": None,
    "saxo_environment": None,  # "sim" | "live" (LIVE rejected at write time this release)
    "saxo_app_key": None,
    "saxo_app_secret": None,
    "saxo_redirect_url": None,
    "saxo_access_token": None,
    "saxo_refresh_token": None,
    "saxo_token_expires_at": None,  # unix seconds
    "saxo_pkce_verifier": None,
    "saxo_oauth_state": None,
    "saxo_last_error": None,
}

# Keys that should be masked in API responses
SENSITIVE_KEYS = {
    "anthropic_api_key",
    "analysis_auth_header",
    "agent_auth_header",
    "gmail_app_password",
    "saxo_app_secret",
    "saxo_access_token",
    "saxo_refresh_token",
    "saxo_pkce_verifier",
    "saxo_oauth_state",
}

# Keys that should NEVER be returned in any API response, even masked.
# These are internal state (verifiers, short-lived tokens) that the UI never needs.
HIDDEN_KEYS = {
    "saxo_access_token",
    "saxo_refresh_token",
    "saxo_token_expires_at",
    "saxo_pkce_verifier",
    "saxo_oauth_state",
}


async def get_setting(db: AsyncSession, user_id: str, key: str) -> str:
    """Get a setting value. DB first, then env var fallback."""
    result = await db.execute(
        select(UserSetting).where(
            and_(UserSetting.user_id == user_id, UserSetting.key == key)
        )
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        return setting.value

    # Env var fallback
    env_key = SETTING_KEYS.get(key)
    if env_key:
        return getattr(env_settings, env_key, "")
    return ""


async def get_all_settings(db: AsyncSession, user_id: str) -> dict[str, str]:
    """Get all settings for a user, merged with env fallbacks.

    Hidden keys (internal token/verifier state) are stripped entirely. Sensitive
    keys are masked.
    """
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == user_id)
    )
    db_settings = {s.key: s.value for s in result.scalars().all()}

    merged = {}
    for key, env_key in SETTING_KEYS.items():
        if key in HIDDEN_KEYS:
            continue
        value = db_settings.get(key, "")
        if not value and env_key:
            value = getattr(env_settings, env_key, "")
        # Mask sensitive values
        if key in SENSITIVE_KEYS and value:
            merged[key] = value[:4] + "..." + value[-4:] if len(value) > 8 else "****"
        else:
            merged[key] = value
    return merged


async def set_setting(db: AsyncSession, user_id: str, key: str, value: str) -> None:
    """Set a setting value in DB."""
    if key not in SETTING_KEYS:
        raise ValueError(f"Unknown setting key: {key}")

    result = await db.execute(
        select(UserSetting).where(
            and_(UserSetting.user_id == user_id, UserSetting.key == key)
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
    else:
        db.add(UserSetting(user_id=user_id, key=key, value=value))
    await db.commit()


async def set_many(db: AsyncSession, user_id: str, settings: dict[str, str]) -> None:
    """Set multiple settings at once."""
    for key, value in settings.items():
        if key in SETTING_KEYS and value is not None:
            await set_setting(db, user_id, key, value)


async def set_many_atomic(db: AsyncSession, user_id: str, settings: dict[str, str]) -> None:
    """Upsert many settings in a single transaction — commits once at the end.

    Use this when multiple keys must move together (e.g. an access+refresh+expiry
    triple after an OAuth token exchange). A crash before the commit leaves the
    DB in its pre-call state.
    """
    unknown = [k for k in settings if k not in SETTING_KEYS]
    if unknown:
        raise ValueError(f"Unknown setting keys: {unknown}")

    existing = await db.execute(
        select(UserSetting).where(
            and_(UserSetting.user_id == user_id, UserSetting.key.in_(list(settings.keys())))
        )
    )
    by_key = {s.key: s for s in existing.scalars().all()}
    for key, value in settings.items():
        if value is None:
            continue
        if key in by_key:
            by_key[key].value = value
        else:
            db.add(UserSetting(user_id=user_id, key=key, value=value))
    await db.commit()


async def delete_keys(db: AsyncSession, user_id: str, keys: list[str]) -> None:
    """Delete the given settings for a user. Used by disconnect flows."""
    if not keys:
        return
    result = await db.execute(
        select(UserSetting).where(
            and_(UserSetting.user_id == user_id, UserSetting.key.in_(keys))
        )
    )
    for setting in result.scalars().all():
        await db.delete(setting)
    await db.commit()
