import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.core.security import generate_api_key
from app.models.user import User
from app.schemas.user_settings import (
    SettingsGetResponse,
    SettingsUpdate,
    SettingsUpdateResponse,
    ApiKeyRegenerateResponse,
)
from app.services.settings import get_all_settings, set_many, SETTING_KEYS, HIDDEN_KEYS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _mask_api_key(key: str) -> str:
    """Return a masked API key showing only the last 4 characters."""
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    return "••••••••••••" + key[-4:]


@router.get("", response_model=SettingsGetResponse)
async def get_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    all_settings = await get_all_settings(db, user.id)
    return {
        "api_key": _mask_api_key(user.api_key or ""),
        "settings": all_settings,
        "groups": {
            "ai": {
                "label": "AI categorization",
                "keys": ["anthropic_api_key", "ai_model", "ai_endpoint", "ai_auth_header"],
            },
            "agent": {
                "label": "Agent",
                "keys": ["agent_endpoint", "agent_auth_header"],
            },
            "gmail": {
                "label": "Gmail (Bank Notifications)",
                "keys": ["gmail_address", "gmail_app_password", "gmail_sender_filter", "gmail_poll_interval"],
            },
        },
    }


@router.put("", response_model=SettingsUpdateResponse)
async def update_settings(
    body: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Filter out unknown keys and internal state (tokens, verifiers)
    valid = {k: v for k, v in body.settings.items() if k in SETTING_KEYS and k not in HIDDEN_KEYS}
    # Defense-in-depth: reject saxo_environment=live; LIVE is not available yet.
    if valid.get("saxo_environment") and valid["saxo_environment"].lower() != "sim":
        raise HTTPException(status_code=400, detail="saxo_environment: only 'sim' is enabled in this release.")
    await set_many(db, user.id, valid)
    return {"status": "ok", "updated": list(valid.keys())}


@router.post("/api-key/regenerate", response_model=ApiKeyRegenerateResponse)
async def regenerate_api_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key for the authenticated user.

    Returns the new key ONCE in plain text — store it immediately.
    The old key is invalidated; any agents using it must be updated.
    """
    new_key = generate_api_key()
    user.api_key = new_key
    await db.commit()
    logger.info("API key regenerated for user %s", user.id[:8])
    return {"api_key": new_key, "message": "Store this key immediately — it will not be shown again."}
