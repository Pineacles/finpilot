"""User settings service: legacy-key migration for the ai_api_key rename
(previously anthropic_api_key), and the new provider-agnostic AI keys.

Follows the conventions in test_categorize.py / test_csv_import.py: real ORM
rows via the db fixture, no network calls.
"""
from __future__ import annotations

from app.services.settings import get_setting, get_all_settings, set_setting


async def test_ai_api_key_reads_value_stored_under_legacy_anthropic_api_key(db, user_id):
    """A value written under the old key name before this rename must still
    be readable under the new name, with no explicit migration step."""
    await set_setting(db, user_id, "anthropic_api_key", "sk-ant-legacy-value")

    value = await get_setting(db, user_id, "ai_api_key")

    assert value == "sk-ant-legacy-value"


async def test_get_all_settings_migrates_legacy_anthropic_api_key_to_ai_api_key(db, user_id):
    await set_setting(db, user_id, "anthropic_api_key", "sk-ant-legacy-value")

    settings = await get_all_settings(db, user_id)

    # anthropic_api_key is deprecated: folded into ai_api_key, not enumerated on its own.
    assert "anthropic_api_key" not in settings
    assert "ai_api_key" in settings
    # Sensitive value: masked, not the raw legacy value.
    assert settings["ai_api_key"] != ""
    assert settings["ai_api_key"] != "sk-ant-legacy-value"


async def test_ai_api_key_prefers_value_stored_under_new_key(db, user_id):
    await set_setting(db, user_id, "anthropic_api_key", "sk-ant-old")
    await set_setting(db, user_id, "ai_api_key", "sk-ant-new")

    value = await get_setting(db, user_id, "ai_api_key")

    assert value == "sk-ant-new"


async def test_new_ai_settings_default_to_empty_string(db, user_id):
    settings = await get_all_settings(db, user_id)

    assert settings["ai_enabled"] == ""
    assert settings["ai_provider"] == ""
    assert settings["ai_base_url"] == ""
