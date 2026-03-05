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
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

# Allow `from app.*` imports when the worker is run from server/ or project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.orm import Session

from app.services.drive_service import (
    build_drive_service,
    list_files_recursive,
    download_file,
)
from app.services.document_service import get_document_by_file_id, get_document_by_checksum
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
        all_files = list_files_recursive(service, user.folder_id)

        # Strip the root folder name from every folder_path so it's never
        # mistaken for a deal name. E.g. "TestDrive/Acme/Q1" → "Acme/Q1"
        root_meta = service.files().get(fileId=user.folder_id, fields="name").execute()
        root_name = root_meta.get("name", "")
        if root_name:
            prefix = root_name + "/"
            for f in all_files:
                fp = f.get("folder_path", "")
                if fp == root_name:
                    f["folder_path"] = ""
                elif fp.startswith(prefix):
                    f["folder_path"] = fp[len(prefix):]
    except Exception as exc:
        logger.error(f"Drive API error for user {user.id}: {exc}")
        return []

    new_files: List[Dict[str, Any]] = []
    for file_meta in all_files:
        # Skip if already processed by Drive file ID
        if get_document_by_file_id(db, file_meta["id"]) is not None:
            logger.debug(
                f"Skipping already-processed file '{file_meta['name']}' ({file_meta['id']})"
            )
            continue

        # Skip if identical content already processed (re-upload with new file ID)
        drive_checksum = file_meta.get("md5Checksum")
        if drive_checksum and get_document_by_checksum(db, user.id, drive_checksum) is not None:
            logger.info(
                f"Skipping duplicate content '{file_meta['name']}' — checksum {drive_checksum} already processed"
            )
            continue

        new_files.append(file_meta)

    logger.info(
        f"User {user.id}: {len(new_files)} new file(s) out of {len(all_files)} total"
    )
    return new_files


_RETRY_DELAYS = [2, 5, 10]  # seconds between attempts (3 attempts total)


def fetch_file_content(user: User, file_id: str) -> Optional[bytes]:
    """
    Download a file from Google Drive with exponential backoff retry.

    Retries up to 3 times on failure (handles Drive API rate limits).
    Returns raw bytes, or None if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            service = build_drive_service(user.refresh_token)
            content = download_file(service, file_id)
            if attempt > 1:
                logger.info(f"Downloaded file {file_id} on attempt {attempt}")
            else:
                logger.info(f"Downloaded file {file_id} ({len(content):,} bytes)")
            return content
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Download attempt {attempt}/4 failed for {file_id}: {exc}")

    logger.error(f"All download attempts failed for {file_id}: {last_exc}")
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
