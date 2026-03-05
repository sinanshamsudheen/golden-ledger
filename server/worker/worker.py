"""
Nightly document processing worker.

Pipeline (per user):
  1.  Fetch all users from the database
  2.  Skip users without Drive connected or folder configured
  3.  Identify new (unprocessed) files in the Drive folder (recursively)
  4.  For each new file: download content + extract text (parallel)
  5.  Batch LLM analysis — all docs in one pass (20 per call, parallel chunks)
      folder_path is passed as a context hint so LLM can factor in location
  6.  Persist all documents (with deal_id) to the database
  7.  Mark superseded versions within each deal
  8.  Send latest docs per type to the vectorizer pipeline

Run manually:
    python server/worker/worker.py   (from project root)
    python worker/worker.py          (from server/)

Scheduled via cron:
    0 2 * * * /path/to/venv/bin/python /path/to/server/worker/worker.py
"""

import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SERVER_DIR)

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
from worker.batch_analyzer import analyze_batch, AnalysisResult
from worker.summarizer import text_summary
from worker.deal_resolver import get_or_create_deal

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
)
logger = logging.getLogger("worker")


# ── Version management ────────────────────────────────────────────────────────

def _mark_superseded_versions(db, document: Document) -> None:
    """
    Mark older documents with the same (user_id, doc_type, deal_id) as superseded.
    Only runs when deal_id and doc_created_date are both known.
    """
    if not document.deal_id or not document.doc_created_date:
        return

    older = (
        db.query(Document)
        .filter(
            Document.user_id == document.user_id,
            Document.doc_type == document.doc_type,
            Document.deal_id == document.deal_id,
            Document.id != document.id,
            Document.doc_created_date < document.doc_created_date,
            Document.version_status == "current",
        )
        .all()
    )
    for doc in older:
        doc.version_status = "superseded"
        logger.info(
            f"Marked '{doc.file_name}' (id={doc.id}) as superseded by '{document.file_name}'"
        )
    if older:
        db.commit()


# ── Vectorizer integration ────────────────────────────────────────────────────

def send_to_vectorizer(document: Document, text: str) -> None:
    """Placeholder: send a processed document to the external vectorizer pipeline."""
    date_str = (
        document.doc_created_date.strftime("%Y-%m-%d") if document.doc_created_date else None
    )
    payload = {
        "doc_id": document.id,
        "text": text[:5000],
        "metadata": {
            "doc_type": document.doc_type,
            "deal_id": document.deal_id,
            "date": date_str,
        },
    }
    logger.info(
        f"[vectorizer] doc_id={document.id} type={document.doc_type} "
        f"deal_id={document.deal_id} name='{document.file_name}'"
    )
    _ = payload  # TODO: replace with real HTTP call


# ── Per-user pipeline ─────────────────────────────────────────────────────────

def process_user(db, user: User) -> None:
    """Run the full ingestion pipeline for a single user."""
    logger.info(f"── Starting pipeline for user {user.id} ({user.email})")

    new_files = get_unprocessed_files(db, user)
    if not new_files:
        logger.info(f"No new files for user {user.id}")
        return

    # ── Step 1: Download + extract text (parallel) ───────────────────────────
    prepared: list[dict] = []

    def _download_and_extract(file_meta: dict) -> dict | None:
        file_id = file_meta["id"]
        file_name = file_meta["name"]
        folder_path = file_meta.get("folder_path", "")

        content = fetch_file_content(user, file_id)
        if content is None:
            logger.error(f"Skipping '{file_name}' – download failed")
            return None

        try:
            text = extract_text(content, file_name)
        except Exception as exc:
            logger.error(f"Skipping '{file_name}' – text extraction failed: {exc}")
            return None

        return {
            "file_meta": file_meta,
            "content": content,
            "text": text,
            "checksum": compute_checksum(content),
            "drive_created_time": parse_drive_created_time(file_meta),
            "folder_path": folder_path,
        }

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_download_and_extract, fm): fm for fm in new_files}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                prepared.append(result)

    # Restore original ordering (as_completed gives arbitrary order)
    order = {fm["id"]: idx for idx, fm in enumerate(new_files)}
    prepared.sort(key=lambda x: order.get(x["file_meta"]["id"], 0))

    if not prepared:
        return

    # ── Step 2: Batch LLM analysis (all docs) ────────────────────────────────
    # folder_path is passed as a soft context hint so the LLM can factor in
    # file location, but LLM output is always authoritative.
    llm_results: dict[str, AnalysisResult] = {}
    batch_items = [
        {
            "custom_id": item["file_meta"]["id"],
            "file_name": item["file_meta"]["name"],
            "text": item["text"],
            "folder_path": item["folder_path"],
        }
        for item in prepared
    ]
    analysis = analyze_batch(batch_items)
    for result in analysis:
        llm_results[result.custom_id] = result

    logger.info(f"User {user.id}: {len(prepared)} file(s) through LLM batch")

    # ── Step 3: Persist all documents ────────────────────────────────────────
    processed_docs: list[Document] = []

    for item in prepared:
        fid = item["file_meta"]["id"]
        fname = item["file_meta"]["name"]
        folder_path = item["folder_path"]

        doc_data = DocumentCreate(
            user_id=user.id,
            file_id=fid,
            file_name=fname,
            drive_created_time=item["drive_created_time"],
            checksum=item["checksum"],
            status="pending",
        )
        document = create_document(db, doc_data)

        try:
            if fid in llm_results:
                r = llm_results[fid]
                doc_type = r.doc_type
                raw_deal_name: Optional[str] = r.deal_name
                doc_date = r.doc_date or item["drive_created_time"]
                description = r.summary or text_summary(item["text"])
            else:
                # LLM unavailable — store with safe defaults, no deal attribution
                doc_type = "pitch_deck"
                raw_deal_name = None
                doc_date = item["drive_created_time"]
                description = text_summary(item["text"])

            # Resolve deal_id
            deal_id: Optional[int] = None
            if raw_deal_name:
                deal = get_or_create_deal(db, user.id, raw_deal_name)
                deal_id = deal.id if deal else None

            updated = update_document(
                db,
                document.id,
                doc_type=doc_type,
                description=description,
                doc_created_date=doc_date,
                deal_id=deal_id,
                folder_path=folder_path or None,
                status="processed",
            )
            logger.info(
                f"Persisted '{fname}' → type={doc_type} deal_id={deal_id} "
                f"folder='{folder_path}' date={doc_date}"
            )
            if updated:
                processed_docs.append(updated)

        except Exception as exc:
            logger.error(f"Persist failed for '{fname}': {exc}", exc_info=True)
            update_document(db, document.id, status="failed")

    logger.info(
        f"User {user.id}: {len(processed_docs)}/{len(prepared)} file(s) persisted"
    )

    # ── Step 4: Version management ────────────────────────────────────────────
    for doc in processed_docs:
        _mark_superseded_versions(db, doc)

    # ── Step 5: Vectorize latest per type ─────────────────────────────────────
    # Build a cache of already-extracted text from this run to avoid re-downloading
    text_cache: dict[str, str] = {
        item["file_meta"]["id"]: item["text"] for item in prepared
    }

    latest_docs = get_latest_documents_per_type(db, user.id)
    logger.info(f"User {user.id}: {len(latest_docs)} document(s) to vectorize")

    for doc in latest_docs:
        if doc.file_id in text_cache:
            text = text_cache[doc.file_id]
        else:
            # Doc was already processed in a prior run — must re-download
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
