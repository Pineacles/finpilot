"""PUT /api/settings and POST /api/settings/ai/test, endpoint-level:
validation 400s for bad ai_provider / ai_enabled / non-http ai_base_url, and
the unconfigured-user response from the AI test endpoint. Endpoint handlers
are called directly (no HTTP transport), matching the pattern in
tests/api/test_watchlist_endpoints.py.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.endpoints.user_settings import update_settings
from app.api.endpoints.user_settings import test_ai as run_ai_test
from app.schemas.user_settings import SettingsUpdate


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id
        self.api_key = None


async def test_update_settings_rejects_bad_ai_provider(db, user_id):
    body = SettingsUpdate(settings={"ai_provider": "gemini"})
    with pytest.raises(HTTPException) as exc_info:
        await update_settings(body, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 400


async def test_update_settings_rejects_bad_ai_enabled(db, user_id):
    body = SettingsUpdate(settings={"ai_enabled": "yes"})
    with pytest.raises(HTTPException) as exc_info:
        await update_settings(body, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 400


async def test_update_settings_rejects_non_http_ai_base_url(db, user_id):
    body = SettingsUpdate(settings={"ai_base_url": "not-a-url"})
    with pytest.raises(HTTPException) as exc_info:
        await update_settings(body, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 400


async def test_update_settings_rejects_non_http_ai_endpoint(db, user_id):
    body = SettingsUpdate(settings={"ai_endpoint": "ftp://agent.example.com"})
    with pytest.raises(HTTPException) as exc_info:
        await update_settings(body, user=FakeUser(user_id), db=db)
    assert exc_info.value.status_code == 400


async def test_update_settings_accepts_valid_ai_settings(db, user_id):
    body = SettingsUpdate(settings={
        "ai_provider": "openai", "ai_enabled": "1",
        "ai_base_url": "http://localhost:11434/v1",
    })
    result = await update_settings(body, user=FakeUser(user_id), db=db)
    assert result["status"] == "ok"
    assert set(result["updated"]) == {"ai_provider", "ai_enabled", "ai_base_url"}


async def test_ai_test_endpoint_unconfigured_user_returns_ok_false(db, user_id):
    response = await run_ai_test(user=FakeUser(user_id), db=db)

    assert response["ok"] is False
    assert response["error"]
    assert response["results"] == []
    assert response["latency_ms"] == 0
