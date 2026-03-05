from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    folder_id: Mapped[str | None] = mapped_column(String, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
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
