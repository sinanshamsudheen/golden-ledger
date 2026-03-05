from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base

if TYPE_CHECKING:
    from .user import User
    from .document import Document


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("user_id", "name_key", name="uq_deals_user_name_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Display name (title-cased, first seen)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Normalized lookup key: lowercase, alphanumeric only, no suffixes
    name_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # ── Analytical pipeline results ───────────────────────────────────────────
    # Investment classification: Fund | Direct | Co-Investment
    investment_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Investment committee outcome: accepted | rejected
    deal_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # 1-2 sentence reason from the Analytical endpoint
    deal_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # External pipeline job ID (Invitus AI Insights) — for debugging
    vectorizer_job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="deals")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="deal")