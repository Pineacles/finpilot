"""User settings service — DB-first with env var fallback."""
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.models.settings import UserSetting

# Setting keys and their env var fallbacks
SETTING_KEYS = {
    # Analysis
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "analysis_model": "ANALYSIS_MODEL",
    "analysis_endpoint": None,  # Custom endpoint for user's own AI agent
    # Saxo Bank
    "saxo_app_key": "SAXO_APP_KEY",
    "saxo_app_secret": "SAXO_APP_SECRET",
    "saxo_account_key": "SAXO_ACCOUNT_KEY",
    "saxo_token_url": "SAXO_TOKEN_URL",
    "saxo_api_url": "SAXO_API_URL",
    "saxo_access_token": None,
    "saxo_refresh_token": None,
    # Viseca
    "viseca_cookie": None,
    "viseca_card_id": None,
    # Custom agent
    "analysis_auth_header": None,  # e.g. "Bearer redacted-example-token"
}

# Keys that should be masked in API responses
SENSITIVE_KEYS = {"anthropic_api_key", "saxo_app_secret", "saxo_access_token", "saxo_refresh_token", "viseca_cookie", "analysis_auth_header"}


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
    """Get all settings for a user, merged with env fallbacks."""
    result = await db.execute(
        select(UserSetting).where(UserSetting.user_id == user_id)
    )
    db_settings = {s.key: s.value for s in result.scalars().all()}

    merged = {}
    for key, env_key in SETTING_KEYS.items():
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
