from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint
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

    user: Mapped["User"] = relationship("User", back_populates="deals")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="deal")
