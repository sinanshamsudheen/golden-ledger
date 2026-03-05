import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def get_credentials(refresh_token: str) -> Credentials:
    """Build and refresh Drive credentials once — reuse the result across downloads."""
    return _get_credentials(refresh_token)


def build_drive_service(refresh_token: str):
    """Build and return an authenticated Google Drive API v3 client."""
    credentials = _get_credentials(refresh_token)
    return build("drive", "v3", credentials=credentials)


def build_drive_service_from_credentials(credentials: Credentials):
    """Build a Drive service from already-refreshed credentials (no OAuth round-trip)."""
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


_FOLDER_WORKERS = 10  # parallel threads per BFS level


def list_files_recursive(
    service,
    folder_id: str,
    _path_parts: Optional[List[str]] = None,
    *,
    credentials: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    List all supported document files using parallel BFS.

    All sibling folders at each depth level are queried concurrently
    (up to _FOLDER_WORKERS threads), turning O(N_folders) sequential Drive
    API calls into O(depth) parallel rounds.  For 200 deal folders this
    reduces listing time from ~4 minutes to ~15 seconds.

    Pass ``credentials`` (from get_credentials) so each thread can build
    its own Drive service without re-issuing an OAuth token refresh.
    """
    def _build_svc():
        # googleapiclient service objects are NOT thread-safe — each thread
        # must own its own instance.  Re-use the already-refreshed credentials
        # so no new OAuth round-trip is needed.
        if credentials is not None:
            return build_drive_service_from_credentials(credentials)
        return service  # fallback for callers that don't pass credentials

    def _visit_folder(item: tuple) -> tuple:
        fid, path = item
        svc = _build_svc()

        # Files in this folder
        files = list_files_in_folder(svc, fid)
        for f in files:
            f["folder_path"] = "/".join(path)

        # Subfolders for the next BFS level
        subs: List[tuple] = []
        q = (
            f"'{fid}' in parents"
            " and mimeType = 'application/vnd.google-apps.folder'"
            " and trashed = false"
        )
        page_token: Optional[str] = None
        while True:
            resp = svc.files().list(
                q=q,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            ).execute()
            for sf in resp.get("files", []):
                subs.append((sf["id"], path + [sf["name"]]))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return files, subs

    all_files: List[Dict[str, Any]] = []
    current_level: List[tuple] = [(folder_id, list(_path_parts or []))]

    while current_level:
        next_level: List[tuple] = []
        workers = min(len(current_level), _FOLDER_WORKERS)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_visit_folder, item) for item in current_level]
            for future in as_completed(futures):
                try:
                    files, subs = future.result()
                    all_files.extend(files)
                    next_level.extend(subs)
                except Exception as exc:
                    logger.error(f"Folder listing error: {exc}", exc_info=True)
        current_level = next_level

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
