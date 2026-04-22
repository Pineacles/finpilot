import uuid
from datetime import datetime, date, timezone

from sqlalchemy import String, DateTime, Date, Float, Integer, ForeignKey, JSON, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockPosition(Base):
    __tablename__ = "stock_positions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    earnings_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False)  # buy|sell|dividend
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    fees: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    total_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, nullable=False)
    total_pnl: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)


class PostMortem(Base):
    """Post-mortem record for closed losing positions — for learning from mistakes."""
    __tablename__ = "post_mortems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    analysis_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("market_analyses.id"), nullable=True)
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    exit_price: Mapped[float] = mapped_column(Float, nullable=False)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BuyAssessment(Base):
    """Forward-looking buy assessment — records what the agent recommends buying."""
    __tablename__ = "buy_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    recommendation: Mapped[str] = mapped_column(String(10), nullable=False)  # buy|hold|watch|avoid
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis: Mapped[str] = mapped_column(String(4000), nullable=False)
    risk_factors: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    conviction: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    time_horizon: Mapped[str | None] = mapped_column(String(10), nullable=True)  # short|medium|long
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MarketAnalysis(Base):
    __tablename__ = "market_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(20), nullable=False)  # macro|sector|position
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PendingOrder(Base):
    """AI-driven pending order — gate between AI agent and Saxo adapter.

    A row is created for every order request the AI submits. In 'semi' mode it
    waits for human approval; in 'auto' mode it is approved immediately and the
    adapter is called in the same request.
    """
    __tablename__ = "pending_orders"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_pending_orders_user_idempotency"),
        Index("ix_pending_orders_user_created", "user_id", "created_at"),
        Index("ix_pending_orders_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    account_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # place|modify|cancel
    target_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    buy_sell: Mapped[str | None] = mapped_column(String(4), nullable=True)  # Buy|Sell
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(20), nullable=True)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    asset_type_saxo: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Stock (Saxo naming)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)  # semi|auto
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    buy_assessment_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("buy_assessments.id"), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cash_required_chf: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_fees_chf: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    broker_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SymbolClassification(Base):
    """Per-user asset-type classification for a symbol.

    Used to cleanly separate individual-stock performance from index/ETF holdings
    when benchmarking against S&P 500. If no row exists for a (user, symbol),
    it defaults to 'equity' (classifier tries to upsert on first sighting).
    """
    __tablename__ = "symbol_classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False)  # equity|etf|index|crypto|bond|commodity|cash
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # auto|user|agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
