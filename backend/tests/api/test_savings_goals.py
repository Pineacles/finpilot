"""finance.py savings-goal endpoints: progress must be computed from real
total wealth (portfolio + cash + bank balance), not the manual
SavingsGoal.current_amount column, which the UI never updates and so stays
0 forever. Mirrors agent_portfolio_router.goals_progress's computation via
the shared app.services.portfolio_service.compute_total_wealth.

Endpoint handlers called directly (no HTTP transport), matching the pattern
in tests/api/test_agent_scoping.py.
"""
from __future__ import annotations

from datetime import date

from app.api.endpoints.finance import create_goal, list_goals, update_goal
from app.models.account import Account
from app.models.finance import SavingsGoal, Transaction
from app.schemas.finance import SavingsGoalCreate, SavingsGoalUpdate


class FakeUser:
    def __init__(self, user_id: str):
        self.id = user_id


async def _fund_bank_balance(db, user_id: str, amount: float) -> None:
    acct = Account(user_id=user_id, name="Bank", type="bank", currency="CHF")
    db.add(acct)
    await db.flush()
    db.add(Transaction(
        user_id=user_id, account_id=acct.id, date=date(2026, 1, 5),
        merchant="Employer", amount=amount, currency="CHF",
    ))
    await db.commit()


async def test_list_goals_computes_progress_from_total_wealth_not_manual_field(db, user_id):
    await _fund_bank_balance(db, user_id, 4000.0)

    goal = SavingsGoal(
        user_id=user_id, name="Emergency Fund",
        target_amount=10000.0, current_amount=0,  # never updated by the UI
    )
    db.add(goal)
    await db.commit()

    goals = await list_goals(user=FakeUser(user_id), db=db)

    assert len(goals) == 1
    assert goals[0].progress_pct == 40.0
    assert goals[0].current_amount == 4000.0


async def test_create_goal_returns_progress_from_existing_wealth(db, user_id):
    await _fund_bank_balance(db, user_id, 2500.0)

    body = SavingsGoalCreate(name="New Car", target_amount=5000.0)
    result = await create_goal(body, user=FakeUser(user_id), db=db)

    assert result.progress_pct == 50.0
    assert result.current_amount == 2500.0


async def test_update_goal_recomputes_progress_after_target_change(db, user_id):
    await _fund_bank_balance(db, user_id, 3000.0)

    goal = SavingsGoal(user_id=user_id, name="Vacation", target_amount=6000.0, current_amount=0)
    db.add(goal)
    await db.commit()
    await db.refresh(goal)

    result = await update_goal(goal.id, SavingsGoalUpdate(target_amount=3000.0), user=FakeUser(user_id), db=db)

    assert result.progress_pct == 100.0
    assert result.current_amount == 3000.0
