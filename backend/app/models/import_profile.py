import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ImportProfile(Base):
    """A saved, reusable column mapping for the generic CSV importer.

    Lets a user teach FinPilot an unknown CSV export once (date/amount/
    description columns, date format, decimal separator, ...) and reuse it
    for future imports without any code change. See services/mapped_import.py
    and POST /api/import/csv/{preview,mapped}.
    """
    __tablename__ = "import_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("accounts.id"), nullable=True)
    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
