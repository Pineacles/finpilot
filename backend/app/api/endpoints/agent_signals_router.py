"""Agent sub-router — API key auth for AI assistant integration."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, and_, func, case, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_user_by_api_key
from app.core.config import settings
from app.core.database import get_db
from app.models.account import Account
from app.models.finance import Transaction, Budget, Category, RecurringExpense, SavingsGoal, Milestone
from app.models.merchant import Merchant
from app.models.signal import SignalHistory, ToolWeight, ToolWeightProposal
from app.models.stock import StockPosition, StockTransaction, PostMortem, BuyAssessment
from app.models.user import User
from app.schemas.finance import TransactionCreate, TransactionResponse

router = APIRouter(tags=["agent"])


# ── Signal Evaluation Layer ──────────────────────────────────────

class SignalItem(BaseModel):
    tool_name: str
    symbol: str | None = None
    raw_output: dict
    signal_score: float | None = None
    benchmark_ticker: str | None = None


class SignalBatchCreate(BaseModel):
    run_id: str
    run_timestamp: datetime
    regime: str | None = None
    regime_inputs: dict | None = None
    signals: list[SignalItem]


@router.post("/signal-history")
async def batch_insert_signals(
    body: SignalBatchCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Batch insert signal history rows from one analysis run."""
    normalized_regime = body.regime.lower().strip() if body.regime else None
    rows = []
    for s in body.signals:
        row = SignalHistory(
            run_id=body.run_id,
            tool_name=s.tool_name,
            symbol=s.symbol,
            raw_output=s.raw_output,
            signal_score=s.signal_score,
            regime=normalized_regime,
            regime_inputs=body.regime_inputs,
            user_id=user.id,
            run_timestamp=body.run_timestamp,
            benchmark_ticker=s.benchmark_ticker,
        )
        db.add(row)
        rows.append(row)
    await db.commit()
    return {"status": "ok", "run_id": body.run_id, "signals_logged": len(rows)}


@router.get("/signal-history")
async def get_signal_history(
    tool_name: str | None = None,
    symbol: str | None = None,
    regime: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    limit: int = 100,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve signal history with optional filters."""
    filters = [SignalHistory.user_id == user.id]
    if tool_name:
        filters.append(SignalHistory.tool_name == tool_name)
    if symbol:
        filters.append(SignalHistory.symbol == symbol)
    if regime:
        filters.append(SignalHistory.regime == regime)
    if from_date:
        filters.append(SignalHistory.run_timestamp >= from_date)
    if to_date:
        filters.append(SignalHistory.run_timestamp <= to_date)

    result = await db.execute(
        select(SignalHistory)
        .where(and_(*filters))
        .order_by(desc(SignalHistory.run_timestamp))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "tool_name": r.tool_name,
            "symbol": r.symbol,
            "signal_score": r.signal_score,
            "regime": r.regime,
            "regime_inputs": r.regime_inputs,
            "run_timestamp": r.run_timestamp.isoformat(),
            "benchmark_ticker": r.benchmark_ticker,
            "forward_return_1d": r.forward_return_1d,
            "forward_return_5d": r.forward_return_5d,
            "forward_return_20d": r.forward_return_20d,
            "alpha_1d": r.alpha_1d,
            "alpha_5d": r.alpha_5d,
            "alpha_20d": r.alpha_20d,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── Tool Weights ─────────────────────────────────────────────────

@router.get("/tool-weights")
async def get_tool_weights(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Return all current tool weights."""
    result = await db.execute(
        select(ToolWeight).where(ToolWeight.user_id == user.id)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "tool_name": r.tool_name,
            "weight": r.weight,
            "locked": r.locked,
            "last_updated_at": r.last_updated_at.isoformat(),
            "last_updated_by": r.last_updated_by,
        }
        for r in rows
    ]


class WeightUpdate(BaseModel):
    weight: float
    updated_by: str
    review_type: str = "weekly"  # weekly|monthly — used for guardrail window


@router.patch("/tool-weights/{tool_name}")
async def update_tool_weight(
    tool_name: str,
    body: WeightUpdate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Update a tool weight. The agent is subject to guardrails; a configured admin bypasses all."""
    result = await db.execute(
        select(ToolWeight).where(
            and_(ToolWeight.tool_name == tool_name, ToolWeight.user_id == user.id)
        )
    )
    tw = result.scalar_one_or_none()

    if tw is None:
        # Auto-create with weight=1.0 first
        tw = ToolWeight(tool_name=tool_name, weight=1.0, user_id=user.id, last_updated_by="system_initial")
        db.add(tw)
        await db.flush()

    admin = settings.GUARDRAIL_ADMIN_NAME
    is_admin = bool(admin) and body.updated_by == admin
    if not is_admin:
        if tw.locked:
            raise HTTPException(status_code=403, detail="Tool is locked — cannot update weight")

        current = tw.weight
        new_w = body.weight

        if body.review_type == "weekly":
            max_change_pct = 0.20
            min_obs = 40
        else:
            max_change_pct = 0.40
            min_obs = 80

        # Check max change
        if current != 0:
            change_pct = abs(new_w - current) / abs(current)
            # Monthly allows zeroing (cutting to 0)
            if not (body.review_type == "monthly" and new_w == 0.0):
                if change_pct > max_change_pct:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Weight change {change_pct:.1%} exceeds {max_change_pct:.0%} limit for {body.review_type} review"
                    )

        # Check observation count — last 30d for weekly, last 60d for monthly
        obs_window_days = 30 if body.review_type == "weekly" else 60
        obs_cutoff = datetime.now(timezone.utc) - timedelta(days=obs_window_days)
        obs_result = await db.execute(
            select(func.count(SignalHistory.id)).where(
                and_(
                    SignalHistory.tool_name == tool_name,
                    SignalHistory.user_id == user.id,
                    SignalHistory.run_timestamp >= obs_cutoff,
                )
            )
        )
        obs_count = obs_result.scalar() or 0
        if obs_count < min_obs:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient observations: {obs_count} < {min_obs} required for {body.review_type} review"
            )

    tw.weight = body.weight
    tw.last_updated_by = body.updated_by
    tw.last_updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"tool_name": tool_name, "weight": tw.weight, "updated_by": tw.last_updated_by}


@router.post("/tool-weights/{tool_name}/lock")
async def lock_tool_weight(
    tool_name: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Lock a tool weight against changes."""
    result = await db.execute(
        select(ToolWeight).where(and_(ToolWeight.tool_name == tool_name, ToolWeight.user_id == user.id))
    )
    tw = result.scalar_one_or_none()
    if tw is None:
        raise HTTPException(status_code=404, detail="Tool weight not found")
    tw.locked = True
    tw.last_updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"tool_name": tool_name, "locked": True}


@router.post("/tool-weights/{tool_name}/unlock")
async def unlock_tool_weight(
    tool_name: str,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Unlock a tool weight."""
    result = await db.execute(
        select(ToolWeight).where(and_(ToolWeight.tool_name == tool_name, ToolWeight.user_id == user.id))
    )
    tw = result.scalar_one_or_none()
    if tw is None:
        raise HTTPException(status_code=404, detail="Tool weight not found")
    tw.locked = False
    tw.last_updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"tool_name": tool_name, "locked": False}


# ── Tool Weight Proposals ────────────────────────────────────────

class ProposalCreate(BaseModel):
    tool_name: str
    current_weight: float
    proposed_weight: float
    rationale: str
    review_type: str
    review_window_start: datetime
    review_window_end: datetime
    ic_30d: float | None = None
    ic_60d: float | None = None
    observations_count: int


@router.post("/tool-weight-proposals")
async def create_proposal(
    body: ProposalCreate,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Create a tool weight proposal (submitted by the agent, reviewed by the user)."""
    proposal = ToolWeightProposal(
        tool_name=body.tool_name,
        current_weight=body.current_weight,
        proposed_weight=body.proposed_weight,
        rationale=body.rationale,
        review_type=body.review_type,
        review_window_start=body.review_window_start,
        review_window_end=body.review_window_end,
        ic_30d=body.ic_30d,
        ic_60d=body.ic_60d,
        observations_count=body.observations_count,
        proposed_by="agent",
        user_id=user.id,
    )
    db.add(proposal)
    await db.commit()
    return {"id": proposal.id, "status": "pending", "tool_name": proposal.tool_name}


@router.get("/tool-weight-proposals")
async def get_proposals(
    status: str | None = None,
    limit: int = 50,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve tool weight proposals. Lazily expires proposals older than 14 days."""
    # Auto-expire stale pending proposals before returning
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

    filters = [ToolWeightProposal.user_id == user.id]
    if status == "pending":
        filters.append(ToolWeightProposal.resolved_at == None)  # noqa: E711
    elif status in ("approved", "rejected", "expired"):
        filters.append(ToolWeightProposal.resolution == status)

    result = await db.execute(
        select(ToolWeightProposal)
        .where(and_(*filters))
        .order_by(desc(ToolWeightProposal.proposed_at))
        .limit(limit)
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
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolution": r.resolution,
            "resolved_by": r.resolved_by,
        }
        for r in rows
    ]


class ProposalResolve(BaseModel):
    resolution: str  # approved|rejected|expired
    resolved_by: str


@router.patch("/tool-weight-proposals/{proposal_id}")
async def resolve_proposal(
    proposal_id: str,
    body: ProposalResolve,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a proposal. If approved, auto-applies the weight change."""
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

    if body.resolution not in ("approved", "rejected", "expired"):
        raise HTTPException(status_code=400, detail="resolution must be approved|rejected|expired")

    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.resolution = body.resolution
    proposal.resolved_by = body.resolved_by

    if body.resolution == "approved":
        # Auto-apply the weight change
        tw_result = await db.execute(
            select(ToolWeight).where(
                and_(ToolWeight.tool_name == proposal.tool_name, ToolWeight.user_id == user.id)
            )
        )
        tw = tw_result.scalar_one_or_none()
        if tw is None:
            tw = ToolWeight(tool_name=proposal.tool_name, weight=proposal.proposed_weight, user_id=user.id, last_updated_by=body.resolved_by)
            db.add(tw)
        else:
            tw.weight = proposal.proposed_weight
            tw.last_updated_by = body.resolved_by
            tw.last_updated_at = datetime.now(timezone.utc)

    await db.commit()
    return {
        "id": proposal.id,
        "resolution": proposal.resolution,
        "resolved_by": proposal.resolved_by,
        "resolved_at": proposal.resolved_at.isoformat(),
    }


# ── Symbol classification (agent can reclassify to keep benchmark card honest) ──

class AgentClassifyRequest(BaseModel):
    asset_type: str  # equity|etf|index|crypto|bond|commodity|cash


@router.get("/classifications")
async def agent_list_classifications(
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    from app.models.stock import SymbolClassification
    result = await db.execute(
        select(SymbolClassification).where(SymbolClassification.user_id == user.id)
    )
    rows = result.scalars().all()
    return [
        {"symbol": r.symbol, "asset_type": r.asset_type, "source": r.source,
         "updated_at": r.updated_at.isoformat()}
        for r in rows
    ]


@router.post("/classifications/{symbol}")
async def agent_set_classification(
    symbol: str,
    body: AgentClassifyRequest,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Agent sets/overrides a symbol's asset_type. Used when the agent decides
    an ETF or index fund shouldn't count toward the individual-stock benchmark.
    """
    from app.services import classification as classification_svc
    try:
        row = await classification_svc.set_classification(
            db, user.id, symbol, body.asset_type, source="agent"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"symbol": row.symbol, "asset_type": row.asset_type, "source": row.source}


@router.get("/benchmark-comparison")
async def agent_benchmark_comparison(
    range: str = "1M",
    benchmark: str = "SPY",
    start: str | None = None,
    end: str | None = None,
    user: User = Depends(get_user_by_api_key),
    db: AsyncSession = Depends(get_db),
):
    """Read-only: TWR of individual stocks vs benchmark. Same shape as the user
    endpoint — useful for the agent to assess its own picks."""
    from app.services.benchmark import compute_benchmark_comparison
    try:
        result = await compute_benchmark_comparison(
            db, user.id,
            range_key=range, benchmark_symbol=benchmark,
            custom_start=start, custom_end=end,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result.__dict__
