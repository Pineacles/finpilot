"""Gmail sender authentication, log hygiene, API key hashing, uploads,
XML hardening, ticker validation and extended settings encryption."""
import email
import io
import logging

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.core import crypto
from app.core.config import settings
from app.core.security import API_KEY_HASH_PREFIX, generate_api_key, hash_api_key
from app.core.uploads import read_upload
from app.models.settings import UserSetting
from app.models.user import User
from app.services import settings as settings_svc
from app.services.camt053 import parse_camt053
from app.services.gmail_poller import has_passing_dkim, sender_filter_is_safe, sender_matches
from app.services.prices import get_history, get_quote, is_valid_ticker


def _msg(from_hdr: str, auth_results: list[str]):
    lines = [f"Authentication-Results: {a}" for a in auth_results]
    raw = "\n".join(lines + [f"From: {from_hdr}", "Subject: x", "", "body"])
    return email.message_from_string(raw)


# ---- Gmail DKIM -----------------------------------------------------------

def test_dkim_pass_for_sender_domain():
    m = _msg("Valiant <noreply@valiant.ch>",
             ["mx.google.com; dkim=pass header.i=@valiant.ch header.s=sel header.b=abc; spf=pass smtp.mailfrom=valiant.ch"])
    assert has_passing_dkim(m)


def test_dkim_fail_or_missing_rejected():
    assert not has_passing_dkim(_msg("a@valiant.ch", ["mx.google.com; dkim=fail header.i=@valiant.ch; spf=pass"]))
    assert not has_passing_dkim(_msg("a@valiant.ch", ["mx.google.com; spf=pass smtp.mailfrom=valiant.ch"]))
    assert not has_passing_dkim(_msg("a@valiant.ch", []))


def test_dkim_pass_for_other_domain_rejected():
    m = _msg("noreply@valiant.ch", ["mx.google.com; dkim=pass header.i=@evil.example header.s=s"])
    assert not has_passing_dkim(m)


def test_dkim_untrusted_authserv_rejected():
    m = _msg("noreply@valiant.ch", ["evil.example; dkim=pass header.i=@valiant.ch"])
    assert not has_passing_dkim(m)


def test_forged_header_below_gmail_header_is_ignored():
    m = _msg("noreply@valiant.ch", [
        "mx.google.com; dkim=fail header.i=@valiant.ch",
        "mx.google.com; dkim=pass header.i=@valiant.ch",
    ])
    assert not has_passing_dkim(m)


def test_sender_must_match_configured_filter():
    assert sender_matches(_msg("N <noreply@valiant.ch>", []), ["noreply@valiant.ch"])
    assert not sender_matches(_msg("noreply@valiant.ch.evil.example", []), ["noreply@valiant.ch"])
    assert sender_matches(_msg("x@valiant.ch", []), ["valiant.ch"])
    assert not sender_matches(_msg("x@notvaliant.ch", []), ["valiant.ch"])


# ---- IMAP filter injection --------------------------------------------------

@pytest.mark.parametrize("bad", ['a@b.ch" OR ALL', "a@b.ch\r\nA1 DELETE INBOX", "a\\b", "a\x00b", ""])
def test_sender_filter_rejects_dangerous_values(bad):
    assert not sender_filter_is_safe(bad)


def test_sender_filter_accepts_normal_values():
    assert sender_filter_is_safe("noreply@valiant.ch")


async def test_poll_logs_no_amounts_and_skips_unverified(db, user_id, monkeypatch, caplog):
    from app.services import gmail_poller

    raw = (
        "From: noreply@valiant.ch\nAuthentication-Results: mx.google.com; spf=pass\n"
        "Date: Mon, 02 Nov 2026 10:00:00 +0000\n\n"
        "Belastung von CHF 30.02 auf dem Konto main. Neuer Saldo CHF 6'170.84."
    ).encode()

    class FakeIMAP:
        def __init__(self, *a, **k): pass
        def login(self, *a): pass
        def select(self, *a): pass
        def logout(self): pass
        def uid(self, cmd, _charset, *args):
            if cmd == "search":
                return "OK", [b"5"]
            return "OK", [(b"5", raw)]

    monkeypatch.setattr(gmail_poller.imaplib, "IMAP4_SSL", FakeIMAP)
    await settings_svc.set_setting(db, user_id, "gmail_address", "me@example.com")
    await settings_svc.set_setting(db, user_id, "gmail_app_password", "pw")
    from app.models.account import Account
    db.add(User(id=user_id, email="u@t.test", password_hash="x", api_key="k", display_name="U"))
    await db.commit()
    caplog.set_level(logging.DEBUG, logger="app")
    result = await gmail_poller.poll_gmail(db, user_id)
    assert result["new_transactions"] == 0
    app_log = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("app"))
    assert "skipped" in app_log
    assert "30.02" not in app_log and "6'170" not in app_log and "6170" not in app_log


async def test_poll_verified_mail_creates_txn_without_logging_amounts(db, user_id, monkeypatch, caplog):
    from app.services import gmail_poller

    raw = (
        "From: noreply@valiant.ch\n"
        "Authentication-Results: mx.google.com; dkim=pass header.i=@valiant.ch header.s=s\n"
        "Date: Mon, 02 Nov 2026 10:00:00 +0000\n\n"
        "Belastung von CHF 30.02 auf dem Konto main. Neuer Saldo CHF 6'170.84."
    ).encode()

    class FakeIMAP:
        def __init__(self, *a, **k): pass
        def login(self, *a): pass
        def select(self, *a): pass
        def logout(self): pass
        def uid(self, cmd, _charset, *args):
            if cmd == "search":
                return "OK", [b"5"]
            return "OK", [(b"5", raw)]

    monkeypatch.setattr(gmail_poller.imaplib, "IMAP4_SSL", FakeIMAP)
    await settings_svc.set_setting(db, user_id, "gmail_address", "me@example.com")
    await settings_svc.set_setting(db, user_id, "gmail_app_password", "pw")
    db.add(User(id=user_id, email="u@t.test", password_hash="x", api_key="k", display_name="U"))
    await db.commit()
    caplog.set_level(logging.DEBUG, logger="app")
    result = await gmail_poller.poll_gmail(db, user_id)
    assert result["new_transactions"] == 1
    app_log = "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("app"))
    assert app_log
    assert "30.02" not in app_log and "6'170" not in app_log and "6170" not in app_log


# ---- API key hashing ---------------------------------------------------------

def test_api_key_hash_is_stable_and_not_plaintext():
    k = generate_api_key()
    h = hash_api_key(k)
    assert h.startswith(API_KEY_HASH_PREFIX) and k not in h and h == hash_api_key(k)
    assert len(h) <= 128


async def test_api_key_lookup_uses_hash(db, user_id):
    from app.api.deps.auth import get_user_by_api_key

    key = generate_api_key()
    db.add(User(id=user_id, email="u@t.test", password_hash="x", api_key=hash_api_key(key), display_name="U"))
    await db.commit()
    assert (await get_user_by_api_key(x_api_key=key, db=db)).id == user_id
    with pytest.raises(HTTPException):
        await get_user_by_api_key(x_api_key=hash_api_key(key), db=db)  # the stored hash is not a credential
    with pytest.raises(HTTPException):
        await get_user_by_api_key(x_api_key="wrong", db=db)


async def test_regenerate_returns_key_once_and_stores_hash(db, user_id):
    from app.api.endpoints.user_settings import regenerate_api_key

    user = User(id=user_id, email="u@t.test", password_hash="x", api_key="old", display_name="U")
    db.add(user)
    await db.commit()
    out = await regenerate_api_key(user=user, db=db)
    assert user.api_key == hash_api_key(out["api_key"])
    assert out["api_key"] not in user.api_key


def test_migration_hashes_legacy_keys_in_place(monkeypatch):
    import importlib.util, pathlib, sqlalchemy as sa
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    path = pathlib.Path(__file__).parent.parent / "alembic/versions/c4d5e6f7a8b9_hash_agent_api_keys.py"
    spec = importlib.util.spec_from_file_location("mig_hash", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    monkeypatch.setattr(mig.op, "alter_column", lambda *a, **k: None)  # SQLite cannot ALTER TYPE
    eng = sa.create_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, api_key VARCHAR(64) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO users VALUES ('1', 'plain-key-1')"))
        conn.execute(sa.text(f"INSERT INTO users VALUES ('2', '{hash_api_key('k2')}')"))
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.upgrade()
            mig.upgrade()  # idempotent
        rows = dict(conn.execute(sa.text("SELECT id, api_key FROM users")).fetchall())
    assert rows["1"] == hash_api_key("plain-key-1")
    assert rows["2"] == hash_api_key("k2")


# ---- Settings encryption ------------------------------------------------------

@pytest.mark.parametrize("key", [
    "saxo_app_secret", "saxo_refresh_token", "ai_api_key", "ai_auth_header", "agent_auth_header",
])
async def test_more_settings_encrypted(db, user_id, monkeypatch, key):
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    await settings_svc.set_setting(db, user_id, key, "secret-value")
    row = (await db.execute(select(UserSetting).where(UserSetting.key == key))).scalar_one()
    assert row.value.startswith(crypto.PREFIX)
    assert await settings_svc.get_setting(db, user_id, key) == "secret-value"
    row.value = "legacy-plain"
    await db.commit()
    assert await settings_svc.get_setting(db, user_id, key) == "legacy-plain"


async def test_legacy_alias_value_decrypted(db, user_id, monkeypatch):
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    await settings_svc.set_setting(db, user_id, "anthropic_api_key", "sk-old")
    assert await settings_svc.get_setting(db, user_id, "ai_api_key") == "sk-old"


def test_startup_warns_without_encryption_key(monkeypatch, caplog):
    from app import main

    monkeypatch.setattr(settings, "SECRET_KEY", "x" * 40)
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", "")
    with caplog.at_level(logging.WARNING):
        main._validate_settings()
    assert "TOKEN_ENCRYPTION_KEY is empty" in caplog.text
    caplog.clear()
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    with caplog.at_level(logging.WARNING):
        main._validate_settings()
    assert "TOKEN_ENCRYPTION_KEY" not in caplog.text


# ---- Uploads and XML -----------------------------------------------------------

async def test_upload_over_limit_is_413():
    f = UploadFile(file=io.BytesIO(b"x" * 2048), filename="a.csv")
    with pytest.raises(HTTPException) as e:
        await read_upload(f, max_bytes=1024)
    assert e.value.status_code == 413
    assert await read_upload(UploadFile(file=io.BytesIO(b"abc"), filename="a.csv"), max_bytes=1024) == b"abc"


def test_camt053_rejects_entity_bomb():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<Document><BkToCstmrStmt><Stmt>&b;</Stmt></BkToCstmrStmt></Document>"
    )
    with pytest.raises(ValueError):
        parse_camt053(bomb)


def test_camt053_rejects_external_entity():
    xxe = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><Document>&x;</Document>'
    with pytest.raises(ValueError):
        parse_camt053(xxe)


# ---- Tickers --------------------------------------------------------------------

@pytest.mark.parametrize("t", ["AAPL", "BRK-B", "NESN.SW", "^GSPC", "CHFEUR=X", "BTC-USD"])
def test_valid_tickers(t):
    assert is_valid_ticker(t)


@pytest.mark.parametrize("t", ["", "../x", "A/B", "A?x=1", "A#", "A B", "A%2F", "x" * 40, "A\n"])
def test_invalid_tickers(t):
    assert not is_valid_ticker(t)


async def test_invalid_ticker_makes_no_request(monkeypatch):
    import httpx
    from app.services import prices

    def boom(*a, **k):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(httpx, "AsyncClient", boom)
    assert await get_quote("../../v7/finance") is None
    assert await get_history("a/b") == []
    assert prices is not None
