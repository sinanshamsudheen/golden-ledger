import logging
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..services.document_service import get_latest_documents_per_type
from ..schemas.document_schema import LatestDocumentResponse
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/latest", response_model=List[LatestDocumentResponse])
def latest_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[LatestDocumentResponse]:
    """
    Return the latest processed document per document type for the current user.

    Example response:
    [
      {
        "type": "pitch_deck",
        "name": "Seed Deck Jan 2025",
        "date": "2025-01-12",
        "description": "Pitch deck outlining the seed investment opportunity."
      }
    ]
    """
    documents = get_latest_documents_per_type(db, current_user.id)

    return [
        LatestDocumentResponse(
            type=doc.doc_type or "other",
            name=doc.file_name,
            date=doc.doc_created_date.strftime("%Y-%m-%d") if doc.doc_created_date else None,
            description=doc.description,
        )
        for doc in documents
    ]
