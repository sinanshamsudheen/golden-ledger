from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, expression
from ..database import Base

if TYPE_CHECKING:
    from .user import User
    from .deal import Deal


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # Unique per user — two users can reference the same Drive file_id (e.g. shared public drives)
    file_id: Mapped[str] = mapped_column(String, nullable=False)
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
    # External vectorizer pipeline doc ID (assigned by Invitus AI Insights after ingestion)
    vectorizer_doc_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="documents")
    deal: Mapped[Optional["Deal"]] = relationship("Deal", back_populates="documents")

    __table_args__ = (
        # (user_id, file_id) — unique per user; two users may reference the same shared Drive file
        Index("ix_documents_user_file_id", "user_id", "file_id", unique=True),
        # user_id alone — prerequisite for every user-scoped query
        Index("ix_documents_user_id", "user_id"),
        # (user_id, status) — all_documents / get_latest_documents_per_type
        Index("ix_documents_user_status", "user_id", "status"),
        # (user_id, checksum) partial — bulk dedup check in get_unprocessed_files
        Index(
            "ix_documents_user_checksum",
            "user_id", "checksum",
            postgresql_where=expression.text("checksum IS NOT NULL"),
        ),
        # (deal_id, doc_type) partial — deal-scoped GROUP BY in get_latest_documents_per_type
        Index(
            "ix_documents_deal_type",
            "deal_id", "doc_type",
            postgresql_where=expression.text("deal_id IS NOT NULL"),
        ),
        # (user_id, folder_path, doc_type) — dealless GROUP BY + Pass B superseded filter
        Index("ix_documents_user_folder_type", "user_id", "folder_path", "doc_type"),
        # (user_id, doc_type, version_status) — _mark_superseded_versions WHERE version_status='current'
        Index("ix_documents_user_type_version", "user_id", "doc_type", "version_status"),
    )
