import io
import logging
import re
from typing import List, Dict, Any, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from ..config import settings

logger = logging.getLogger(__name__)

SUPPORTED_MIME_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
]


def _get_credentials(refresh_token: str) -> Credentials:
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials


def build_drive_service(refresh_token: str):
    """Build and return an authenticated Google Drive API v3 client."""
    credentials = _get_credentials(refresh_token)
    return build("drive", "v3", credentials=credentials)


def extract_folder_id_from_url(value: str) -> Optional[str]:
    """Extract a folder ID from a Google Drive URL (…/folders/<id>), or None if not a URL."""
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    return match.group(1) if match else None


def resolve_folder_id(service, folder_path: str) -> Optional[str]:
    """
    Resolve a folder path (e.g. '/InvestmentDocs/StartupA/') to a Drive folder ID.
    Traverses each path segment from the Drive root.

    Returns the folder ID, or None if any segment is not found.
    """
    parts = [p for p in folder_path.strip("/").split("/") if p]
    if not parts:
        return "root"

    parent_id = "root"
    for part in parts:
        escaped = part.replace("'", "\\'")
        query = (
            f"'{parent_id}' in parents"
            f" and name = '{escaped}'"
            f" and mimeType = 'application/vnd.google-apps.folder'"
            f" and trashed = false"
        )
        result = service.files().list(q=query, fields="files(id, name)").execute()
        files = result.get("files", [])
        if not files:
            logger.warning(f"Drive folder segment '{part}' not found under '{parent_id}'")
            return None
        parent_id = files[0]["id"]

    return parent_id


def list_files_in_folder(service, folder_id: str) -> List[Dict[str, Any]]:
    """
    List all supported document files inside a Drive folder (non-recursive).
    Handles Drive API pagination automatically.
    """
    mime_filter = " or ".join(f"mimeType = '{m}'" for m in SUPPORTED_MIME_TYPES)
    query = f"'{folder_id}' in parents and trashed = false and ({mime_filter})"

    files: List[Dict[str, Any]] = []
    page_token: Optional[str] = None

    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, createdTime, size, md5Checksum)",
                pageToken=page_token,
            )
            .execute()
        )
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return files


def list_files_recursive(
    service,
    folder_id: str,
    _path_parts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Recursively list all supported document files in a Drive folder and all its subfolders.
    Returns a flat list of file metadata dicts, each augmented with a ``folder_path`` key
    containing the slash-joined ancestor folder names relative to the configured root
    (e.g. ``"Portfolio/Acme Corp/Q1 2025"``).
    """
    path_parts: List[str] = _path_parts or []
    all_files: List[Dict[str, Any]] = []

    # Files in this folder — stamp each with the current path
    for f in list_files_in_folder(service, folder_id):
        f["folder_path"] = "/".join(path_parts)
        all_files.append(f)

    # Recurse into subfolders, extending the path
    subfolder_query = (
        f"'{folder_id}' in parents"
        " and mimeType = 'application/vnd.google-apps.folder'"
        " and trashed = false"
    )
    page_token: Optional[str] = None
    while True:
        response = (
            service.files()
            .list(
                q=subfolder_query,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            )
            .execute()
        )
        for subfolder in response.get("files", []):
            child_path = path_parts + [subfolder["name"]]
            all_files.extend(list_files_recursive(service, subfolder["id"], child_path))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    logger.info(f"Found {len(all_files)} file(s) total under folder '{folder_id}'")
    return all_files


def download_file(service, file_id: str) -> bytes:
    """Download a file from Google Drive and return its raw bytes."""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()
