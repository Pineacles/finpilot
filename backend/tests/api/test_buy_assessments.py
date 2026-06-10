"""Model-level round-trip tests for BuyAssessment.time_stop.

Uses the shared in-memory SQLite fixture (see conftest.py) — no running Postgres
or HTTP server required. The repo has no FastAPI test-client infrastructure, so
model-level is the right layer here.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models.stock import BuyAssessment
from app.models.user import User


async def _seed_user(db, user_id: str) -> None:
    db.add(User(
        id=user_id,
        email=f"{user_id}@t.test",
        password_hash="x",
        api_key=f"apikey-{user_id}",
        display_name="t",
    ))
    await db.commit()


@pytest.mark.asyncio
async def test_time_stop_persists_and_round_trips(db, user_id):
    """Create a BuyAssessment with time_stop set, commit, re-query, assert round-trip."""
    await _seed_user(db, user_id)

    stop_date = date(2026, 5, 29)
    ba = BuyAssessment(
        user_id=user_id,
        symbol="AAPL",
        recommendation="buy",
        thesis="Strong fundamentals",
        conviction=4,
        time_stop=stop_date,
        assessed_at=datetime.now(timezone.utc),
    )
    db.add(ba)
    await db.commit()
    await db.refresh(ba)
    ba_id = ba.id

    # Re-query to confirm persistence (not just in-memory state)
    result = await db.execute(select(BuyAssessment).where(BuyAssessment.id == ba_id))
    fetched = result.scalar_one()

    assert fetched.time_stop == stop_date
    assert fetched.time_stop.isoformat() == "2026-05-29"


@pytest.mark.asyncio
async def test_time_stop_nullable_by_default(db, user_id):
    """BuyAssessment without time_stop should have None — existing rows unaffected."""
    await _seed_user(db, user_id)

    ba = BuyAssessment(
        user_id=user_id,
        symbol="MSFT",
        recommendation="watch",
        thesis="Waiting for dip",
        conviction=2,
        assessed_at=datetime.now(timezone.utc),
    )
    db.add(ba)
    await db.commit()
    await db.refresh(ba)

    result = await db.execute(select(BuyAssessment).where(BuyAssessment.id == ba.id))
    fetched = result.scalar_one()

    assert fetched.time_stop is None


@pytest.mark.asyncio
async def test_time_stop_can_be_updated(db, user_id):
    """time_stop can be set on an existing row (PATCH semantics)."""
    await _seed_user(db, user_id)

    ba = BuyAssessment(
        user_id=user_id,
        symbol="NVDA",
        recommendation="buy",
        thesis="AI tailwind",
        conviction=5,
        assessed_at=datetime.now(timezone.utc),
    )
    db.add(ba)
    await db.commit()
    await db.refresh(ba)

    assert ba.time_stop is None

    new_stop = date(2026, 6, 15)
    ba.time_stop = new_stop
    await db.commit()
    await db.refresh(ba)

    result = await db.execute(select(BuyAssessment).where(BuyAssessment.id == ba.id))
    fetched = result.scalar_one()

    assert fetched.time_stop == new_stop
    assert fetched.time_stop.isoformat() == "2026-06-15"
