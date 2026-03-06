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


def _resolve(current_user: User, folder_path: str) -> tuple[str, str]:
    """Resolve a user-supplied path/URL to (folder_id, label). Raises HTTPException on failure."""
    if not current_user.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google Drive is not connected. Please complete OAuth first.",
        )

    folder_id = extract_folder_id_from_url(folder_path)
    label = folder_id or folder_path.strip()

    if not folder_id:
        try:
            service = build_drive_service(current_user.plaintext_refresh_token)
            folder_id = resolve_folder_id(service, folder_path)
            # If input was a path, keep it as the label so the UI can display it
            label = folder_path.strip()
        except Exception as exc:
            logger.error(f"Drive API error for user {current_user.id}: {exc}")
            raise HTTPException(status_code=503, detail="Google Drive API request failed")

    if not folder_id:
        raise HTTPException(
            status_code=404,
            detail=f"Folder '{folder_path}' was not found in your Google Drive",
        )

    return folder_id, label


@router.post("/folder")
@limiter.limit("30/minute")
def add_folder(
    request: Request,
    body: FolderConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Resolve a Drive folder path/URL and add it to the user's folder list.
    Duplicate folder IDs are silently ignored.
    """
    folder_id, label = _resolve(current_user, body.folder_path)

    folders: list[dict] = list(current_user.folder_ids or [])

    # Deduplicate by folder_id
    if any(f["id"] == folder_id for f in folders):
        return {"folder_id": folder_id, "label": label, "folders": folders}

    folders.append({"id": folder_id, "label": label})
    current_user.folder_ids = folders
    # Keep legacy folder_id pointing to the first entry
    current_user.folder_id = folders[0]["id"]
    db.commit()

    return {"folder_id": folder_id, "label": label, "folders": folders}


@router.delete("/folder/{folder_id}")
@limiter.limit("30/minute")
def remove_folder(
    request: Request,
    folder_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a folder from the user's folder list by its Drive folder ID."""
    folders: list[dict] = [f for f in (current_user.folder_ids or []) if f["id"] != folder_id]
    current_user.folder_ids = folders or None
    current_user.folder_id = folders[0]["id"] if folders else None
    db.commit()

    return {"folders": folders}
