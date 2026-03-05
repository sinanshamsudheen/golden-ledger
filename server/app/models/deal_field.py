from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..database import Base

if TYPE_CHECKING:
    from .deal import Deal


class DealField(Base):
    """
    One extracted structured field per deal (e.g. Fund Size, Target IRR).

    Rows are deleted and re-inserted every time the ExtractFields pipeline
    runs for a deal, so the set always reflects the latest documents.
    The set of fields present depends on deal.investment_type:
        Fund          → Fund-Fields definitions
        Direct        → Direct-Fields definitions
        Co-Investment → Co-Investment-Fields definitions
    """

    __tablename__ = "deal_fields"
    __table_args__ = (
        UniqueConstraint("deal_id", "field_name", name="uq_deal_fields_deal_field"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    deal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("deals.id"), nullable=False, index=True
    )

    # Identifier matching the CSV field_name (e.g. "prescreening_assetClass")
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    # Human-readable label (e.g. "Asset Class")
    field_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Original CSV type hint for UI rendering (select / currency / range / text / geography)
    field_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Grouping section in the UI (e.g. "Opportunity overview" / "Key terms")
    section: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Raw value as returned by ExtractFields (always stored as text)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Human-readable formatted value (may equal value for plain strings)
    value_formatted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    deal: Mapped["Deal"] = relationship("Deal", back_populates="fields")
