"""
Nightly document processing worker.

Pipeline (per user):
  1.  Fetch all users from the database
  2.  Skip users without Drive connected or folder configured
  3.  Identify new (unprocessed) files in the Drive folder
  4.  For each new file:
        a. Download content
        b. Extract text
        c. Classify document type
        d. Extract document date
        e. Generate a short description
        f. Persist metadata to the database
  5.  Determine the latest document per type
  6.  Send those documents to the vectorizer pipeline

Run manually (from project root):
    python server/worker/worker.py

Or from inside server/:
    python worker/worker.py

Scheduled via cron:
    0 2 * * * /path/to/venv/bin/python /path/to/server/worker/worker.py
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
# server/ is the package root; add it to sys.path so `from app.*` works whether
# the worker is run from project root or from within server/.
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SERVER_DIR)

# Load .env from server/.env (if present) before importing settings
from dotenv import load_dotenv  # type: ignore

_env_path = os.path.join(_SERVER_DIR, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)

# ── Internal imports ──────────────────────────────────────────────────────────
from app.database import SessionLocal
from app.models.user import User
from app.models.document import Document
from app.schemas.document_schema import DocumentCreate
from app.services.document_service import (
    get_document_by_file_id,
    create_document,
    update_document,
    get_latest_documents_per_type,
)

from worker.drive_ingestion import (
    get_unprocessed_files,
    fetch_file_content,
    compute_checksum,
    parse_drive_created_time,
)
from worker.parser import extract_text
from worker.classifier import classify_document
from worker.summarizer import generate_description

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
)
logger = logging.getLogger("worker")

# ── Date extraction ───────────────────────────────────────────────────────────
_DATE_PATTERNS = [
    r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b",  # DD/MM/YYYY or MM/DD/YYYY
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"[\s,]+(\d{1,2})[\s,]+(\d{4})\b",  # Month DD, YYYY
    r"\b(\d{4})[\/\-](\d{2})[\/\-](\d{2})\b",  # YYYY-MM-DD
]


def _extract_doc_date(text: str) -> Optional[datetime]:
    """
    Try to extract a document creation date from its text using regex patterns.
    Returns a datetime on success, otherwise None.
    """
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text[:2000], re.IGNORECASE)
        if match:
            try:
                return datetime(*[int(g) for g in match.groups() if g and g.isdigit()][:3])
            except (TypeError, ValueError):
                continue
    return None


# ── Vectorizer integration ────────────────────────────────────────────────────

def send_to_vectorizer(document: Document, text: str) -> None:
    """
    Placeholder: send a processed document to the external vectorizer pipeline.

    Replace this function body with your actual HTTP call / queue message
    when the vectorizer endpoint is available.

    Expected payload shape (per PRD §11):
        {
            "doc_id":   <int>,
            "text":     <str>,
            "metadata": {
                "doc_type": <str>,
                "company":  <str | None>,   # extracted from file_name heuristic
                "date":     <str | None>    # YYYY-MM-DD
            }
        }
    """
    date_str = (
        document.doc_created_date.strftime("%Y-%m-%d")
        if document.doc_created_date
        else None
    )
    payload = {
        "doc_id": document.id,
        "text": text[:5000],  # truncate for safety
        "metadata": {
            "doc_type": document.doc_type,
            "company": None,  # TODO: extract from file_name or text
            "date": date_str,
        },
    }
    logger.info(
        f"[vectorizer] Sending doc_id={document.id} type={document.doc_type} "
        f"name='{document.file_name}'"
    )
    # TODO: replace with real call e.g.:
    # import httpx
    # httpx.post(VECTORIZER_URL, json=payload, timeout=30)
    _ = payload  # suppress unused-variable warning


# ── Per-file processing ───────────────────────────────────────────────────────

def process_file(
    db,
    user: User,
    file_meta: dict,
) -> Optional[Document]:
    """
    Full processing pipeline for a single Drive file.

    Returns the created/updated Document on success, None on failure.
    """
    file_id = file_meta["id"]
    file_name = file_meta["name"]

    logger.info(f"Processing '{file_name}' ({file_id})")

    # 1. Download
    content = fetch_file_content(user, file_id)
    if content is None:
        logger.error(f"Skipping '{file_name}' – download failed")
        return None

    checksum = compute_checksum(content)
    drive_created_time = parse_drive_created_time(file_meta)

    # Create a pending record immediately so a crash doesn't reprocess the file
    doc_data = DocumentCreate(
        user_id=user.id,
        file_id=file_id,
        file_name=file_name,
        drive_created_time=drive_created_time,
        checksum=checksum,
        status="pending",
    )
    document = create_document(db, doc_data)

    try:
        # 2. Extract text
        text = extract_text(content, file_name)

        # 3. Classify
        doc_type = classify_document(text, file_name)

        # 4. Extract date
        doc_created_date = _extract_doc_date(text) or drive_created_time

        # 5. Summarize
        description = generate_description(text)

        # 6. Persist results
        document = update_document(
            db,
            document.id,
            doc_type=doc_type,
            description=description,
            doc_created_date=doc_created_date,
            status="processed",
        )
        logger.info(
            f"Processed '{file_name}' → type={doc_type} date={doc_created_date}"
        )
        return document

    except Exception as exc:
        logger.error(f"Processing failed for '{file_name}': {exc}", exc_info=True)
        update_document(db, document.id, status="failed")
        return None


# ── Per-user pipeline ─────────────────────────────────────────────────────────

def process_user(db, user: User) -> None:
    """Run the full ingestion pipeline for a single user."""
    logger.info(f"── Starting pipeline for user {user.id} ({user.email})")

    new_files = get_unprocessed_files(db, user)
    if not new_files:
        logger.info(f"No new files for user {user.id}")
        return

    processed_docs = []
    for file_meta in new_files:
        doc = process_file(db, user, file_meta)
        if doc:
            processed_docs.append(doc)

    logger.info(
        f"User {user.id}: {len(processed_docs)}/{len(new_files)} file(s) processed"
    )

    # ── Step 5-6: select latest per type & vectorize ───────────────────────
    latest_docs = get_latest_documents_per_type(db, user.id)
    logger.info(f"User {user.id}: {len(latest_docs)} latest document(s) to vectorize")

    for doc in latest_docs:
        # Retrieve cached text is not stored, so we re-download only for vectorization
        content = fetch_file_content(user, doc.file_id)
        if content is None:
            logger.warning(f"Cannot vectorize '{doc.file_name}' – download failed")
            continue
        try:
            text = extract_text(content, doc.file_name)
        except Exception as exc:
            logger.error(f"Re-extraction failed for '{doc.file_name}': {exc}")
            continue

        send_to_vectorizer(doc, text)
        update_document(db, doc.id, status="vectorized")


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    """Main worker loop: iterate over all users and run the pipeline."""
    logger.info("═══ Golden Ledger nightly worker started ═══")
    db = SessionLocal()
    try:
        users = db.query(User).all()
        logger.info(f"Found {len(users)} user(s)")
        for user in users:
            try:
                process_user(db, user)
            except Exception as exc:
                logger.error(
                    f"Unhandled error for user {user.id} ({user.email}): {exc}",
                    exc_info=True,
                )
    finally:
        db.close()
    logger.info("═══ Worker run complete ═══")


if __name__ == "__main__":
    run()
