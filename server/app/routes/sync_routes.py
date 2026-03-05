import logging

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..models.document import Document
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/status")
@limiter.limit("60/minute")
def sync_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the current sync state and document counts for the user.

    Status values:
      not_connected  – Google Drive not linked
      no_folder      – Drive connected but no folder configured
      processing     – Documents are pending ingestion
      idle           – Everything is up to date
    """
    total = db.query(Document).filter(Document.user_id == current_user.id).count()

    processed = (
        db.query(Document)
        .filter(
            Document.user_id == current_user.id,
            Document.status.in_(["processed", "vectorized"]),
        )
        .count()
    )

    pending = (
        db.query(Document)
        .filter(Document.user_id == current_user.id, Document.status == "pending")
        .count()
    )

    drive_connected = current_user.refresh_token is not None
    folder_configured = current_user.folder_id is not None

    if not drive_connected:
        status = "not_connected"
    elif not folder_configured:
        status = "no_folder"
    elif pending > 0:
        status = "processing"
    else:
        status = "idle"

    return {
        "status": status,
        "next_sync": "02:00 AM",
        "drive_connected": drive_connected,
        "folder_configured": folder_configured,
        "total_documents": total,
        "processed_documents": processed,
        "pending_documents": pending,
    }
