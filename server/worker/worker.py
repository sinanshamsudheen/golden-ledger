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
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
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
from app.constants import PIPELINE_TYPES as _PIPELINE_TYPES_CONST
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
from worker.vectorizer import ingest_and_analyze_deal, rerun_analytical_and_fields

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

# ── Per-user run statistics ───────────────────────────────────────────────────

@dataclass
class _RunStats:
    user_id: int
    new_files_found: int = 0
    downloaded: int = 0          # successfully downloaded + extracted
    download_failed: int = 0     # download or extraction error
    password_protected: int = 0
    skipped_client: int = 0
    skipped_other: int = 0
    persisted: int = 0           # status=processed
    persist_failed: int = 0
    superseded: int = 0          # marked superseded by version management
    retired_deals: int = 0       # meeting-minutes-only deals retired
    deals_vectorized: int = 0    # deals sent to vectorizer this run
    docs_already_vectorized: int = 0
    dealless_skipped: int = 0
    elapsed_seconds: float = 0.0


# ── Version management ────────────────────────────────────────────────────────

def _bulk_mark_superseded(db, processed_docs: list) -> int:
    """
    Mark older documents as superseded in bulk — one UPDATE per (user_id, doc_type, group)
    instead of one SELECT + commit per document.

    Two-pass strategy:
      Pass A (deal-scoped)   — docs with deal_id: group by (user_id, doc_type, deal_id).
      Pass B (folder-scoped) — docs without deal_id: group by (user_id, doc_type, folder_path).

    Both passes require doc_created_date to determine which is newer.
    """
    # Split into two buckets
    deal_docs: list = []
    folder_docs: list = []
    for doc in processed_docs:
        if not doc.doc_created_date:
            continue
        if doc.deal_id:
            deal_docs.append(doc)
        elif doc.folder_path:
            folder_docs.append(doc)

    total_superseded = 0

    # Pass A: deal-scoped — group by (user_id, doc_type, deal_id), keep newest per group
    a_groups: dict[tuple, list] = {}
    for doc in deal_docs:
        key = (doc.user_id, doc.doc_type, doc.deal_id)
        a_groups.setdefault(key, []).append(doc)

    for (user_id, doc_type, deal_id), docs in a_groups.items():
        newest = max(docs, key=lambda d: d.doc_created_date)
        exclude_ids = [d.id for d in docs]
        n = (
            db.query(Document)
            .filter(
                Document.user_id == user_id,
                Document.doc_type == doc_type,
                Document.deal_id == deal_id,
                Document.id.notin_(exclude_ids),
                Document.doc_created_date < newest.doc_created_date,
                Document.version_status == "current",
            )
            .update({"version_status": "superseded"}, synchronize_session="fetch")
        )
        total_superseded += n

    # Pass B: folder-scoped — group by (user_id, doc_type, folder_path)
    b_groups: dict[tuple, list] = {}
    for doc in folder_docs:
        key = (doc.user_id, doc.doc_type, doc.folder_path)
        b_groups.setdefault(key, []).append(doc)

    for (user_id, doc_type, folder_path), docs in b_groups.items():
        newest = max(docs, key=lambda d: d.doc_created_date)
        exclude_ids = [d.id for d in docs]
        n = (
            db.query(Document)
            .filter(
                Document.user_id == user_id,
                Document.doc_type == doc_type,
                Document.deal_id.is_(None),
                Document.folder_path == folder_path,
                Document.id.notin_(exclude_ids),
                Document.doc_created_date < newest.doc_created_date,
                Document.version_status == "current",
            )
            .update({"version_status": "superseded"}, synchronize_session="fetch")
        )
        total_superseded += n

    if total_superseded:
        db.commit()
        logger.info(f"Bulk supersede: marked {total_superseded} document(s) as superseded")
    return total_superseded  # always int (0 when nothing was superseded)


# ── Per-user pipeline ─────────────────────────────────────────────────────────

def process_user(db, user: User) -> _RunStats:
    """
    Run the full ingestion pipeline for a single user.

    Files are processed in memory-bounded batches of cfg.INGEST_BATCH_SIZE to cap
    peak RAM.  Credentials are fetched once and reused across all downloads
    to avoid an OAuth round-trip per file.  Version management and
    vectorization run once after all batches for a consistent final state.

    Returns a _RunStats with per-user counters for the final summary.
    """
    stats = _RunStats(user_id=user.id)
    _t0 = _time.monotonic()
    logger.info(f"── Starting pipeline for user {user.id} ({user.email})")

    new_files = get_unprocessed_files(db, user)
    if not new_files:
        logger.info(f"No new files for user {user.id}")
        stats.elapsed_seconds = _time.monotonic() - _t0
        return stats

    stats.new_files_found = len(new_files)

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
    total_batches = (total + cfg.INGEST_BATCH_SIZE - 1) // cfg.INGEST_BATCH_SIZE

    for batch_start in range(0, total, cfg.INGEST_BATCH_SIZE):
        batch = new_files[batch_start : batch_start + cfg.INGEST_BATCH_SIZE]
        batch_num = batch_start // cfg.INGEST_BATCH_SIZE + 1
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

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(_download_and_extract, fm): fm for fm in batch}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    prepared.append(result)
                    stats.downloaded += 1
                else:
                    stats.download_failed += 1

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
        # Pre-fetch all deals for this user once — reused by get_or_create_deal
        # to avoid a DB round-trip per document during fuzzy matching.
        existing_deals = db.query(Deal).filter(Deal.user_id == user.id).all()

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
                        d = get_or_create_deal(db, user.id, hint, existing_deals)
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
                stats.password_protected += 1
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
                    stats.skipped_client += 1
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
                    stats.skipped_other += 1
                    continue

                deal_id: Optional[int] = None
                if raw_deal_name:
                    deal = get_or_create_deal(db, user.id, raw_deal_name, existing_deals)
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
                    stats.persisted += 1

            except Exception as exc:
                logger.error(f"Persist failed for '{fname}': {exc}", exc_info=True)
                update_document(db, document.id, status="failed")
                stats.persist_failed += 1

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
    stats.superseded = _bulk_mark_superseded(db, all_processed_docs)

    # ── Step 4.5: Retire meeting-minutes-only deals ───────────────────────────
    # A deal whose only classified documents are meeting_minutes is a
    # client/portfolio deal, not a pipeline opportunity.
    # Single SELECT across all touched deals, then one bulk UPDATE — avoids
    # N individual queries + M individual commits that would slow at scale.
    all_deal_ids = list({doc.deal_id for doc in all_processed_docs if doc.deal_id is not None})

    if all_deal_ids:
        deal_docs_all = (
            db.query(Document)
            .filter(
                Document.deal_id.in_(all_deal_ids),
                Document.user_id == user.id,
                Document.doc_type.in_(list(_PIPELINE_TYPES_CONST) + ["meeting_minutes"]),
                Document.status.in_(["processed", "vectorized"]),
            )
            .all()
        )

        # Group in Python — no extra queries
        by_deal: dict[int, list[Document]] = {}
        for d in deal_docs_all:
            by_deal.setdefault(d.deal_id, []).append(d)

        minutes_only_ids = {
            deal_id
            for deal_id, docs in by_deal.items()
            if not any(d.doc_type in _PIPELINE_TYPES_CONST for d in docs)
        }

        if minutes_only_ids:
            # One UPDATE statement for all affected docs
            db.query(Document).filter(
                Document.deal_id.in_(list(minutes_only_ids)),
                Document.user_id == user.id,
                Document.status.in_(["processed", "vectorized"]),
            ).update(
                {"doc_type": "client", "status": "skipped"},
                synchronize_session="fetch",
            )
            db.commit()
            all_processed_docs = [
                d for d in all_processed_docs if d.deal_id not in minutes_only_ids
            ]
            stats.retired_deals += len(minutes_only_ids)
            logger.info(
                f"User {user.id}: retired {len(minutes_only_ids)} "
                f"meeting-minutes-only deal(s) — {sum(len(by_deal[i]) for i in minutes_only_ids)} doc(s) marked client/skipped"
            )

    # ── Step 5: Vectorize + analyze per deal (requires VECTORIZER_INGEST_URL) ────
    if not cfg.VECTORIZER_INGEST_URL:
        logger.info(
            f"User {user.id}: VECTORIZER_INGEST_URL not configured — skipping vectorization"
        )
        stats.elapsed_seconds = _time.monotonic() - _t0
        return stats

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

    stats.deals_vectorized = len(per_deal_docs)
    stats.docs_already_vectorized = already_vectorized_count
    stats.dealless_skipped = dealless_count
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
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="vec") as pool:
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

    stats.elapsed_seconds = _time.monotonic() - _t0
    return stats


# ── Entry point ───────────────────────────────────────────────────────────────

def _process_user_isolated(user_id: int) -> Optional[_RunStats]:
    """Process a single user in an isolated DB session (safe for threads)."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            logger.warning(f"User {user_id} not found — skipping")
            return None
        return process_user(db, user)
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
        # Re-query docs so we see the vectorizer_doc_id values committed by
        # ingest_and_analyze_deal.  Only mark a doc 'vectorized' when it
        # actually received an external doc ID — failed docs stay 'processed'
        # so they are retried on the next worker run.
        fresh_docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
        for doc in fresh_docs:
            if doc.vectorizer_doc_id is not None:
                update_document(db, doc.id, status="vectorized")
            else:
                logger.warning(
                    f"[vectorizer] Deal {deal_id}: doc {doc.id} ('{doc.file_name}') "
                    f"has no vectorizer_doc_id — leaving status='{doc.status}' for retry"
                )
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
    run_start = _time.monotonic()
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

    all_stats: list[_RunStats] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process_user_isolated, uid): uid for uid in user_ids}
        for future in as_completed(futures):
            uid = futures[future]
            exc = future.exception()
            if exc:
                logger.error(f"Thread for user {uid} raised: {exc}", exc_info=exc)
            else:
                result = future.result()
                if result is not None:
                    all_stats.append(result)
                logger.info(f"User {uid} processed successfully")

    # ── Final run summary ─────────────────────────────────────────────────────
    total_elapsed = _time.monotonic() - run_start
    mins, secs = divmod(int(total_elapsed), 60)

    if all_stats:
        t_found       = sum(s.new_files_found for s in all_stats)
        t_downloaded  = sum(s.downloaded for s in all_stats)
        t_dl_failed   = sum(s.download_failed for s in all_stats)
        t_persisted   = sum(s.persisted for s in all_stats)
        t_p_failed    = sum(s.persist_failed for s in all_stats)
        t_locked      = sum(s.password_protected for s in all_stats)
        t_client      = sum(s.skipped_client for s in all_stats)
        t_other       = sum(s.skipped_other for s in all_stats)
        t_superseded  = sum(s.superseded for s in all_stats)
        t_retired     = sum(s.retired_deals for s in all_stats)
        t_vec         = sum(s.deals_vectorized for s in all_stats)
        t_already_vec = sum(s.docs_already_vectorized for s in all_stats)
        t_dealless    = sum(s.dealless_skipped for s in all_stats)

        logger.info(
            "\n"
            "╔══════════════════════════════════════════════════════╗\n"
            "║              WORKER RUN SUMMARY                     ║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Users processed       : {len(all_stats):<27}║\n"
            f"║  Total elapsed         : {f'{mins}m {secs}s':<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  New files found       : {t_found:<27}║\n"
            f"║  Downloaded & parsed   : {t_downloaded:<27}║\n"
            f"║  Download failures     : {t_dl_failed:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Persisted (processed) : {t_persisted:<27}║\n"
            f"║  Persist failures      : {t_p_failed:<27}║\n"
            f"║  Password-protected    : {t_locked:<27}║\n"
            f"║  Skipped (client)      : {t_client:<27}║\n"
            f"║  Skipped (other)       : {t_other:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Versions superseded   : {t_superseded:<27}║\n"
            f"║  Deals retired (mins)  : {t_retired:<27}║\n"
            "╠══════════════════════════════════════════════════════╣\n"
            f"║  Deals vectorized      : {t_vec:<27}║\n"
            f"║  Docs already vec'd    : {t_already_vec:<27}║\n"
            f"║  Dealless docs skipped : {t_dealless:<27}║\n"
            "╚══════════════════════════════════════════════════════╝"
        )
    else:
        logger.info(f"No stats collected (elapsed: {mins}m {secs}s)")

    logger.info("═══ Worker run complete ═══")


def run_vectorizer_only() -> None:
    """
    Skip Drive sync + LLM analysis.  Runs the full vectorizer pipeline
    (Stages 1–7) for all deals with incomplete pipeline state:

      Case A — Unvectorized docs (vectorizer_doc_id IS NULL)
                → full Stage 1–7 via ingest_and_analyze_deal

      Case B — All docs vectorized but investment_type IS NULL
                → Stage 6 (Analytical) + Stage 7 (ExtractFields)

      Case C — investment_type set but deal_fields table empty
                → Stage 7 (ExtractFields) only
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

            latest_docs = get_latest_documents_per_type(db, uid)

            # Case A: deals with at least one unvectorized doc → full Stage 1-7
            per_deal_unvec: dict[int, list[int]] = {}
            # Deals fully vectorized — check if Stage 6/7 are incomplete
            fully_vec_deal_ids: set[int] = set()
            per_deal_all: dict[int, list] = {}
            for doc in latest_docs:
                if doc.deal_id is None:
                    continue
                per_deal_all.setdefault(doc.deal_id, []).append(doc)

            for deal_id, docs in per_deal_all.items():
                unvec = [d for d in docs if d.vectorizer_doc_id is None]
                if unvec:
                    per_deal_unvec[deal_id] = [d.id for d in docs]
                else:
                    fully_vec_deal_ids.add(deal_id)

            # Case B/C: fully vectorized deals missing Stage 6 or 7
            partial_deals: list[Deal] = []
            if fully_vec_deal_ids:
                from app.models.deal_field import DealField
                candidate_deals = (
                    db.query(Deal)
                    .filter(Deal.id.in_(fully_vec_deal_ids))
                    .all()
                )
                field_counts: dict[int, int] = {
                    row.deal_id: row.cnt
                    for row in db.query(
                        DealField.deal_id,
                        sqlalchemy.func.count(DealField.id).label("cnt"),
                    )
                    .filter(DealField.deal_id.in_(fully_vec_deal_ids))
                    .group_by(DealField.deal_id)
                    .all()
                }
                for deal in candidate_deals:
                    missing_type = deal.investment_type is None
                    missing_fields = field_counts.get(deal.id, 0) == 0
                    if missing_type or missing_fields:
                        partial_deals.append(deal)

            logger.info(
                f"User {uid}: {len(per_deal_unvec)} deal(s) need full vectorization (Case A), "
                f"{len(partial_deals)} deal(s) need Stage 6/7 only (Cases B/C)"
            )
        finally:
            db.close()

        # Case A — full Stage 1-7
        if per_deal_unvec:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="vec") as pool:
                futures = {
                    pool.submit(_vectorize_deal_isolated, uid, did, doc_ids): did
                    for did, doc_ids in per_deal_unvec.items()
                }
                for future in as_completed(futures):
                    deal_id = futures[future]
                    exc = future.exception()
                    if exc:
                        logger.error(
                            f"Deal {deal_id} vectorization thread raised: {exc}",
                            exc_info=exc,
                        )

        # Cases B/C — re-run Stage 6 and/or Stage 7 only
        for deal in partial_deals:
            db = SessionLocal()
            try:
                fresh_deal = db.query(Deal).filter(Deal.id == deal.id).first()
                if fresh_deal:
                    rerun_analytical_and_fields(db, fresh_deal)
            except Exception as exc:
                logger.error(
                    f"[vectorizer] Deal {deal.id} Stage 6/7 re-run failed: {exc}",
                    exc_info=True,
                )
            finally:
                db.close()

    logger.info("═══ Vectorizer-only run complete ═══")


if __name__ == "__main__":
    import sys
    if "--vectorize-only" in sys.argv:
        run_vectorizer_only()
    else:
        run()
