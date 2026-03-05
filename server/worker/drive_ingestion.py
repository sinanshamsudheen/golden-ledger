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
    build_drive_service_from_credentials,
    get_credentials,
    list_files_recursive,
    download_file,
)
from app.models.document import Document as _Doc
from app.models.user import User

logger = logging.getLogger(__name__)


def get_unprocessed_files(
    db: Session,
    user: User,
) -> List[Dict[str, Any]]:
    """
    Return Drive file metadata for files that are not yet in the database.

    Uses two bulk DB queries (all known file IDs + checksums for the user)
    instead of per-file lookups, reducing query count from O(N) to O(1).
    Passes shared credentials to list_files_recursive for parallel BFS.
    """
    if not user.refresh_token or not user.folder_id:
        logger.warning(
            f"User {user.id} ({user.email}) has no refresh_token or folder_id – skipping"
        )
        return []

    try:
        # Build credentials once — shared across all parallel folder-listing threads
        credentials = get_credentials(user.plaintext_refresh_token)
        service = build_drive_service_from_credentials(credentials)
        all_files = list_files_recursive(service, user.folder_id, credentials=credentials)

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

    # ── Batch DB lookup — 2 queries regardless of how many files exist ─────────
    known_ids: set[str] = {
        row[0]
        for row in db.query(_Doc.file_id).filter(_Doc.user_id == user.id).all()
    }
    known_checksums: set[str] = {
        row[0]
        for row in db.query(_Doc.checksum)
        .filter(_Doc.user_id == user.id, _Doc.checksum.isnot(None))
        .all()
    }

    new_files: List[Dict[str, Any]] = []
    for file_meta in all_files:
        if file_meta["id"] in known_ids:
            logger.debug(
                f"Skipping already-processed file '{file_meta['name']}' ({file_meta['id']})"
            )
            continue
        drive_checksum = file_meta.get("md5Checksum")
        if drive_checksum and drive_checksum in known_checksums:
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


def get_user_drive_credentials(user: User):
    """
    Build and return valid Drive credentials for a user.
    Call once per worker run and pass the result to fetch_file_content
    to avoid an OAuth token refresh for every single file download.
    """
    return get_credentials(user.plaintext_refresh_token)


def fetch_file_content(user: User, file_id: str, credentials=None) -> Optional[bytes]:
    """
    Download a file from Google Drive with exponential backoff retry.

    Pass ``credentials`` (from get_user_drive_credentials) to reuse an
    already-refreshed token instead of triggering a new OAuth refresh
    per file — critical when downloading hundreds of files in parallel.
    """
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            time.sleep(delay)
        try:
            if credentials is not None:
                service = build_drive_service_from_credentials(credentials)
            else:
                service = build_drive_service(user.plaintext_refresh_token)
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
