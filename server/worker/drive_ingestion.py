"""
Drive ingestion module.

Responsible for:
  - Building an authenticated Drive service for a user
  - Listing files in the configured folder
  - Identifying new / unprocessed files
  - Downloading file content
  - Computing an MD5 checksum for deduplication

Used by worker.py during the nightly processing run.
"""

import hashlib
import logging
import sys
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

# Allow `from app.*` imports when the worker is run from server/ or project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import Session

from app.services.drive_service import (
    build_drive_service,
    list_files_in_folder,
    download_file,
)
from app.services.document_service import get_document_by_file_id
from app.models.user import User

logger = logging.getLogger(__name__)


def get_unprocessed_files(
    db: Session,
    user: User,
) -> List[Dict[str, Any]]:
    """
    Return Drive file metadata for files that are not yet in the database.

    Args:
        db:   Active database session.
        user: User record with refresh_token and folder_id populated.

    Returns:
        List of Drive file metadata dicts for new files only.
    """
    if not user.refresh_token or not user.folder_id:
        logger.warning(
            f"User {user.id} ({user.email}) has no refresh_token or folder_id – skipping"
        )
        return []

    try:
        service = build_drive_service(user.refresh_token)
        all_files = list_files_in_folder(service, user.folder_id)
    except Exception as exc:
        logger.error(f"Drive API error for user {user.id}: {exc}")
        return []

    new_files: List[Dict[str, Any]] = []
    for file_meta in all_files:
        existing = get_document_by_file_id(db, file_meta["id"])
        if existing is None:
            new_files.append(file_meta)
        else:
            logger.debug(
                f"Skipping already-processed file '{file_meta['name']}' ({file_meta['id']})"
            )

    logger.info(
        f"User {user.id}: {len(new_files)} new file(s) out of {len(all_files)} total"
    )
    return new_files


def fetch_file_content(user: User, file_id: str) -> Optional[bytes]:
    """
    Download a file from Google Drive.

    Args:
        user:    User record with a valid refresh_token.
        file_id: Google Drive file ID.

    Returns:
        Raw bytes of the file, or None on failure.
    """
    try:
        service = build_drive_service(user.refresh_token)
        content = download_file(service, file_id)
        logger.info(f"Downloaded file {file_id} ({len(content):,} bytes)")
        return content
    except Exception as exc:
        logger.error(f"Failed to download file {file_id}: {exc}")
        return None


def compute_checksum(content: bytes) -> str:
    """Return the MD5 hex digest of the given bytes."""
    return hashlib.md5(content).hexdigest()


def parse_drive_created_time(drive_meta: Dict[str, Any]) -> Optional[datetime]:
    """Parse the 'createdTime' field from Drive file metadata into a datetime."""
    raw = drive_meta.get("createdTime")
    if not raw:
        return None
    try:
        # Drive returns ISO 8601 with trailing Z
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.warning(f"Could not parse createdTime '{raw}'")
        return None
