"""Live-SIM integration test. Skipped unless SAXO_SIM_TEST_TOKEN is set.

Generate a 24h token from the Saxo developer portal ("Generate a 24-hour
access token") and export it:

    export SAXO_SIM_TEST_TOKEN="..."
    pytest backend/tests/brokers/test_saxo_sim.py
"""
from __future__ import annotations

import os
import time

import pytest

from app.services import settings as settings_svc

SIM_TOKEN = os.environ.get("SAXO_SIM_TEST_TOKEN")
pytestmark = pytest.mark.skipif(not SIM_TOKEN, reason="SAXO_SIM_TEST_TOKEN not set")


@pytest.fixture
def saxo_adapter():
    from app.brokers.saxo.adapter import SaxoAdapter
    return SaxoAdapter()


async def test_sim_diagnostics_and_accounts(db, user_id, saxo_adapter):
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "manual",
        "saxo_app_secret": "manual",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": SIM_TOKEN,
        "saxo_refresh_token": "",
        "saxo_token_expires_at": str(int(time.time()) + 23 * 3600),
    })

    assert await saxo_adapter.health_check(db, user_id) is True

    accounts = await saxo_adapter.get_accounts(db, user_id)
    assert len(accounts) >= 1
    first = accounts[0]
    assert first.external_id
    assert first.currency

    balance = await saxo_adapter.get_balances(db, user_id, first.external_id)
    assert balance.account_external_id == first.external_id
    assert balance.currency

    positions = await saxo_adapter.get_positions(db, user_id, first.external_id)
    # Positions may legitimately be empty on a fresh SIM account.
    assert isinstance(positions, list)
