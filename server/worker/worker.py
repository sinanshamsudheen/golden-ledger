"""
Nightly document processing worker.

Pipeline (per user):
  1.  Fetch all users from the database
  2.  Skip users without Drive connected or folder configured
  3.  Identify new (unprocessed) files in the Drive folder (recursively)
  4.  For each new file: download content + extract text
  5.  Heuristic pre-filter: classify doc type + resolve deal from folder path
  6.  Batch LLM analysis for docs that still need it (20 docs per call)
  7.  Persist all documents (with deal_id) to the database
  8.  Mark superseded versions within each deal
  9.  Send latest docs per type to the vectorizer pipeline

Run manually:
    python server/worker/worker.py   (from project root)
    python worker/worker.py          (from server/)

Scheduled via cron:
    0 2 * * * /path/to/venv/bin/python /path/to/server/worker/worker.py
"""

import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
from worker.classifier import classify_document
from worker.batch_analyzer import analyze_batch, AnalysisResult
from worker.summarizer import generate_description
from worker.deal_resolver import (
    extract_deal_from_folder_path,
    get_or_create_deal,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
)
logger = logging.getLogger("worker")


# ── Date extraction ───────────────────────────────────────────────────────────

def _extract_doc_date(text: str) -> Optional[datetime]:
    """
    Try to extract a document creation date from its text using regex patterns.
    Handles 3 formats with dedicated parsers to avoid group-ordering bugs.
    """
    excerpt = text[:2000]

    # Pattern 1: YYYY-MM-DD
    m = re.search(r"\b(\d{4})[\/\-](\d{2})[\/\-](\d{2})\b", excerpt)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Pattern 2: Month DD, YYYY  (e.g. "March 4, 2026" or "Mar 4 2026")
    m = re.search(
        r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"[\s,]+(\d{1,2})[\s,]+(\d{4})\b",
        excerpt,
        re.IGNORECASE,
    )
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1)[:3].capitalize()} {m.group(2)} {m.group(3)}", "%b %d %Y"
            )
        except ValueError:
            pass

    # Pattern 3: DD/MM/YYYY or MM/DD/YYYY — treat as MM/DD/YYYY
    m = re.search(r"\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})\b", excerpt)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    return None


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

    # ── Step 2: Heuristic pre-filter ─────────────────────────────────────────
    needs_llm: list[dict] = []
    heuristic_results: dict[str, dict] = {}  # file_id → partial result

    for item in prepared:
        fid = item["file_meta"]["id"]
        fname = item["file_meta"]["name"]
        text = item["text"]
        folder_path = item["folder_path"]

        doc_type, confident = classify_document(text, fname)
        deal_name_from_folder = extract_deal_from_folder_path(folder_path)
        doc_date = _extract_doc_date(text)

        if confident and deal_name_from_folder:
            # Both signals confident — skip LLM
            heuristic_results[fid] = {
                "doc_type": doc_type,
                "deal_name": deal_name_from_folder,
                "doc_date": doc_date,
                "summary": None,  # will use fallback summarizer
            }
        else:
            needs_llm.append(
                {
                    "custom_id": fid,
                    "file_name": fname,
                    "text": text,
                    "known_deal_name": deal_name_from_folder,  # hint for prompt
                    "_heuristic_type": doc_type,
                    "_heuristic_date": doc_date,
                }
            )

    logger.info(
        f"User {user.id}: {len(heuristic_results)} heuristic-only, "
        f"{len(needs_llm)} need LLM"
    )

    # ── Step 3: Batch LLM analysis ────────────────────────────────────────────
    llm_results: dict[str, AnalysisResult] = {}
    if needs_llm:
        batch_items = [
            {
                "custom_id": d["custom_id"],
                "file_name": d["file_name"],
                "text": d["text"],
                "known_deal_name": d["known_deal_name"],
            }
            for d in needs_llm
        ]
        analysis = analyze_batch(batch_items)
        for result in analysis:
            llm_results[result.custom_id] = result

        # Folder path always wins over LLM for deal name
        for item in needs_llm:
            fid = item["custom_id"]
            res = llm_results.get(fid)
            if res:
                if res.doc_date is None:
                    res.doc_date = item["_heuristic_date"]
                if item["known_deal_name"]:
                    res.deal_name = item["known_deal_name"]

    # ── Step 4: Persist all documents ────────────────────────────────────────
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
            if fid in heuristic_results:
                h = heuristic_results[fid]
                doc_type = h["doc_type"]
                raw_deal_name: Optional[str] = h["deal_name"]
                doc_date = h["doc_date"] or item["drive_created_time"]
                description = generate_description(item["text"])
            elif fid in llm_results:
                r = llm_results[fid]
                doc_type = r.doc_type
                raw_deal_name = r.deal_name
                doc_date = r.doc_date or item["drive_created_time"]
                description = r.summary or generate_description(item["text"])
            else:
                doc_type = "pitch_deck"
                raw_deal_name = extract_deal_from_folder_path(folder_path)
                doc_date = _extract_doc_date(item["text"]) or item["drive_created_time"]
                description = generate_description(item["text"])

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

    # ── Step 5: Version management ────────────────────────────────────────────
    for doc in processed_docs:
        _mark_superseded_versions(db, doc)

    # ── Step 6: Vectorize latest per type ─────────────────────────────────────
    latest_docs = get_latest_documents_per_type(db, user.id)
    logger.info(f"User {user.id}: {len(latest_docs)} document(s) to vectorize")

    for doc in latest_docs:
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
