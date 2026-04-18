"""Tools page aggregation endpoints — JWT auth, user-facing.

Mounted at /api/dashboard/tools.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.core.database import get_db
from app.models.signal import SignalHistory, ToolWeight, ToolWeightProposal
from app.models.user import User

router = APIRouter(prefix="/api/dashboard/tools", tags=["tools"])


@router.get("/leaderboard")
async def tools_leaderboard(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """IC leaderboard: correlation of signal_score vs alpha_5d over 30d and 60d windows."""
    now = datetime.now(timezone.utc)
    cutoff_60d = now - timedelta(days=60)

    # Fetch all signals with alpha data over last 60d
    result = await db.execute(
        select(SignalHistory).where(
            and_(
                SignalHistory.user_id == user.id,
                SignalHistory.run_timestamp >= cutoff_60d,
                SignalHistory.signal_score.isnot(None),
                SignalHistory.alpha_5d.isnot(None),
            )
        )
    )
    rows = result.scalars().all()

    # Fetch all tool weights
    tw_result = await db.execute(
        select(ToolWeight).where(ToolWeight.user_id == user.id)
    )
    weights_map = {tw.tool_name: tw for tw in tw_result.scalars().all()}

    # Group by tool
    from collections import defaultdict
    tool_data: dict[str, list] = defaultdict(list)
    for r in rows:
        tool_data[r.tool_name].append(r)

    cutoff_30d = now - timedelta(days=30)
    leaderboard = []
    for tool_name, signals in tool_data.items():
        def ic_for_window(sigs):
            scores = np.array([s.signal_score for s in sigs], dtype=float)
            alphas = np.array([s.alpha_5d for s in sigs], dtype=float)
            if len(scores) < 2:
                return None
            if np.std(scores) == 0 or np.std(alphas) == 0:
                return None
            return float(np.corrcoef(scores, alphas)[0, 1])

        sigs_30d = [s for s in signals if s.run_timestamp >= cutoff_30d]
        ic_30d = ic_for_window(sigs_30d)
        ic_60d = ic_for_window(signals)

        tw = weights_map.get(tool_name)
        leaderboard.append({
            "tool_name": tool_name,
            "ic_30d": ic_30d,
            "ic_60d": ic_60d,
            "weight": tw.weight if tw else None,
            "locked": tw.locked if tw else False,
            "last_weight_change": tw.last_updated_at.isoformat() if tw else None,
            "observation_count": len(signals),
        })

    leaderboard.sort(key=lambda x: (x["ic_30d"] or -99), reverse=True)
    return leaderboard


@router.get("/drill-down/{tool_name}")
async def tool_drill_down(
    tool_name: str,
    window_days: int = 60,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Drill down for a single tool: recent signals + rolling 30d IC time series."""
    now = datetime.now(timezone.utc)

    # Recent 50 signals
    recent_result = await db.execute(
        select(SignalHistory).where(
            and_(SignalHistory.user_id == user.id, SignalHistory.tool_name == tool_name)
        )
        .order_by(desc(SignalHistory.run_timestamp))
        .limit(50)
    )
    recent = recent_result.scalars().all()

    # All signals for rolling IC over last 180d
    cutoff = now - timedelta(days=180)
    all_result = await db.execute(
        select(SignalHistory).where(
            and_(
                SignalHistory.user_id == user.id,
                SignalHistory.tool_name == tool_name,
                SignalHistory.run_timestamp >= cutoff,
                SignalHistory.signal_score.isnot(None),
                SignalHistory.alpha_5d.isnot(None),
            )
        ).order_by(SignalHistory.run_timestamp)
    )
    all_sigs = all_result.scalars().all()

    # Rolling 30d IC weekly
    ic_series = []
    if all_sigs:
        start_ts = all_sigs[0].run_timestamp
        end_ts = now
        week = timedelta(days=7)
        window = timedelta(days=30)
        current = start_ts + window
        while current <= end_ts + week:
            window_sigs = [s for s in all_sigs if current - window <= s.run_timestamp <= current]
            if len(window_sigs) >= 2:
                scores = np.array([s.signal_score for s in window_sigs], dtype=float)
                alphas = np.array([s.alpha_5d for s in window_sigs], dtype=float)
                if np.std(scores) > 0 and np.std(alphas) > 0:
                    ic = float(np.corrcoef(scores, alphas)[0, 1])
                    ic_series.append({"date": current.isoformat(), "ic": ic, "n": len(window_sigs)})
            current += week

    return {
        "tool_name": tool_name,
        "recent_signals": [
            {
                "id": r.id,
                "run_id": r.run_id,
                "symbol": r.symbol,
                "signal_score": r.signal_score,
                "regime": r.regime,
                "run_timestamp": r.run_timestamp.isoformat(),
                "forward_return_1d": r.forward_return_1d,
                "forward_return_5d": r.forward_return_5d,
                "forward_return_20d": r.forward_return_20d,
                "alpha_5d": r.alpha_5d,
            }
            for r in recent
        ],
        "ic_time_series": ic_series,
    }


@router.get("/regime-breakdown/{tool_name}")
async def tool_regime_breakdown(
    tool_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """IC per regime for the given tool."""
    result = await db.execute(
        select(SignalHistory).where(
            and_(
                SignalHistory.user_id == user.id,
                SignalHistory.tool_name == tool_name,
                SignalHistory.signal_score.isnot(None),
                SignalHistory.alpha_5d.isnot(None),
                SignalHistory.regime.isnot(None),
            )
        )
    )
    rows = result.scalars().all()

    from collections import defaultdict
    by_regime: dict[str, list] = defaultdict(list)
    for r in rows:
        by_regime[r.regime].append(r)

    breakdown = {}
    for regime, sigs in by_regime.items():
        scores = np.array([s.signal_score for s in sigs], dtype=float)
        alphas = np.array([s.alpha_5d for s in sigs], dtype=float)
        if len(scores) >= 2 and np.std(scores) > 0 and np.std(alphas) > 0:
            ic = float(np.corrcoef(scores, alphas)[0, 1])
        else:
            ic = None
        breakdown[regime] = {"ic": ic, "n": len(sigs)}

    return breakdown


@router.get("/correlation-matrix")
async def tools_correlation_matrix(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pairwise signal_score correlation between all tools over 60d."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    result = await db.execute(
        select(SignalHistory).where(
            and_(
                SignalHistory.user_id == user.id,
                SignalHistory.run_timestamp >= cutoff,
                SignalHistory.signal_score.isnot(None),
            )
        ).order_by(SignalHistory.run_timestamp)
    )
    rows = result.scalars().all()

    # Group by run_id → tool → avg signal_score
    from collections import defaultdict
    run_tool_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        run_tool_scores[r.run_id][r.tool_name].append(r.signal_score)

    tools = sorted(set(r.tool_name for r in rows))
    if len(tools) < 2:
        return {"tools": tools, "matrix": []}

    # Build matrix: each run is one observation, use mean signal_score per tool per run
    run_ids = list(run_tool_scores.keys())
    data = np.full((len(run_ids), len(tools)), np.nan)
    for i, run_id in enumerate(run_ids):
        for j, tool in enumerate(tools):
            scores = run_tool_scores[run_id].get(tool)
            if scores:
                data[i, j] = float(np.mean(scores))

    # Compute pairwise correlation ignoring NaN pairs
    n = len(tools)
    matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i, j] = 1.0
            else:
                mask = ~(np.isnan(data[:, i]) | np.isnan(data[:, j]))
                if mask.sum() >= 2:
                    col_i = data[mask, i]
                    col_j = data[mask, j]
                    if np.std(col_i) > 0 and np.std(col_j) > 0:
                        matrix[i, j] = float(np.corrcoef(col_i, col_j)[0, 1])

    return {"tools": tools, "matrix": matrix.tolist()}


@router.get("/pending-proposals")
async def get_pending_proposals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return pending (unresolved) tool weight proposals for the UI."""
    # Auto-expire stale proposals older than 14 days
    expire_cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    stale_result = await db.execute(
        select(ToolWeightProposal).where(
            and_(
                ToolWeightProposal.user_id == user.id,
                ToolWeightProposal.resolved_at == None,  # noqa: E711
                ToolWeightProposal.proposed_at < expire_cutoff,
            )
        )
    )
    stale_proposals = stale_result.scalars().all()
    if stale_proposals:
        now_utc = datetime.now(timezone.utc)
        for sp in stale_proposals:
            sp.resolution = "expired"
            sp.resolved_by = "system"
            sp.resolved_at = now_utc
        await db.commit()

    result = await db.execute(
        select(ToolWeightProposal).where(
            and_(
                ToolWeightProposal.user_id == user.id,
                ToolWeightProposal.resolved_at == None,  # noqa: E711
            )
        ).order_by(desc(ToolWeightProposal.proposed_at))
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "tool_name": r.tool_name,
            "current_weight": r.current_weight,
            "proposed_weight": r.proposed_weight,
            "rationale": r.rationale,
            "review_type": r.review_type,
            "review_window_start": r.review_window_start.isoformat(),
            "review_window_end": r.review_window_end.isoformat(),
            "ic_30d": r.ic_30d,
            "ic_60d": r.ic_60d,
            "observations_count": r.observations_count,
            "proposed_by": r.proposed_by,
            "proposed_at": r.proposed_at.isoformat(),
        }
        for r in rows
    ]


class DashboardProposalResolve(BaseModel):
    resolution: str  # approved|rejected
    resolved_by: str


@router.patch("/proposals/{proposal_id}")
async def resolve_proposal_dashboard(
    proposal_id: str,
    body: DashboardProposalResolve,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a proposal from the dashboard UI. Auto-applies weight on approval."""
    result = await db.execute(
        select(ToolWeightProposal).where(
            and_(ToolWeightProposal.id == proposal_id, ToolWeightProposal.user_id == user.id)
        )
    )
    proposal = result.scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.resolved_at is not None:
        raise HTTPException(status_code=400, detail="Proposal already resolved")

    if body.resolution not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="resolution must be approved|rejected")

    now_utc = datetime.now(timezone.utc)
    proposal.resolved_at = now_utc
    proposal.resolution = body.resolution
    proposal.resolved_by = body.resolved_by

    if body.resolution == "approved":
        tw_result = await db.execute(
            select(ToolWeight).where(
                and_(ToolWeight.tool_name == proposal.tool_name, ToolWeight.user_id == user.id)
            )
        )
        tw = tw_result.scalar_one_or_none()
        if tw is None:
            tw = ToolWeight(
                tool_name=proposal.tool_name,
                weight=proposal.proposed_weight,
                user_id=user.id,
                last_updated_by=body.resolved_by,
            )
            db.add(tw)
        else:
            tw.weight = proposal.proposed_weight
            tw.last_updated_by = body.resolved_by
            tw.last_updated_at = now_utc

    await db.commit()
    return {
        "id": proposal.id,
        "resolution": proposal.resolution,
        "resolved_by": proposal.resolved_by,
        "resolved_at": proposal.resolved_at.isoformat(),
        "tool_name": proposal.tool_name,
        "applied_weight": proposal.proposed_weight if body.resolution == "approved" else None,
    }
