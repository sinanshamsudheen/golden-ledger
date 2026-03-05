import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models.user import User
from ..services.drive_service import build_drive_service, resolve_folder_id, extract_folder_id_from_url
from ..utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drive", tags=["drive"])
limiter = Limiter(key_func=get_remote_address)


class FolderConfigRequest(BaseModel):
    folder_path: str


@router.post("/folder")
@limiter.limit("30/minute")
def configure_folder(
    request: Request,
    body: FolderConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Resolve a Drive folder path to its folder ID and persist it for the user.

    Body:
        folder_path: A path string such as "/InvestmentDocs/StartupA/"

    Returns the resolved folder_id.
    """
    if not current_user.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google Drive is not connected. Please complete OAuth first.",
        )

    folder_id = extract_folder_id_from_url(body.folder_path)
    if not folder_id:
        try:
            service = build_drive_service(current_user.plaintext_refresh_token)
            folder_id = resolve_folder_id(service, body.folder_path)
        except Exception as exc:
            logger.error(f"Drive API error for user {current_user.id}: {exc}")
            raise HTTPException(status_code=503, detail="Google Drive API request failed")

    if not folder_id:
        raise HTTPException(
            status_code=404,
            detail=f"Folder '{body.folder_path}' was not found in your Google Drive",
        )

    current_user.folder_id = folder_id
    db.commit()

    return {"folder_id": folder_id, "folder_path": body.folder_path}
