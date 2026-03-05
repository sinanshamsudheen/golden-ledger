"""
Invitus AI Insights — vectorizer + analytical pipeline integration.

Public interface
----------------
    ingest_and_analyze_deal(db, user, deal, docs)

For each deal this module runs a 6-stage pipeline:

    Stage 1 — Create ingestion job
              POST /v1/api/ingestions  →  job_id + per-doc SAS upload URLs

    Stage 2 — Download files from Google Drive and upload to SAS URLs (parallel)
              PUT <SAS_URL>            →  raw file bytes

    Stage 3 — Confirm uploads to trigger orchestration
              POST /v1/api/jobs/{jobId}/confirm-upload

    Stage 4 — Poll until every document reaches COMPLETED or FAILED
              GET  /v1/api/jobs/{jobId}  (exponential back-off, 25-min cap)

    Stage 5 — Persist vectorizer_doc_id on each completed Document row

    Stage 6 — Call Analytical endpoint with all completed doc IDs
              POST /api/Analytical  →  investment_type + deal_outcome
              Parse and persist results on the Deal row

Configuration
-------------
All settings come from app.config.Settings (loaded from .env):

    VECTORIZER_INGEST_URL      — base URL for the ingestion API
    VECTORIZER_ANALYTICAL_URL  — base URL for the RAG / Analytical gateway
    VECTORIZER_FUNCTION_KEY    — Azure Functions host key
    VECTORIZER_TENANT_ID       — tenant identifier
    VECTORIZER_REGION          — deployment region tag  (default: "uae")
    VECTORIZER_MODULE_ID       — module identifier      (default: "invictus-deals")
    VECTORIZER_USE_CASE_ID     — use-case identifier    (default: "due-diligence")

If VECTORIZER_INGEST_URL is None the caller should skip this module entirely.
"""

import logging
import mimetypes
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger("worker.vectorizer")

# ── Polling tunables ──────────────────────────────────────────────────────────
_MAX_POLL_SECONDS = 25 * 60   # hard cap per the pipeline docs
_POLL_BACKOFF_BASE = 5.0      # first inter-poll delay (seconds)
_POLL_BACKOFF_MULT = 1.5      # growth factor
_POLL_BACKOFF_MAX  = 60.0     # ceiling

# Terminal states defined by the pipeline API spec
_TERMINAL_JOB = frozenset({
    "DOC_PROCESS_COMPLETED",
    "DOC_PROCESS_FAILED",
    "DOC_PROCESS_INCOMPLETED",
    "PROCESSING_COMPLETE",
    "COMPLETED",
})
_TERMINAL_DOC = frozenset({"COMPLETED", "FAILED", "PROCESSING_COMPLETE"})


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cfg():
    """Lazy-import settings so the module can be imported without .env present."""
    from app.config import settings
    return settings


def _api_headers() -> dict[str, str]:
    return {
        "x-functions-key": _cfg().VECTORIZER_FUNCTION_KEY or "",
        "Content-Type": "application/json",
    }


def _rag_headers() -> dict[str, str]:
    s = _cfg()
    key = s.RAG_FUNCTION_KEY or s.VECTORIZER_FUNCTION_KEY or ""
    return {
        "x-functions-key": key,
        "Content-Type": "application/json",
    }


# ── HTTP retry constants ──────────────────────────────────────────────────────
_MAX_HTTP_RETRIES = 3
_HTTP_RETRY_BACKOFF = (5.0, 15.0, 30.0)   # wait (seconds) before attempt n+1


def _retried_request(
    method: str, url: str, *, retries: int = _MAX_HTTP_RETRIES, **kwargs
) -> requests.Response:
    """Make an HTTP request, retrying up to `retries` times on network errors."""
    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):
        try:
            return requests.request(method, url, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt <= retries:
                wait = _HTTP_RETRY_BACKOFF[min(attempt - 1, len(_HTTP_RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"[vectorizer] {method.upper()} {url[:70]} "
                    f"attempt {attempt}/{retries + 1} failed: {exc} "
                    f"\u2014 retrying in {wait:.0f}s"
                )
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def _guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _sanitize_name(name: str) -> str:
    """Replace characters that are unsafe in blob storage paths / SAS URLs."""
    return re.sub(r'[#%?&+]', '_', name)


def _unique_name(doc_type: str, original_name: str) -> str:
    """
    Prefix filename with doc_type so names are unambiguous after the round-trip.
    E.g. "pitch_deck__Q1 Deck.pdf" — safe even when two docs share the same name.
    """
    return f"{doc_type}__{_sanitize_name(original_name)}"


# ── Stage 1 ───────────────────────────────────────────────────────────────────

def _create_ingestion_job(docs: list, user_id: int) -> dict | None:
    """
    POST /v1/api/ingestions.

    Returns {"job_id": str, "name_to_entry": {unique_name: {"doc_id", "put_url"}}}
    or None on failure.
    """
    s = _cfg()
    files_payload = [
        {
            "name": _unique_name(doc.doc_type or "doc", doc.file_name),
            "mime": _guess_mime(doc.file_name),
        }
        for doc in docs
    ]

    body = {
        "tenant_id": s.VECTORIZER_TENANT_ID,
        "region": s.VECTORIZER_REGION,
        "module_id": s.VECTORIZER_MODULE_ID,
        "use_case_id": s.VECTORIZER_USE_CASE_ID,
        "purpose": "deal-analysis",
        "user-id": str(user_id),
        "request-id": str(uuid.uuid4()),
        "data_classification": "confidential",
        "engine_policy": "di_vlm",
        "retention_days": 365,
        "files": files_payload,
    }

    try:
        resp = _retried_request(
            "POST",
            f"{s.VECTORIZER_INGEST_URL}/v1/api/ingestions",
            headers=_api_headers(),
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f"[vectorizer] Create ingestion job failed: {exc}")
        return None

    data = resp.json()
    try:
        ingestion = data["jobs"]["file_ingestion"]
        job_id = ingestion["job_id"]
        upload_urls = ingestion["upload_urls"]   # [{doc_id, name, put_url}]
    except (KeyError, TypeError) as exc:
        logger.error(
            f"[vectorizer] Unexpected ingestion response structure: {exc} — {data}"
        )
        return None

    name_to_entry = {
        entry["name"]: {"doc_id": entry["doc_id"], "put_url": entry["put_url"]}
        for entry in upload_urls
    }
    logger.info(
        f"[vectorizer] Job {job_id} created — {len(upload_urls)} doc(s) to upload"
    )
    return {"job_id": job_id, "name_to_entry": name_to_entry}


# ── Stage 2 (helper) ──────────────────────────────────────────────────────────

def _put_file(put_url: str, content: bytes, filename: str) -> bool:
    """PUT raw bytes to the SAS URL, with up to _MAX_HTTP_RETRIES retries."""
    mime = _guess_mime(filename)
    for attempt in range(1, _MAX_HTTP_RETRIES + 2):   # +1 for initial attempt
        try:
            resp = requests.put(
                put_url,
                headers={"x-ms-blob-type": "BlockBlob", "Content-Type": mime},
                data=content,
                timeout=120,
            )
            if resp.status_code in (200, 201):
                return True
            logger.warning(
                f"[vectorizer] Upload attempt {attempt} failed for '{filename}': "
                f"HTTP {resp.status_code} \u2014 {resp.text[:200]}"
            )
        except Exception as exc:
            logger.warning(
                f"[vectorizer] Upload attempt {attempt} exception for '{filename}': {exc}"
            )
        if attempt <= _MAX_HTTP_RETRIES:
            wait = _HTTP_RETRY_BACKOFF[min(attempt - 1, len(_HTTP_RETRY_BACKOFF) - 1)]
            logger.info(f"[vectorizer] Retrying upload for '{filename}' in {wait:.0f}s ...")
            time.sleep(wait)
    logger.error(
        f"[vectorizer] Upload failed for '{filename}' after {_MAX_HTTP_RETRIES + 1} attempts"
    )
    return False


# ── Stage 3 ───────────────────────────────────────────────────────────────────

def _confirm_uploads(job_id: str, ext_doc_ids: list[str]) -> bool:
    """POST /v1/api/jobs/{jobId}/confirm-upload."""
    s = _cfg()
    body = {"documents": [{"doc_id": did} for did in ext_doc_ids]}
    try:
        resp = _retried_request(
            "POST",
            f"{s.VECTORIZER_INGEST_URL}/v1/api/jobs/{job_id}/confirm-upload",
            headers=_api_headers(),
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        logger.info(
            f"[vectorizer] Job {job_id} confirmed — {len(ext_doc_ids)} doc(s) queued"
        )
        return True
    except Exception as exc:
        logger.error(f"[vectorizer] Confirm-upload failed for job {job_id}: {exc}")
        return False


# ── Stage 4 ───────────────────────────────────────────────────────────────────

def _poll_job(job_id: str) -> dict[str, str] | None:
    """
    Poll GET /v1/api/jobs/{job_id} until a terminal state or timeout.

    Returns {ext_doc_id: status_string} (e.g. {"doc-001": "COMPLETED"})
    or None on timeout / unrecoverable error.
    """
    s = _cfg()
    url = f"{s.VECTORIZER_INGEST_URL}/v1/api/jobs/{job_id}"
    deadline = time.monotonic() + _MAX_POLL_SECONDS
    delay = _POLL_BACKOFF_BASE

    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, headers=_api_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f"[vectorizer] Poll error for job {job_id}: {exc}")
            time.sleep(delay)
            delay = min(delay * _POLL_BACKOFF_MULT, _POLL_BACKOFF_MAX)
            continue

        job_status = data.get("status") or data.get("job_status", "")
        doc_statuses: dict[str, str] = {
            d.get("doc_id", d.get("id", "")): d.get("status") or d.get("doc_status", "")
            for d in data.get("documents", [])
            if d.get("doc_id") or d.get("id")
        }

        all_terminal = bool(doc_statuses) and all(
            st in _TERMINAL_DOC for st in doc_statuses.values()
        )
        logger.info(
            f"[vectorizer] Job {job_id} — job_status={job_status!r}  "
            f"docs={doc_statuses}"
        )

        if job_status in _TERMINAL_JOB or all_terminal:
            return doc_statuses

        time.sleep(delay)
        delay = min(delay * _POLL_BACKOFF_MULT, _POLL_BACKOFF_MAX)

    logger.error(
        f"[vectorizer] Job {job_id} timed out after {_MAX_POLL_SECONDS}s"
    )
    return None


# ── Stage 6 ───────────────────────────────────────────────────────────────────

def _run_analytical(
    ext_doc_ids: list[str],
) -> tuple[str | None, str | None, str | None]:
    """
    POST /api/Analytical with two fields:
        investment_type  — Fund | Direct | Co-Investment
        deal_outcome     — ACCEPTED: <reason> or REJECTED: <reason>

    Returns (investment_type, deal_status, deal_reason).
    Any value may be None if the endpoint cannot determine it.
    """
    s = _cfg()
    payload = {
        "tenant_id": s.VECTORIZER_TENANT_ID,
        "doc_ids": ext_doc_ids,
        "fields": [
            {
                "name": "investment_type",
                "description": (
                    "Classification of the investment opportunity as "
                    "Fund, Direct, or Co-Investment"
                ),
                "instructions": (
                    "Classify this investment as exactly one of: Fund, Direct, Co-Investment. "
                    "Respond with just the classification word — no other text."
                ),
                "reasoning_type": "analysis",
            },
            {
                "name": "deal_outcome",
                "description": (
                    "Final investment committee decision on whether to accept or reject the deal"
                ),
                "instructions": (
                    "Determine whether the investment deal was accepted or rejected. "
                    "Begin your response with exactly 'ACCEPTED:' or 'REJECTED:' "
                    "(uppercase, including the colon), then provide a 1-2 sentence reason. "
                    "Example: 'ACCEPTED: Strong financials and experienced management team.'"
                ),
                "reasoning_type": "synthesis",
            },
        ],
    }

    try:
        resp = _retried_request(
            "POST",
            f"{s.VECTORIZER_ANALYTICAL_URL}/api/Analytical",
            headers=_rag_headers(),
            json=payload,
            timeout=180,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error(f"[vectorizer] Analytical request failed: {exc}")
        return None, None, None

    data = resp.json()
    if data.get("status") != "OK":
        logger.error(
            f"[vectorizer] Analytical returned status={data.get('status')!r}: {data}"
        )
        return None, None, None

    investment_type: str | None = None
    deal_status: str | None = None
    deal_reason: str | None = None

    for field in data.get("fields", []):
        err = field.get("error")
        if err:
            logger.warning(
                f"[vectorizer] Analytical field '{field.get('name')}' error: {err}"
            )
            continue

        summary: str = (field.get("analysis") or {}).get("summary") or ""
        name: str = field.get("name", "")

        if name == "investment_type":
            sl = summary.strip().lower()
            # Check longest/most-specific match first
            if "co-investment" in sl:
                investment_type = "Co-Investment"
            elif "direct" in sl:
                investment_type = "Direct"
            elif "fund" in sl:
                investment_type = "Fund"
            else:
                logger.warning(
                    f"[vectorizer] Cannot parse investment_type "
                    f"from summary: '{summary[:120]}'"
                )

        elif name == "deal_outcome":
            stripped = summary.strip()
            upper = stripped.upper()
            if upper.startswith("ACCEPTED"):
                deal_status = "accepted"
                colon_pos = stripped.find(":")
                deal_reason = (
                    stripped[colon_pos + 1:].strip() if colon_pos != -1
                    else stripped[8:].strip()
                )
            elif upper.startswith("REJECTED"):
                deal_status = "rejected"
                colon_pos = stripped.find(":")
                deal_reason = (
                    stripped[colon_pos + 1:].strip() if colon_pos != -1
                    else stripped[8:].strip()
                )
            else:
                # Fallback: search anywhere in the text
                if "accepted" in upper:
                    deal_status = "accepted"
                elif "rejected" in upper:
                    deal_status = "rejected"
                deal_reason = stripped or None
                logger.warning(
                    f"[vectorizer] deal_outcome did not start with ACCEPTED/REJECTED: "
                    f"'{summary[:120]}'"
                )

    return investment_type, deal_status, deal_reason


# ── Main entry point ──────────────────────────────────────────────────────────

def ingest_and_analyze_deal(db, user, deal, docs: list) -> None:
    """
    Full vectorizer + analytical pipeline for a single deal.

    Parameters
    ----------
    db    — active SQLAlchemy session (caller owns lifecycle)
    user  — User ORM object (for Google Drive credentials)
    deal  — Deal ORM object (results written here)
    docs  — current-version Document objects (≤ 4, one per type)

    Side-effects
    ------------
    • deal.vectorizer_job_id  set after Stage 1
    • doc.vectorizer_doc_id   set for each COMPLETED document after Stage 4
    • deal.investment_type, deal.deal_status, deal.deal_reason  set after Stage 6
    All changes are committed to db before each return path.
    """
    from worker.drive_ingestion import fetch_file_content, get_user_drive_credentials

    if not docs:
        return

    # Pre-fetch Drive credentials once to avoid a round-trip per file
    try:
        credentials = get_user_drive_credentials(user)
    except Exception as exc:
        logger.warning(
            f"[vectorizer] Deal {deal.id}: Drive credentials failed ({exc}) "
            "— will fall back to per-file auth"
        )
        credentials = None

    # ── Stage 1: Create ingestion job ─────────────────────────────────────────
    job_info = _create_ingestion_job(docs, user.id)
    if job_info is None:
        logger.error(
            f"[vectorizer] Deal {deal.id} ({deal.name!r}): job creation failed"
        )
        return

    job_id: str = job_info["job_id"]
    name_to_entry: dict = job_info["name_to_entry"]

    deal.vectorizer_job_id = job_id
    db.commit()

    # ── Stage 2: Download from Drive + upload to SAS URLs (parallel) ──────────
    # Pre-load all needed ORM attributes in the main thread.
    # SQLAlchemy sessions are not thread-safe; lazy-loading inside a
    # ThreadPoolExecutor will raise "concurrent operations are not permitted".
    for _doc in docs:
        _ = _doc.doc_type, _doc.file_name, _doc.file_id

    def _upload_one(doc):
        unique_name = _unique_name(doc.doc_type or "doc", doc.file_name)
        entry = name_to_entry.get(unique_name)
        if entry is None:
            logger.warning(
                f"[vectorizer] No upload entry for '{unique_name}' "
                f"(available: {list(name_to_entry)})"
            )
            return None

        content = fetch_file_content(user, doc.file_id, credentials=credentials)
        if content is None:
            logger.warning(
                f"[vectorizer] Cannot download '{doc.file_name}' from Drive — skipping"
            )
            return None

        if not _put_file(entry["put_url"], content, doc.file_name):
            return None

        logger.info(
            f"[vectorizer] Uploaded '{doc.file_name}' → ext_doc_id={entry['doc_id']}"
        )
        return (doc, entry["doc_id"])

    uploaded: list[tuple] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_upload_one, doc): doc for doc in docs}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                uploaded.append(result)

    if not uploaded:
        logger.error(
            f"[vectorizer] Deal {deal.id} ({deal.name!r}): "
            "no documents uploaded — aborting"
        )
        return

    # ── Stage 3: Confirm uploads ──────────────────────────────────────────────
    ext_ids_uploaded = [ext_id for _, ext_id in uploaded]
    if not _confirm_uploads(job_id, ext_ids_uploaded):
        logger.error(
            f"[vectorizer] Deal {deal.id} ({deal.name!r}): "
            "confirm-upload failed — aborting"
        )
        return

    # ── Stage 4: Poll until job completes ─────────────────────────────────────
    doc_status_map = _poll_job(job_id)
    if doc_status_map is None:
        logger.error(
            f"[vectorizer] Deal {deal.id} ({deal.name!r}): "
            "polling timed out / failed — aborting"
        )
        return

    # ── Stage 5: Persist vectorizer_doc_id for completed docs ────────────────
    ext_ids_completed: list[str] = []
    _SUCCESS_DOC = _TERMINAL_DOC - {"FAILED"}
    for doc, ext_doc_id in uploaded:
        status = doc_status_map.get(ext_doc_id, "")
        if status in _SUCCESS_DOC:
            doc.vectorizer_doc_id = ext_doc_id
            ext_ids_completed.append(ext_doc_id)
            logger.info(
                f"[vectorizer] '{doc.file_name}' {status} "
                f"→ vectorizer_doc_id={ext_doc_id}"
            )
        else:
            logger.warning(
                f"[vectorizer] '{doc.file_name}' not in terminal success states "
                f"(status={status!r}) — excluded from Analytical call"
            )
    db.commit()

    if not ext_ids_completed:
        logger.error(
            f"[vectorizer] Deal {deal.id} ({deal.name!r}): "
            "no documents completed vectorization — skipping Analytical step"
        )
        return

    # ── Stage 6: Analytical endpoint ──────────────────────────────────────────
    investment_type, deal_status, deal_reason = _run_analytical(ext_ids_completed)

    deal.investment_type = investment_type
    deal.deal_status = deal_status
    deal.deal_reason = deal_reason
    db.commit()

    _reason_preview = repr(deal_reason[:80]) if deal_reason else None
    logger.info(
        f"[vectorizer] Deal {deal.id} ({deal.name!r}): "
        f"investment_type={investment_type!r}  "
        f"deal_status={deal_status!r}  "
        f"reason={_reason_preview}"
    )
