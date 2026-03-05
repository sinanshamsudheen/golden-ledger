from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base

if TYPE_CHECKING:
    from .user import User
    from .deal import Deal


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_created_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    drive_created_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Status values: pending | processed | vectorized | failed
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    # Deal association (FK replaces the plain deal_name string)
    deal_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("deals.id"), nullable=True, index=True
    )
    # Drive folder path for display/debugging (e.g. "Portfolio/Acme Corp/Q1 2025")
    folder_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Version tracking: current | superseded
    version_status: Mapped[str] = mapped_column(String, default="current", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="documents")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="documents")
