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
