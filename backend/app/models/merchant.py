import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Boolean, ForeignKey, ARRAY, Float, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Merchant(Base):
    """Known merchant with matching patterns and default category."""
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    patterns: Mapped[str] = mapped_column(Text, nullable=False, default="")  # pipe-separated lowercase patterns
    default_category_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("categories.id"), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CategorizationLog(Base):
    """Tracks how each transaction was categorized — for learning."""
    __tablename__ = "categorization_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # merchant_db|user_rule|history|ai|manual
    category_id: Mapped[str] = mapped_column(String(36), ForeignKey("categories.id"), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
