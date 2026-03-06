from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DocumentBase(BaseModel):
    file_id: str
    file_name: str
    doc_type: Optional[str] = None


class DocumentCreate(DocumentBase):
    user_id: int
    file_path: Optional[str] = None
    description: Optional[str] = None
    doc_created_date: Optional[datetime] = None
    drive_created_time: Optional[datetime] = None
    checksum: Optional[str] = None
    status: str = "pending"


class DocumentResponse(DocumentBase):
    id: int
    user_id: int
    file_path: Optional[str] = None
    description: Optional[str] = None
    doc_created_date: Optional[datetime] = None
    drive_created_time: Optional[datetime] = None
    checksum: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LatestDocumentResponse(BaseModel):
    """Response schema for the /documents/latest endpoint."""

    type: str
    name: str
    date: Optional[str] = None
    description: Optional[str] = None


class AllDocumentResponse(BaseModel):
    """Response schema for the /documents/all endpoint."""

    id: int
    file_id: str
    type: str
    name: str
    date: Optional[str] = None
    description: Optional[str] = None
    status: str
    deal_id: Optional[int] = None
    deal_name: Optional[str] = None
    version_status: str = "current"
    folder_path: Optional[str] = None


# ── Deal-level schemas ────────────────────────────────────────────────────────

class DealDocSlot(BaseModel):
    """A single document filling one of the 4 type slots in a deal."""

    id: int
    file_id: str
    name: str
    date: Optional[str] = None
    description: Optional[str] = None
    vectorizer_doc_id: Optional[str] = None


class DealDocSlots(BaseModel):
    """The 4 canonical document type slots for a deal. None = empty slot."""

    pitch_deck: Optional[DealDocSlot] = None
    investment_memo: Optional[DealDocSlot] = None
    prescreening_report: Optional[DealDocSlot] = None
    meeting_minutes: Optional[DealDocSlot] = None


class ArchivedDoc(BaseModel):
    """A superseded document shown in the deal archive."""

    id: int
    file_id: str
    type: str
    name: str
    date: Optional[str] = None


class LockedFileDoc(BaseModel):
    """A password-protected file that could not be parsed."""

    id: int
    file_id: str
    name: str
    date: Optional[str] = None


class LockedFileWithDeal(BaseModel):
    """A password-protected file enriched with the deal it belongs to."""

    id: int
    file_id: str
    name: str
    date: Optional[str] = None
    deal_id: Optional[int] = None
    deal_name: Optional[str] = None


class DealFieldResponse(BaseModel):
    """A single structured field extracted for a deal via the ExtractFields API."""

    field_name: str
    field_label: Optional[str] = None
    # Original CSV type hint: select | currency | range | text | geography
    field_type: Optional[str] = None
    # UI grouping: "Opportunity overview" | "Key terms"
    section: Optional[str] = None
    # Raw value as returned by the API (string, or null)
    value: Optional[str] = None
    # Human-readable formatted value (falls back to value if not provided)
    value_formatted: Optional[str] = None


class DocumentStatsResponse(BaseModel):
    """Aggregated document statistics for the dashboard."""
    total_validated: int
    shortlisted: int
    archived: int
    knowledge_base: int


class DealResponse(BaseModel):
    """Full deal with its current document slots, archive, and analytical results."""

    id: int
    name: str
    documents: DealDocSlots
    archived: list[ArchivedDoc] = []
    doc_count: int  # number of current (non-archived) documents
    # Populated by the Analytical endpoint after vectorization
    investment_type: Optional[str] = None   # Fund | Direct | Co-Investment
    deal_status: Optional[str] = None       # accepted | rejected
    deal_reason: Optional[str] = None       # IC rationale (3-4 sentences)
    # Structured fields extracted by ExtractFields API (type-specific)
    deal_fields: list[DealFieldResponse] = []
    # Password-protected files that couldn’t be processed
    locked_files: list[LockedFileDoc] = []
