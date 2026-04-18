import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Float, Boolean, Integer, ForeignKey, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SignalHistory(Base):
    __tablename__ = "signal_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    raw_output: Mapped[dict] = mapped_column(JSON, nullable=False)
    signal_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    regime_inputs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    run_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    forward_return_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_return_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alpha_1d: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha_5d: Mapped[float | None] = mapped_column(Float, nullable=True)
    alpha_20d: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_signal_history_tool_symbol", "tool_name", "symbol"),
    )


class ToolWeight(Base):
    __tablename__ = "tool_weights"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_updated_by: Mapped[str] = mapped_column(String(50), nullable=False, default="system_initial")
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)


class ToolWeightProposal(Base):
    __tablename__ = "tool_weight_proposals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    current_weight: Mapped[float] = mapped_column(Float, nullable=False)
    proposed_weight: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(String(2000), nullable=False)
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # weekly|monthly
    review_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ic_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    ic_60d: Mapped[float | None] = mapped_column(Float, nullable=True)
    observations_count: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_by: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)  # approved|rejected|expired
    resolved_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
