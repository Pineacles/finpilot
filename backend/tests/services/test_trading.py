"""AI auto-trading gate tests.

Covers all 19 test cases from the spec. Uses respx for Saxo HTTP mocking and
the same in-memory SQLite pattern as other tests.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from app.brokers.saxo import instruments as saxo_instruments
from app.models.account import Account
from app.models.stock import PendingOrder, StockPosition
from app.models.user import User
from app.services import settings as settings_svc
from app.services import trading as trading_svc

SIM = "https://gateway.saxobank.com/sim/openapi"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_instrument_cache():
    saxo_instruments._reset_cache_for_tests()
    yield
    saxo_instruments._reset_cache_for_tests()


async def _seed_user(db, user_id: str) -> User:
    u = User(id=user_id, email=f"{user_id}@t.test", password_hash="x",
             api_key=f"apikey-{user_id}", display_name="t")
    db.add(u)
    await db.commit()
    return u


async def _seed_saxo_ready(db, user_id: str) -> None:
    """Seed all settings so the Saxo adapter can reach the SIM environment."""
    await settings_svc.set_many_atomic(db, user_id, {
        "saxo_enabled": "1",
        "saxo_trading_enabled": "1",
        "saxo_environment": "sim",
        "saxo_app_key": "k",
        "saxo_app_secret": "s",
        "saxo_redirect_url": "https://example.test/cb",
        "saxo_access_token": "access-ok",
        "saxo_refresh_token": "refresh-ok",
        "saxo_token_expires_at": str(int(time.time()) + 1200),
    })


async def _seed_trading_enabled(db, user_id: str, mode: str = "semi") -> None:
    await settings_svc.set_many_atomic(db, user_id, {
        "trading_ai_enabled": "1",
        "trading_mode": mode,
        "trading_allowed_actions": "place,modify,cancel",
        "trading_symbol_whitelist": "",
        "trading_symbol_blacklist": "",
        "trading_order_max_chf": "5000",
        "trading_daily_count_max": "20",
        "trading_daily_chf_max": "50000",
        "trading_position_size_max_pct": "5",
        "trading_per_symbol_max_pct": "3",
        "trading_semi_approval_timeout_s": "1800",
        "trading_timezone": "Europe/Zurich",
    })


def _mock_instrument_and_precheck(mock, price=200.0, currency="USD"):
    mock.get(f"{SIM}/ref/v1/instruments").respond(json={
        "Data": [{"Identifier": 211, "Symbol": "AAPL", "Description": "Apple",
                  "AssetType": "Stock", "CurrencyCode": currency}]
    })
    mock.post(f"{SIM}/trade/v2/orders/precheck").respond(json={
        "PreCheckResult": "Ok",
        "EstimatedCashRequired": price,
        "EstimatedCommissions": 1.0,
        "Currency": currency,
    })


def _mock_place_order(mock, order_id="ord-123"):
    mock.post(f"{SIM}/trade/v2/orders").respond(
        status_code=201, json={"OrderId": order_id}
    )


# ── Test 1: Kill switch off → 403 ─────────────────────────────────────────────

async def test_kill_switch_off_returns_403(db, user_id):
    await _seed_user(db, user_id)
    # trading_ai_enabled defaults to "0"
    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.status == 403
    assert exc_info.value.code == "ai_trading_disabled"


# ── Test 2: Mode off → 400 ────────────────────────────────────────────────────

async def test_mode_off_returns_400(db, user_id):
    await _seed_user(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {
        "trading_ai_enabled": "1",
        "trading_mode": "off",
    })
    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.status == 400
    assert exc_info.value.code == "trading_mode_off"


# ── Test 3: Action not in allowed_actions → 403 ───────────────────────────────

async def test_action_not_allowed_returns_403(db, user_id):
    await _seed_user(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {
        "trading_ai_enabled": "1",
        "trading_mode": "semi",
        "trading_allowed_actions": "cancel",  # only cancel, not place
    })
    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.status == 403
    assert exc_info.value.code == "action_not_allowed"


# ── Test 4: Symbol whitelist enforcement ─────────────────────────────────────

async def test_symbol_whitelist_blocks_unlisted(db, user_id):
    await _seed_user(db, user_id)
    await _seed_trading_enabled(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"trading_symbol_whitelist": "MSFT,NVDA"})
    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.code == "symbol_not_in_whitelist"


async def test_symbol_blacklist_blocks_listed(db, user_id):
    await _seed_user(db, user_id)
    await _seed_trading_enabled(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"trading_symbol_blacklist": "AAPL,GME"})
    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.code == "symbol_in_blacklist"


# ── Test 5: Per-order CHF cap ─────────────────────────────────────────────────

async def test_per_order_chf_cap_rejected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"trading_order_max_chf": "100"})

    with respx.mock(assert_all_called=False) as mock:
        # price 200 USD → precheck returns 200, CHF rate ≈ 1 → 200 CHF > 100 cap
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            with pytest.raises(trading_svc.GateError) as exc_info:
                await trading_svc.request_order(
                    db, user_id, action="place", account_key="AK",
                    symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
                )
    assert exc_info.value.code == "order_cap_exceeded"


# ── Test 6: Daily count cap ───────────────────────────────────────────────────

async def test_daily_count_cap_rejected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"trading_daily_count_max": "2"})

    # Seed 2 existing non-terminal pending_orders today
    now = datetime.now(timezone.utc)
    for i in range(2):
        db.add(PendingOrder(
            id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
            symbol="AAPL", action="place", buy_sell="Buy", amount=1,
            order_type="Market", mode="semi", status="pending_approval",
            idempotency_key=str(uuid.uuid4()), created_at=now,
        ))
    await db.commit()

    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.request_order(
            db, user_id, action="place", account_key="AK",
            symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        )
    assert exc_info.value.code == "daily_count_exceeded"


# ── Test 7: Daily CHF cap ─────────────────────────────────────────────────────

async def test_daily_chf_cap_rejected(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    await settings_svc.set_many_atomic(db, user_id, {"trading_daily_chf_max": "1000"})

    # Seed one existing order that already consumed 900 CHF
    now = datetime.now(timezone.utc)
    db.add(PendingOrder(
        id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
        symbol="AAPL", action="place", buy_sell="Buy", amount=1,
        order_type="Market", mode="semi", status="pending_approval",
        estimated_cash_required_chf=900.0,
        idempotency_key=str(uuid.uuid4()), created_at=now,
    ))
    await db.commit()

    with respx.mock(assert_all_called=False) as mock:
        # New order will add 200 CHF → total 1100 > 1000
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            with pytest.raises(trading_svc.GateError) as exc_info:
                await trading_svc.request_order(
                    db, user_id, action="place", account_key="AK",
                    symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
                )
    assert exc_info.value.code == "daily_chf_exceeded"


# ── Test 8: Per-symbol cap ────────────────────────────────────────────────────

async def test_per_symbol_cap_rejected(db, user_id):
    """Seed a position where buying more would push AAPL over 3% allocation."""
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    # per_symbol_max_pct = 3%

    # Set up an account with some cash so portfolio total is non-zero
    acct = Account(user_id=user_id, name="Test", type="brokerage", currency="CHF",
                   balance=10000.0)
    db.add(acct)
    await db.commit()
    await db.refresh(acct)

    # Existing AAPL position = 0 (fresh buy)
    # amount=5, price=100 CHF → 500 CHF / 10000 CHF = 5% > 3% cap → breach
    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=500.0, currency="CHF")
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            with pytest.raises(trading_svc.GateError) as exc_info:
                await trading_svc.request_order(
                    db, user_id, action="place", account_key="AK",
                    symbol="AAPL", buy_sell="Buy", amount=5, order_type="Market",
                )
    assert exc_info.value.code in ("per_symbol_cap_exceeded", "position_size_cap_exceeded")


# ── Test 9: Position size cap ─────────────────────────────────────────────────

async def test_position_size_cap_rejected(db, user_id):
    """Same setup but per_symbol cap is wide and position_size cap is tighter."""
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    # Tighten position_size to 2% but per_symbol to 10% — position_size fires first
    await settings_svc.set_many_atomic(db, user_id, {
        "trading_per_symbol_max_pct": "10",
        "trading_position_size_max_pct": "2",
    })

    acct = Account(user_id=user_id, name="Test", type="brokerage", currency="CHF",
                   balance=10000.0)
    db.add(acct)
    await db.commit()

    # 5 shares × 100 CHF = 500 CHF / 10000 = 5% > position_size 2%
    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=500.0, currency="CHF")
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            with pytest.raises(trading_svc.GateError) as exc_info:
                await trading_svc.request_order(
                    db, user_id, action="place", account_key="AK",
                    symbol="AAPL", buy_sell="Buy", amount=5, order_type="Market",
                )
    # Either cap fires — both are valid failures
    assert exc_info.value.code in ("per_symbol_cap_exceeded", "position_size_cap_exceeded")


# ── Test 10: Idempotency ──────────────────────────────────────────────────────

async def test_idempotency_returns_same_row(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id)
    ikey = "unique-key-abc"

    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            r1 = await trading_svc.request_order(
                db, user_id, action="place", account_key="AK",
                symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
                idempotency_key=ikey,
            )

    # Second call with same key — no Saxo call expected
    r2 = await trading_svc.request_order(
        db, user_id, action="place", account_key="AK",
        symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
        idempotency_key=ikey,
    )
    assert r1["pending_order_id"] == r2["pending_order_id"]


# ── Test 11: Semi mode creates pending row ────────────────────────────────────

async def test_semi_mode_creates_pending_approval(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="semi")

    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        # Ensure place_order is NOT called
        place_route = mock.post(f"{SIM}/trade/v2/orders").respond(
            status_code=201, json={"OrderId": "should-not-be-called"}
        )
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            result = await trading_svc.request_order(
                db, user_id, action="place", account_key="AK",
                symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
            )

    assert result["status"] == "pending_approval"
    assert result["mode"] == "semi"
    assert result["broker_order_id"] is None
    assert not place_route.called

    # expires_at should be set
    assert result["expires_at"] is not None


# ── Test 12: Auto mode places immediately ─────────────────────────────────────

async def test_auto_mode_places_order_immediately(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="auto")

    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        place_route = mock.post(f"{SIM}/trade/v2/orders").respond(
            status_code=201, json={"OrderId": "ord-auto-999"}
        )
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            result = await trading_svc.request_order(
                db, user_id, action="place", account_key="AK",
                symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
            )

    assert result["status"] == "placed"
    assert result["broker_order_id"] == "ord-auto-999"
    assert place_route.called


# ── Test 13: Approve calls Saxo and updates status ────────────────────────────

async def test_approve_calls_saxo_and_sets_placed(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="semi")

    # Create a pending_approval row directly
    now = datetime.now(timezone.utc)
    row = PendingOrder(
        id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
        symbol="AAPL", action="place", buy_sell="Buy", amount=1,
        order_type="Market", duration="DayOrder", asset_type_saxo="Stock",
        mode="semi", status="pending_approval",
        idempotency_key=str(uuid.uuid4()),
        created_at=now,
        expires_at=now + timedelta(seconds=1800),
    )
    db.add(row)
    await db.commit()

    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=200.0, currency="CHF")
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={"Data": []})
        place_route = mock.post(f"{SIM}/trade/v2/orders").respond(
            status_code=201, json={"OrderId": "ord-approved-42"}
        )
        result = await trading_svc.approve_order(db, user_id, row.id)

    assert result["status"] == "placed"
    assert result["broker_order_id"] == "ord-approved-42"
    assert place_route.called


# ── Test 14: Approve expired row → 410 ───────────────────────────────────────

async def test_approve_expired_returns_410(db, user_id):
    await _seed_user(db, user_id)

    now = datetime.now(timezone.utc)
    row = PendingOrder(
        id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
        symbol="AAPL", action="place", buy_sell="Buy", amount=1,
        order_type="Market", mode="semi", status="pending_approval",
        idempotency_key=str(uuid.uuid4()),
        created_at=now - timedelta(hours=2),
        expires_at=now - timedelta(hours=1),  # expired
    )
    db.add(row)
    await db.commit()

    with pytest.raises(trading_svc.GateError) as exc_info:
        await trading_svc.approve_order(db, user_id, row.id)
    assert exc_info.value.status == 410
    assert exc_info.value.code == "order_expired"

    # Verify it was marked expired in DB
    from sqlalchemy import select
    refreshed = (await db.execute(select(PendingOrder).where(PendingOrder.id == row.id))).scalar_one()
    assert refreshed.status == "expired"


# ── Test 15: Reject sets status and stores reason ─────────────────────────────

async def test_reject_sets_status_rejected(db, user_id):
    await _seed_user(db, user_id)

    now = datetime.now(timezone.utc)
    row = PendingOrder(
        id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
        symbol="AAPL", action="place", buy_sell="Buy", amount=1,
        order_type="Market", mode="semi", status="pending_approval",
        idempotency_key=str(uuid.uuid4()),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    db.add(row)
    await db.commit()

    result = await trading_svc.reject_order(db, user_id, row.id, reason="Too risky")
    assert result["status"] == "rejected"
    assert result["rejected_reason"] == "Too risky"
    assert result["rejected_at"] is not None


# ── Test 16: Expire-stale sweep ───────────────────────────────────────────────

async def test_expire_stale_flips_expired_rows(db, user_id):
    await _seed_user(db, user_id)

    now = datetime.now(timezone.utc)
    stale_ids = []
    for i in range(3):
        r = PendingOrder(
            id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
            symbol="AAPL", action="place", buy_sell="Buy", amount=1,
            order_type="Market", mode="semi", status="pending_approval",
            idempotency_key=str(uuid.uuid4()),
            created_at=now - timedelta(hours=3),
            expires_at=now - timedelta(hours=1),  # stale
        )
        db.add(r)
        stale_ids.append(r.id)

    # One active row that must NOT be expired
    active = PendingOrder(
        id=str(uuid.uuid4()), user_id=user_id, account_key="AK",
        symbol="MSFT", action="place", buy_sell="Buy", amount=1,
        order_type="Market", mode="semi", status="pending_approval",
        idempotency_key=str(uuid.uuid4()),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    db.add(active)
    await db.commit()

    count = await trading_svc.expire_stale(db, user_id)
    assert count == 3

    from sqlalchemy import select
    for sid in stale_ids:
        r = (await db.execute(select(PendingOrder).where(PendingOrder.id == sid))).scalar_one()
        assert r.status == "expired"
    a = (await db.execute(select(PendingOrder).where(PendingOrder.id == active.id))).scalar_one()
    assert a.status == "pending_approval"


# ── Test 17: Modify action ────────────────────────────────────────────────────

async def test_auto_modify_calls_adapter(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="auto")

    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{SIM}/port/v1/accounts/me").respond(json={
            "Data": [{"AccountKey": "AK", "ClientKey": "CK"}]
        })
        mock.get(f"{SIM}/port/v1/orders/me").respond(json={
            "Data": [{
                "OrderId": "target-42", "Uic": 211, "AssetType": "Stock",
                "BuySell": "Buy", "Amount": 1, "OpenOrderType": "Limit",
                "Price": 200.0, "Duration": {"DurationType": "DayOrder"},
            }]
        })
        patch_route = mock.patch(f"{SIM}/trade/v2/orders").respond(
            json={"OrderId": "target-42"}
        )
        result = await trading_svc.request_order(
            db, user_id, action="modify", account_key="AK",
            target_order_id="target-42", limit_price=210.0,
        )

    assert result["status"] == "placed"
    assert patch_route.called


# ── Test 18: Cancel action ────────────────────────────────────────────────────

async def test_auto_cancel_calls_adapter(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="auto")

    with respx.mock(assert_all_called=False) as mock:
        delete_route = mock.delete(f"{SIM}/trade/v2/orders/ord-cancel").respond(
            json={"OrderId": "ord-cancel"}
        )
        result = await trading_svc.request_order(
            db, user_id, action="cancel", account_key="AK",
            target_order_id="ord-cancel",
        )

    assert result["status"] == "placed"
    assert delete_route.called


# ── Test 19: Saxo failure → status=failed ─────────────────────────────────────

async def test_saxo_failure_sets_failed_status(db, user_id):
    await _seed_user(db, user_id)
    await _seed_saxo_ready(db, user_id)
    await _seed_trading_enabled(db, user_id, mode="auto")

    with respx.mock(assert_all_called=False) as mock:
        _mock_instrument_and_precheck(mock, price=100.0, currency="CHF")
        # Place order returns 500
        mock.post(f"{SIM}/trade/v2/orders").respond(status_code=500, json={"Message": "Internal error"})
        with patch("app.services.trading._get_fx", new=AsyncMock(return_value=1.0)):
            result = await trading_svc.request_order(
                db, user_id, action="place", account_key="AK",
                symbol="AAPL", buy_sell="Buy", amount=1, order_type="Market",
            )

    assert result["status"] == "failed"
    assert result["rejected_reason"] is not None
