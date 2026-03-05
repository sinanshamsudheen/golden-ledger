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

import fcntl
import logging
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import sqlalchemy

# ── Path setup ────────────────────────────────────────────────────────────────
_SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _SERVER_DIR)

from dotenv import load_dotenv  # type: ignore

_env_path = os.path.join(_SERVER_DIR, ".env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)

# ── Internal imports ──────────────────────────────────────────────────────────
from app.config import settings as cfg
from app.database import SessionLocal, engine
from app.models.user import User
from app.models.document import Document
from app.models.deal import Deal
from app.schemas.document_schema import DocumentCreate
from app.services.document_service import (
    create_document,
    update_document,
    get_latest_documents_per_type,
)

from worker.drive_ingestion import (
    get_unprocessed_files,
    fetch_file_content,
    get_user_drive_credentials,
    compute_checksum,
    parse_drive_created_time,
)
from worker.parser import extract_text, PasswordProtectedError
from worker.batch_analyzer import analyze_batch, AnalysisResult
from worker.summarizer import text_summary
from worker.deal_resolver import get_or_create_deal
from worker.vectorizer import ingest_and_analyze_deal

# ── Logging ───────────────────────────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s – %(message)s"
_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

import datetime as _dt
_run_ts = _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
_log_file = os.path.join(_LOG_DIR, f"worker_{_run_ts}.log")

_root = logging.getLogger()
_root.setLevel(logging.INFO)

_fmt = logging.Formatter(_LOG_FORMAT)

_sh = logging.StreamHandler()
_sh.setFormatter(_fmt)
_root.addHandler(_sh)

_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(_fmt)
_root.addHandler(_fh)

logger = logging.getLogger("worker")
logger.info(f"Logging to {_log_file}")

INGEST_BATCH = 100  # max files per download → LLM → persist cycle — caps peak RAM

# ── Version management ────────────────────────────────────────────────────────

def _mark_superseded_versions(db, document: Document) -> None:
    """
    Mark older documents with the same type+deal as superseded.

    Two-pass strategy:
      Pass A (deal-scoped)  — when deal_id is known, group by (user_id, doc_type, deal_id).
      Pass B (folder-scoped) — when deal_id is None, group by (user_id, doc_type, folder_path)
                               so files in misc/ or unresolved folders still get versioned.

    Both passes require doc_created_date to determine which is newer.
    """
    if not document.doc_created_date:
        return

    if document.deal_id:
        # Pass A: deal-scoped versioning
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
    else:
        # Pass B: folder-scoped versioning for dealless documents
        if not document.folder_path:
            return
        older = (
            db.query(Document)
            .filter(
                Document.user_id == document.user_id,
                Document.doc_type == document.doc_type,
                Document.deal_id.is_(None),
                Document.folder_path == document.folder_path,
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


# ── Per-user pipeline ─────────────────────────────────────────────────────────

def process_user(db, user: User) -> None:
    """
    Run the full ingestion pipeline for a single user.

    Files are processed in memory-bounded batches of INGEST_BATCH to cap
    peak RAM.  Credentials are fetched once and reused across all downloads
    to avoid an OAuth round-trip per file.  Version management and
    vectorization run once after all batches for a consistent final state.
    """
    logger.info(f"── Starting pipeline for user {user.id} ({user.email})")

    new_files = get_unprocessed_files(db, user)
    if not new_files:
        logger.info(f"No new files for user {user.id}")
        return

    # Get credentials once — shared across all download threads so the OAuth
    # token is refreshed exactly once, not once per file.
    try:
        drive_credentials = get_user_drive_credentials(user)
    except Exception as exc:
        logger.warning(f"Could not pre-fetch drive credentials: {exc} — falling back to per-file auth")
        drive_credentials = None

    # Accumulators across all batches
    all_processed_docs: list[Document] = []

    total = len(new_files)
    total_batches = (total + INGEST_BATCH - 1) // INGEST_BATCH

    for batch_start in range(0, total, INGEST_BATCH):
        batch = new_files[batch_start : batch_start + INGEST_BATCH]
        batch_num = batch_start // INGEST_BATCH + 1
        logger.info(
            f"User {user.id}: batch {batch_num}/{total_batches} — {len(batch)} file(s)"
        )

        # ── Step 1: Download + extract text (parallel) ───────────────────────
        prepared: list[dict] = []

        def _download_and_extract(file_meta: dict) -> dict | None:
            file_id = file_meta["id"]
            file_name = file_meta["name"]
            folder_path = file_meta.get("folder_path", "")

            content = fetch_file_content(user, file_id, credentials=drive_credentials)
            if content is None:
                logger.error(f"Skipping '{file_name}' – download failed")
                return None

            try:
                text = extract_text(content, file_name)
            except PasswordProtectedError:
                logger.info(f"'{file_name}' is password-protected — flagging")
                return {
                    "file_meta": file_meta,
                    "content": content,
                    "text": "",
                    "checksum": compute_checksum(content),
                    "drive_created_time": parse_drive_created_time(file_meta),
                    "folder_path": folder_path,
                    "password_protected": True,
                }
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
            futures = {pool.submit(_download_and_extract, fm): fm for fm in batch}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    prepared.append(result)

        # Restore batch ordering (as_completed returns in completion order)
        order = {fm["id"]: idx for idx, fm in enumerate(batch)}
        prepared.sort(key=lambda x: order.get(x["file_meta"]["id"], 0))

        if not prepared:
            continue

        # ── Step 2: Batch LLM analysis ───────────────────────────────────────
        llm_results: dict[str, AnalysisResult] = {}
        batch_items = [
            {
                "custom_id": item["file_meta"]["id"],
                "file_name": item["file_meta"]["name"],
                "text": item["text"],
                "folder_path": item["folder_path"],
            }
            for item in prepared
            if not item.get("password_protected")
        ]
        analysis = analyze_batch(batch_items)
        for result in analysis:
            llm_results[result.custom_id] = result

        logger.info(f"User {user.id}: {len(prepared)} file(s) through LLM batch")

        # ── Reconnect DB after potentially long LLM batch ─────────────────────
        # The LLM call can take minutes; Railway's Postgres proxy may drop the
        # idle SSL connection in the meantime.  Always close + reopen the
        # session's connection so SQLAlchemy grabs a fresh one from the pool
        # (pool_pre_ping will verify liveness) before persisting.
        try:
            db.execute(sqlalchemy.text("SELECT 1"))
            logger.debug("DB ping OK before persist step")
        except Exception as _ping_err:
            logger.warning("DB ping failed (%s) – reconnecting", _ping_err)
            try:
                db.rollback()
            except Exception:
                pass
            try:
                db.close()
            except Exception:
                pass
            engine.dispose()  # recycle all pooled connections

        # ── Step 3: Persist ───────────────────────────────────────────────────
        batch_persisted = 0
        for item in prepared:
            fid = item["file_meta"]["id"]
            fname = item["file_meta"]["name"]
            folder_path = item["folder_path"]

            # ── Password-protected: persist tombstone, infer deal from folder path ──
            if item.get("password_protected"):
                doc_data = DocumentCreate(
                    user_id=user.id,
                    file_id=fid,
                    file_name=fname,
                    drive_created_time=item["drive_created_time"],
                    checksum=item["checksum"],
                    status="pending",
                )
                document = create_document(db, doc_data)
                # Infer deal from first folder component (e.g. "Acme Corp/Q1" → "Acme Corp")
                locked_deal_id: Optional[int] = None
                if folder_path:
                    hint = folder_path.split("/")[0].strip()
                    if hint:
                        d = get_or_create_deal(db, user.id, hint)
                        locked_deal_id = d.id if d else None
                update_document(
                    db,
                    document.id,
                    doc_type="password_protected",
                    folder_path=folder_path or None,
                    deal_id=locked_deal_id,
                    status="skipped",
                )
                logger.info(
                    f"Flagged '{fname}' as password-protected — deal_id={locked_deal_id}"
                )
                continue

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
                    # LLM unavailable — store with safe defaults
                    doc_type = "pitch_deck"
                    raw_deal_name = None
                    doc_date = item["drive_created_time"]
                    description = text_summary(item["text"])

                # Client/portfolio file: store tombstone so it's never re-downloaded,
                # but exclude it from all deal processing and vectorization.
                if fid in llm_results and llm_results[fid].is_client:
                    update_document(
                        db,
                        document.id,
                        doc_type="client",
                        description=description,
                        doc_created_date=doc_date,
                        folder_path=folder_path or None,
                        status="skipped",
                    )
                    logger.info(f"Skipped '{fname}' — identified as client/portfolio file")
                    continue

                # Unrelated documents: store a permanent tombstone so this
                # file_id stays in known_ids and is never re-downloaded on
                # any future run. These rows are invisible to all API queries
                # and are never passed to the vectorizer.
                if doc_type == "other":
                    update_document(
                        db,
                        document.id,
                        doc_type="other",
                        description=description,
                        doc_created_date=doc_date,
                        folder_path=folder_path or None,
                        status="skipped",
                    )
                    logger.info(f"Skipped '{fname}' — unrelated document (type=other)")
                    continue

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
                    all_processed_docs.append(updated)
                    batch_persisted += 1

            except Exception as exc:
                logger.error(f"Persist failed for '{fname}': {exc}", exc_info=True)
                update_document(db, document.id, status="failed")

        logger.info(
            f"User {user.id}: batch {batch_num}/{total_batches} complete "
            f"({batch_persisted}/{len(prepared)} persisted, "
            f"{len(all_processed_docs)} total so far)"
        )
        # Release batch content bytes — text_cache already holds what we need
        prepared.clear()

    # ── Step 4: Version management (once, after all batches) ─────────────────
    # Running after all docs are persisted is more correct: the full date
    # picture is visible, so older duplicates across batch boundaries are caught.
    for doc in all_processed_docs:
        _mark_superseded_versions(db, doc)

    # ── Step 4.5: Retire meeting-minutes-only deals ───────────────────────────
    # A deal whose only classified documents are meeting_minutes is a
    # client/portfolio deal, not a pipeline opportunity.  Mark every document
    # in such deals as doc_type="client", status="skipped" so they:
    #   • are never vectorized
    #   • never appear in API responses (same tombstone used for is_client flag)
    _PIPELINE_TYPES = {"pitch_deck", "investment_memo", "prescreening_report"}
    all_deal_ids = {doc.deal_id for doc in all_processed_docs if doc.deal_id is not None}
    retired_deals = 0
    for deal_id in all_deal_ids:
        deal_docs = (
            db.query(Document)
            .filter(
                Document.deal_id == deal_id,
                Document.user_id == user.id,
                Document.doc_type.in_(list(_PIPELINE_TYPES) + ["meeting_minutes"]),
                Document.status.in_(["processed", "vectorized"]),
            )
            .all()
        )
        if not deal_docs:
            continue
        has_pipeline = any(d.doc_type in _PIPELINE_TYPES for d in deal_docs)
        if has_pipeline:
            continue
        # Every current doc is meeting_minutes — retire them all
        for d in deal_docs:
            update_document(db, d.id, doc_type="client", status="skipped")
        # Also remove from all_processed_docs so they skip version-mgmt + vectorization
        all_processed_docs = [d for d in all_processed_docs if d.deal_id != deal_id]
        retired_deals += 1
        logger.info(
            f"Retired deal_id={deal_id} — all {len(deal_docs)} doc(s) are meeting_minutes only"
        )
    if retired_deals:
        logger.info(f"User {user.id}: retired {retired_deals} meeting-minutes-only deal(s)")

    # ── Step 5: Vectorize + analyze per deal (requires VECTORIZER_INGEST_URL) ────
    if not cfg.VECTORIZER_INGEST_URL:
        logger.info(
            f"User {user.id}: VECTORIZER_INGEST_URL not configured — skipping vectorization"
        )
        return

    latest_docs = get_latest_documents_per_type(db, user.id)

    # Group by deal_id — only deal-associated documents get the full pipeline.
    # Dealless documents are skipped: without a deal they cannot receive an
    # investment_type / deal_status from the Analytical endpoint.
    # Documents that already have a vectorizer_doc_id are also skipped — they
    # were successfully ingested on a previous run.
    per_deal_docs: dict[int, list[Document]] = {}
    dealless_count = 0
    already_vectorized_count = 0
    for doc in latest_docs:
        if doc.deal_id is None:
            dealless_count += 1
        elif doc.vectorizer_doc_id is not None:
            already_vectorized_count += 1
        else:
            per_deal_docs.setdefault(doc.deal_id, []).append(doc)

    logger.info(
        f"User {user.id}: {len(per_deal_docs)} deal(s) need vectorization "
        f"({already_vectorized_count} doc(s) already vectorized, "
        f"{dealless_count} dealless doc(s) skipped)"
    )

    # Run all deals in parallel — each gets its own DB session via
    # _vectorize_deal_isolated so sessions are never shared across threads.
    deal_tasks = [
        (user.id, deal_id, [d.id for d in deal_doc_list])
        for deal_id, deal_doc_list in per_deal_docs.items()
    ]
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="vec") as pool:
        futures = {
            pool.submit(_vectorize_deal_isolated, uid, did, doc_ids): did
            for uid, did, doc_ids in deal_tasks
        }
        for future in as_completed(futures):
            deal_id = futures[future]
            exc = future.exception()
            if exc:
                logger.error(
                    f"Deal {deal_id} vectorization thread raised: {exc}",
                    exc_info=exc,
                )


# ── Entry point ───────────────────────────────────────────────────────────────

def _process_user_isolated(user_id: int) -> None:
    """Process a single user in an isolated DB session (safe for threads)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            logger.warning(f"User {user_id} not found — skipping")
            return
        process_user(db, user)
    except Exception as exc:
        logger.error(
            f"Unhandled error for user {user_id}: {exc}",
            exc_info=True,
        )
    finally:
        db.close()

def _vectorize_deal_isolated(user_id: int, deal_id: int, doc_ids: list[int]) -> None:
    """
    Vectorize a single deal in its own DB session — safe to run in a thread.

    Opens a fresh SessionLocal, re-fetches user/deal/docs by primary key, runs
    the full ingest+analyze pipeline, then closes the session.  Each deal
    therefore has an independent connection so multiple deals can be processed
    in parallel without SQLAlchemy "concurrent operations" errors.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        deal = db.query(Deal).filter(Deal.id == deal_id).first()
        if user is None or deal is None:
            logger.warning(f"[vectorizer] user {user_id} or deal {deal_id} missing \u2014 skipping")
            return
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        if not docs:
            return
        ingest_and_analyze_deal(db, user, deal, docs)
        for doc in docs:
            update_document(db, doc.id, status="vectorized")
    except Exception as exc:
        logger.error(
            f"Vectorization failed for deal {deal_id}: {exc}",
            exc_info=True,
        )
    finally:
        db.close()

def run() -> None:
    """Main worker loop: process all users in parallel (one thread each, max 5)."""
    _lock_path = os.path.join(tempfile.gettempdir(), "golden_ledger_worker.lock")
    lock_file = open(_lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        logger.warning(
            "Another worker instance is already running (lock held at %s) — exiting.",
            _lock_path,
        )
        lock_file.close()
        return

    try:
        _run()
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _run() -> None:
    """Inner run — called only when the exclusive lock is held."""
    logger.info("═══ Golden Ledger nightly worker started ═══")
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User.id).all()]
    finally:
        db.close()

    if not user_ids:
        logger.info("No users found — nothing to do")
        logger.info("═══ Worker run complete ═══")
        return

    logger.info(f"Found {len(user_ids)} user(s) — processing in parallel (max 5 threads)")
    max_workers = min(len(user_ids), 5)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_user_isolated, uid): uid for uid in user_ids}
        for future in as_completed(futures):
            uid = futures[future]
            exc = future.exception()
            if exc:
                logger.error(f"Thread for user {uid} raised: {exc}", exc_info=exc)
            else:
                logger.info(f"User {uid} processed successfully")

    logger.info("═══ Worker run complete ═══")


def run_vectorizer_only() -> None:
    """
    Skip Drive sync + LLM analysis — only run the vectorizer + Analytical
    pipeline on deals that already have documents in the DB but haven't
    been vectorized yet (vectorizer_doc_id IS NULL on their docs).
    """
    logger.info("═══ Vectorizer-only run started ═══")
    db = SessionLocal()
    try:
        user_ids = [u.id for u in db.query(User.id).all()]
    finally:
        db.close()

    for uid in user_ids:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == uid).first()
            if not user or not user.folder_id:
                continue

            # All deals that have at least one unvectorized current doc
            latest_docs = get_latest_documents_per_type(db, uid)
            per_deal: dict[int, list[int]] = {}   # deal_id -> [doc_id, ...]
            for doc in latest_docs:
                if doc.deal_id is not None and doc.vectorizer_doc_id is None:
                    per_deal.setdefault(doc.deal_id, []).append(doc.id)

            logger.info(
                f"User {uid}: {len(per_deal)} deal(s) need vectorization"
            )
        finally:
            db.close()

        # Run all deals in parallel; each opens its own session
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="vec") as pool:
            futures = {
                pool.submit(_vectorize_deal_isolated, uid, did, doc_ids): did
                for did, doc_ids in per_deal.items()
            }
            for future in as_completed(futures):
                deal_id = futures[future]
                exc = future.exception()
                if exc:
                    logger.error(
                        f"Deal {deal_id} vectorization thread raised: {exc}",
                        exc_info=exc,
                    )

    logger.info("═══ Vectorizer-only run complete ═══")


if __name__ == "__main__":
    import sys
    if "--vectorize-only" in sys.argv:
        run_vectorizer_only()
    else:
        run()
