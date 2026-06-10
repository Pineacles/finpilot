from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.settings import get_all_settings, set_many, SETTING_KEYS, SENSITIVE_KEYS, HIDDEN_KEYS

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


@router.get("")
async def get_settings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    all_settings = await get_all_settings(db, user.id)
    return {
        "api_key": user.api_key,
        "settings": all_settings,
        "groups": {
            "analysis": {
                "label": "AI Analysis",
                "keys": ["anthropic_api_key", "analysis_model", "analysis_endpoint", "analysis_auth_header"],
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


@router.put("")
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
