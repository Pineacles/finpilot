"""Response/request schemas for user settings (app.api.endpoints.user_settings)."""
from pydantic import BaseModel


class SettingsGroup(BaseModel):
    label: str
    keys: list[str]


class SettingsGetResponse(BaseModel):
    api_key: str
    settings: dict[str, str]
    groups: dict[str, SettingsGroup]


class SettingsUpdate(BaseModel):
    settings: dict[str, str]


class SettingsUpdateResponse(BaseModel):
    status: str
    updated: list[str]


class ApiKeyRegenerateResponse(BaseModel):
    api_key: str
    message: str
