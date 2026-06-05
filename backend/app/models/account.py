import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # brokerage|credit_card|bank
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CHF")
    balance: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)  # User-set balance anchor
    balance_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)  # Date the balance was set
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="accounts")
