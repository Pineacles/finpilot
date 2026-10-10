"""Client-IP resolution, SSRF guard and settings encryption."""
import pytest
from cryptography.fernet import Fernet
from starlette.requests import Request

from app.core import crypto
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.services import settings as settings_svc
from app.services.url_guard import UnsafeURLError, assert_public_http_url


def _req(peer: str, headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


def test_client_ip_trusts_cf_header_from_internal_peer():
    assert get_client_ip(_req("172.18.0.5", {"CF-Connecting-IP": "1.1.1.1"})) == "1.1.1.1"


def test_client_ip_ignores_headers_from_public_peer():
    assert get_client_ip(_req("8.8.4.4", {"CF-Connecting-IP": "1.1.1.1"})) == "8.8.4.4"


def test_client_ip_xff_skips_internal_hops_and_spoofed_left():
    xff = "9.9.9.9, 1.1.1.1, 10.0.0.2"
    assert get_client_ip(_req("127.0.0.1", {"X-Forwarded-For": xff})) == "1.1.1.1"


def test_client_ip_falls_back_to_peer():
    assert get_client_ip(_req("172.18.0.5")) == "172.18.0.5"
    assert get_client_ip(_req("172.18.0.5", {"CF-Connecting-IP": "garbage"})) == "172.18.0.5"


async def test_url_guard_blocks_private_and_metadata():
    for url in ("http://127.0.0.1:8000/x", "http://169.254.169.254/latest", "http://10.1.2.3/", "ftp://example.com/"):
        with pytest.raises(UnsafeURLError):
            await assert_public_http_url(url, field="t")


async def test_url_guard_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "ALLOWED_PRIVATE_HOSTS", "localhost, ollama")
    await assert_public_http_url("http://localhost:11434/v1", field="t")
    with pytest.raises(UnsafeURLError):
        await assert_public_http_url("http://127.0.0.1:11434/v1", field="t")


async def test_sensitive_settings_encrypted_at_rest(db, user_id, monkeypatch):
    from sqlalchemy import select
    from app.models.settings import UserSetting

    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    await settings_svc.set_setting(db, user_id, "gmail_app_password", "abcd efgh ijkl mnop")
    await settings_svc.set_setting(db, user_id, "gmail_address", "me@example.com")
    raw = {r.key: r.value for r in (await db.execute(select(UserSetting))).scalars()}
    assert raw["gmail_app_password"].startswith(crypto.PREFIX)
    assert "abcd" not in raw["gmail_app_password"]
    assert raw["gmail_address"] == "me@example.com"
    assert await settings_svc.get_setting(db, user_id, "gmail_app_password") == "abcd efgh ijkl mnop"

    # legacy plaintext row still reads back
    row = (await db.execute(select(UserSetting).where(UserSetting.key == "gmail_app_password"))).scalar_one()
    row.value = "plain-legacy"
    await db.commit()
    assert await settings_svc.get_setting(db, user_id, "gmail_app_password") == "plain-legacy"


async def test_no_key_means_plaintext(db, user_id, monkeypatch):
    from sqlalchemy import select
    from app.models.settings import UserSetting

    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", "")
    await settings_svc.set_setting(db, user_id, "saxo_access_token", "tok123")
    row = (await db.execute(select(UserSetting))).scalar_one()
    assert row.value == "tok123"
