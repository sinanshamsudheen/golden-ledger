from datetime import datetime
from typing import Optional, TYPE_CHECKING, List
from sqlalchemy import String, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    folder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # List of {"id": "<drive_folder_id>", "label": "<original input>"} objects
    folder_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def drive_folders(self) -> List[dict]:
        """Return folder_ids list, falling back to legacy folder_id if needed."""
        if self.folder_ids:
            return self.folder_ids
        if self.folder_id:
            return [{"id": self.folder_id, "label": self.folder_id}]
        return []
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document", back_populates="user"
    )
    deals: Mapped[list["Deal"]] = relationship("Deal", back_populates="user")  # noqa: F821

    @property
    def plaintext_refresh_token(self) -> Optional[str]:
        """
        Return the decrypted Google OAuth refresh token.

        Falls back to the raw value during the one-time migration window
        when tokens were stored as plaintext (decrypt() handles this gracefully).
        """
        if self.refresh_token is None:
            return None
        from ..utils.encryption import decrypt
        return decrypt(self.refresh_token)
