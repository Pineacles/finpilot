import logging
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.core.security import generate_api_key, hash_api_key
from app.models.user import User
from app.schemas.user_settings import (
    SettingsGetResponse,
    SettingsUpdate,
    SettingsUpdateResponse,
    ApiKeyRegenerateResponse,
    AiTestResponse,
)
from app.services.settings import get_all_settings, set_many, SETTING_KEYS, HIDDEN_KEYS
from app.services.categorize import (
    load_ai_config,
    _build_category_tree_prompt,
    _build_prompt,
    _parse_ai_results,
    _call_ai,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

AI_PROVIDERS = {"", "anthropic", "openai", "custom"}
AI_ENABLED_VALUES = {"", "0", "1"}

# Fixed sample transactions for POST /api/settings/ai/test: exercises a real
# call to the configured backend without touching the user's own data.
_AI_TEST_TRANSACTIONS = [
    {"id": "sample-1", "merchant": "Migros Zuerich", "amount": -23.50, "description": "Migros Zuerich"},
    {"id": "sample-2", "merchant": "SBB EasyRide", "amount": -8.40, "description": "SBB EasyRide"},
]


def _validate_url_setting(value: str, field_name: str) -> None:
    """Reject a non-empty setting that isn't a valid http(s) URL."""
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(status_code=400, detail=f"{field_name}: must be a valid http:// or https:// URL")


def _mask_api_key(key: str) -> str:
    """Placeholder shown for an existing key. Only a hash is stored, so no
    part of the real key can be displayed."""
    return "••••••••••••" if key else ""


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
    if "ai_provider" in valid and valid["ai_provider"] not in AI_PROVIDERS:
        raise HTTPException(status_code=400, detail="ai_provider must be one of '', 'anthropic', 'openai', 'custom'.")
    if "ai_enabled" in valid and valid["ai_enabled"] not in AI_ENABLED_VALUES:
        raise HTTPException(status_code=400, detail="ai_enabled must be '', '0', or '1'.")
    if "ai_base_url" in valid:
        _validate_url_setting(valid["ai_base_url"], "ai_base_url")
    if "ai_endpoint" in valid:
        _validate_url_setting(valid["ai_endpoint"], "ai_endpoint")
    if "ai_search_url" in valid:
        _validate_url_setting(valid["ai_search_url"], "ai_search_url")
    await set_many(db, user.id, valid)
    return {"status": "ok", "updated": list(valid.keys())}


@router.post("/ai/test", response_model=AiTestResponse)
async def test_ai(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run one live call against the user's configured AI backend using two
    hardcoded sample transactions. Read-only: never writes to the DB.
    """
    config = await load_ai_config(db, user.id)
    if not config.enabled:
        return {
            "ok": False,
            "provider": config.provider,
            "model": config.model,
            "latency_ms": 0,
            "error": "AI categorization is disabled or not configured. Set an API key or endpoint in Settings and enable it.",
            "results": [],
        }

    cat_tree_prompt, categories = await _build_category_tree_prompt(db, user.id)
    prompt = _build_prompt(cat_tree_prompt, _AI_TEST_TRANSACTIONS)

    start = time.monotonic()
    chunk_results, error = await _call_ai(config, prompt, _AI_TEST_TRANSACTIONS)
    latency_ms = int((time.monotonic() - start) * 1000)

    mapped = _parse_ai_results(chunk_results, _AI_TEST_TRANSACTIONS, categories)
    results = [
        {"merchant": txn["merchant"], "category": r["category_name"], "confidence": r["confidence"]}
        for txn, r in zip(_AI_TEST_TRANSACTIONS, mapped)
    ]
    matched = sum(1 for r in mapped if r["category_id"])

    return {
        "ok": error is None and matched > 0,
        "provider": config.provider,
        "model": config.model,
        "latency_ms": latency_ms,
        "error": error,
        "results": results,
    }


@router.post("/api-key/regenerate", response_model=ApiKeyRegenerateResponse)
async def regenerate_api_key(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key for the authenticated user.

    Returns the new key ONCE in plain text: store it immediately.
    The old key is invalidated; any agents using it must be updated.
    """
    new_key = generate_api_key()
    user.api_key = hash_api_key(new_key)
    await db.commit()
    logger.info("API key regenerated for user %s", user.id[:8])
    return {"api_key": new_key, "message": "Store this key immediately, it will not be shown again."}
