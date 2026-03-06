# Worker Pipeline — Developer Reference

The worker is a standalone Python process that runs nightly (or on demand) to ingest, classify, and analyse investment documents from Google Drive. It is completely independent of the FastAPI server and talks to the same PostgreSQL database.

---

## Table of Contents

- [How to Run](#how-to-run)
- [Pipeline Overview](#pipeline-overview)
- [Stage-by-Stage Breakdown](#stage-by-stage-breakdown)
  - [Stage 1 — Drive Discovery](#stage-1--drive-discovery)
  - [Stage 2 — Download & Text Extraction](#stage-2--download--text-extraction)
  - [Stage 3 — Batch LLM Classification](#stage-3--batch-llm-classification)
  - [Stage 4 — Persist & Deal Resolution](#stage-4--persist--deal-resolution)
  - [Stage 5 — Version Management](#stage-5--version-management)
  - [Stage 5.5 — Meeting-Minutes Retirement](#stage-55--meeting-minutes-retirement)
  - [Stage 6 — Vectorization Pipeline](#stage-6--vectorization-pipeline)
  - [Stage 7 — Analytical Endpoint](#stage-7--analytical-endpoint)
  - [Stage 8 — Field Extraction](#stage-8--field-extraction)
- [Document Statuses](#document-statuses)
- [What Gets Skipped](#what-gets-skipped)
- [What Is Hidden from the UI](#what-is-hidden-from-the-ui)
- [Deal Resolution Logic](#deal-resolution-logic)
- [Version Management Logic](#version-management-logic)
- [Module Reference](#module-reference)
- [Config Tuning](#config-tuning)
- [Logs](#logs)

---

## How to Run

```bash
# from server/
python worker/worker.py

# skip Drive sync + LLM — only re-run the vectorizer pipeline for incomplete deals
python worker/worker.py --vectorize-only
```

A file lock (`/tmp/golden_ledger_worker.lock`) prevents two instances from running simultaneously. If you kill the process mid-run, delete the lock file before restarting.

---

## Pipeline Overview

```
Google Drive folder (recursive)
        │
        ▼
[Stage 1]  Discover new files
           Filter out known file_ids and known MD5 checksums
        │
        ▼
[Stage 2]  Download + extract text   (20 parallel threads)
           PDF → pdfminer · PPTX → python-pptx · DOCX → python-docx
           Password-protected files → flagged, not extracted
        │
        ▼
[Stage 3]  Batch LLM classification  (30 docs/call, up to 10 parallel calls)
           → doc_type, deal_name, doc_date, summary, is_client
        │
        ▼
[Stage 4]  Persist to PostgreSQL
           Deal resolution (exact key → fuzzy match → create)
           Password-protected, client, and "other" docs stored as tombstones
        │
        ▼
[Stage 5]  Version management  (bulk UPDATE, one pass after all batches)
           Mark older docs of the same type in the same deal as superseded
        │
        ▼
[Stage 5.5] Retire meeting-minutes-only deals
            Deals with no pitch_deck / memo / prescreening → marked client/skipped
        │
        ▼
[Stage 6]  Vectorization  (Invitus AI Insights, per deal, sequential)
           7-stage sub-pipeline: create job → upload → confirm → poll → persist IDs
        │
        ▼
[Stage 7]  Analytical endpoint
           → investment_type (Fund | Direct | Co-Investment)
           → deal_status (ACCEPTED | REJECTED | REVIEWING | ...)
           → deal_reason (free-text explanation)
        │
        ▼
[Stage 8]  Field extraction
           → 13–16 structured fields per deal, depending on investment_type
           Stored in deal_fields table (delete + reinsert atomically)
```

All users are processed in parallel (up to 5 threads). Each user gets an isolated DB session. Vectorization runs serially per user (1 deal at a time) to avoid throttling the Azure Functions backend.

---

## Stage-by-Stage Breakdown

### Stage 1 — Drive Discovery

**Module:** `drive_ingestion.py` → `get_unprocessed_files()`

Recursively lists all files in the user's configured Drive folder. Uses two bulk DB queries (all known `file_id`s + all known MD5 checksums) to determine which files are new — no per-file DB lookups.

**A file is skipped at this stage if:**
- Its `file_id` is already in the `documents` table for this user (regardless of status — even failed or skipped docs are tracked so they are never re-downloaded)
- Its MD5 checksum matches an already-processed file (catches renamed copies)

The root folder name is stripped from `folder_path` so it never gets mistaken for a deal name. E.g. if the root is `"Deals"`, a file at `"Deals/Acme/Q1/deck.pdf"` gets `folder_path = "Acme/Q1"`.

---

### Stage 2 — Download & Text Extraction

**Module:** `drive_ingestion.py` → `fetch_file_content()`, `parser.py` → `extract_text()`

Downloads all new files in parallel (20 threads). OAuth credentials are pre-fetched once and reused across all threads — no per-file token refresh.

Text extraction by format:
| Format | Library |
|--------|---------|
| `.pdf` | pdfminer.six |
| `.pptx` | python-pptx |
| `.docx` | python-docx |
| Other | Returns empty string |

**Password-protected files:** If text extraction raises `PasswordProtectedError`, the file is flagged. It proceeds to Stage 4 as a tombstone (`doc_type = "password_protected"`) and never reaches LLM classification or vectorization.

**Download failures:** If the Drive API returns an error after 4 attempts (0s, 2s, 5s, 10s backoff), the file is skipped entirely for this run. It will be retried on the next run because no DB row is written.

---

### Stage 3 — Batch LLM Classification

**Module:** `batch_analyzer.py` → `analyze_batch()`

Groups documents into chunks of `LLM_CHUNK_SIZE` (default: 30) and calls OpenAI in parallel (up to 10 concurrent calls). Each call returns a JSON array with one result per document.

Each result contains:
| Field | Description |
|-------|-------------|
| `doc_type` | `pitch_deck` / `investment_memo` / `prescreening_report` / `meeting_minutes` / `other` |
| `deal_name` | Company or fund name (max 3 words), or null |
| `doc_date` | Document date as YYYY-MM-DD, or null |
| `summary` | Two-sentence description |
| `is_client` | `true` if this is a post-investment / portfolio monitoring file |

Only the first `LLM_TEXT_LIMIT` characters (default: 1500) of each document's text are sent to the LLM. The folder path is also sent as a context hint.

**If OPENAI_API_KEY is not set:** All documents fall back to heuristic defaults (`doc_type = "pitch_deck"`, no deal name, no summary). The pipeline still runs — vectorization and field extraction still work.

**If a chunk fails after 3 retries:** Those documents also fall back to heuristics. The run continues.

---

### Stage 4 — Persist & Deal Resolution

**Module:** `worker.py` → `process_user()`, `deal_resolver.py`

For each document in the batch, a `Document` row is created in `status = "pending"`, then updated after classification. All existing deals for the user are pre-fetched once and reused throughout the batch.

**Deal resolution priority (highest → lowest):**
1. LLM `deal_name` from document content
2. First non-generic folder segment from `folder_path` (fallback used when LLM returns null)
3. None — document stored without a deal (`deal_id = NULL`)

Deal lookup order within `get_or_create_deal`:
1. Exact `name_key` match in the pre-fetched list
2. Fuzzy match via `rapidfuzz.token_set_ratio` ≥ 85 against all existing deals
3. Create a new Deal row (appended to the pre-fetched list so subsequent lookups see it)

See [Deal Resolution Logic](#deal-resolution-logic) for full details.

**Special handling per document type at persist time:**

| Condition | Action |
|-----------|--------|
| `password_protected = True` | `doc_type = "password_protected"`, `status = "skipped"`. Deal inferred from first folder segment only. |
| `is_client = True` | `doc_type = "client"`, `status = "skipped"`. No deal assigned. |
| `doc_type = "other"` | `doc_type = "other"`, `status = "skipped"`. No deal assigned. |
| Normal | `status = "processed"`, deal assigned if resolvable. |

All skipped tombstones are permanent — they prevent re-download on future runs.

---

### Stage 5 — Version Management

**Module:** `worker.py` → `_bulk_mark_superseded()`

Runs once after all batches are persisted. Groups newly processed documents by `(user_id, doc_type, deal_id)` for deal-scoped docs, and by `(user_id, doc_type, folder_path)` for dealless docs. For each group, issues one `UPDATE` statement to mark all existing older documents of the same type as `version_status = "superseded"`.

Only documents with `doc_created_date` set participate. Documents without a date are never superseded and never supersede anything.

A document is marked `superseded` when:
- It has the same `(user_id, doc_type, deal_id)` or `(user_id, doc_type, folder_path)` as a newer document
- Its `doc_created_date` is strictly earlier than the newest in the group
- Its current `version_status` is `"current"`

Superseded documents remain in the database and are surfaced in the UI as the "Archive" section of a deal.

---

### Stage 5.5 — Meeting-Minutes Retirement

**Module:** `worker.py` → inline after `_bulk_mark_superseded()`

After version management, the worker checks all newly processed deals. If a deal's only classified documents are `meeting_minutes` (no `pitch_deck`, `investment_memo`, or `prescreening_report`), those documents are relabelled `doc_type = "client"`, `status = "skipped"`.

This prevents governance and IC session records from creating spurious pipeline deals. A single `UPDATE` statement covers all affected deals at once.

---

### Stage 6 — Vectorization Pipeline

**Module:** `vectorizer.py` → `ingest_and_analyze_deal()`

Runs for each deal that has at least one unvectorized document (i.e. `vectorizer_doc_id IS NULL`). Only the **latest document per type** (from `get_latest_documents_per_type`) is sent — not every historical version.

The sub-pipeline has 7 internal stages:

| Sub-stage | Operation |
|-----------|-----------|
| 1 | `POST /v1/api/ingestions` — create job, get SAS upload URLs |
| 2 | `PUT <SAS_URL>` — upload file bytes (4 parallel threads per deal, 3 retries each) |
| 3 | `POST /v1/api/jobs/{jobId}/confirm-upload` — trigger orchestration |
| 4 | Poll `GET /v1/api/jobs/{jobId}` with exponential backoff (5s → 60s, ×1.5, 25-min cap) |
| 5 | Persist `vectorizer_doc_id` on each `Document` row that succeeded |
| 6 | `POST /api/Analytical` — classify deal (see Stage 7) |
| 7 | `POST /api/ExtractFields` — extract structured fields (see Stage 8) |

After Stage 5, each successfully vectorized document gets `status = "vectorized"`. Documents that failed (no `vectorizer_doc_id` returned) remain `status = "processed"` and are retried on the next run.

**If `VECTORIZER_INGEST_URL` is not set:** The entire vectorization step is skipped. Documents stay at `status = "processed"`.

Pitch decks are excluded from the ExtractFields call (sub-stage 7) because they tend to reduce extraction accuracy.

---

### Stage 7 — Analytical Endpoint

**Module:** `vectorizer.py` → `_run_analytical()`

Calls `POST /api/Analytical` with all successfully vectorized doc IDs for the deal. Returns:

| Field | Values |
|-------|--------|
| `investment_type` | `Fund` / `Direct` / `Co-Investment` |
| `deal_status` | `ACCEPTED` / `REJECTED` / `REVIEWING` / `ON_HOLD` |
| `deal_reason` | Free-text explanation |

These are persisted on the `Deal` row. `investment_type` determines which field set is used in Stage 8.

---

### Stage 8 — Field Extraction

**Module:** `field_extractor.py` → `extract_deal_fields()`, `field_definitions.py`

Calls `POST /api/ExtractFields` with field definitions tailored to the deal's `investment_type`. Field sets:

| Investment Type | Field Count | Sample Fields |
|----------------|-------------|---------------|
| `Fund` | 13 | Asset Class, Asset Manager, Fund Name, Fund Size, Vintage Year, Target Return, … |
| `Direct` | 15 | Asset Class, Company Name, Sector, Stage, Round Size, Pre-Money Valuation, Lead Investor, … |
| `Co-Investment` | 16 | All Direct fields + Lead Sponsor, Co-Investment Size |

The existing `deal_fields` rows for the deal are deleted and replaced atomically in a single transaction on every call, so the data always reflects the latest document versions.

Fields with no extractable value are stored with `value = NULL`. Fields where the API returned an error are logged at WARNING level and stored as NULL.

---

## Document Statuses

| `status` | Meaning |
|----------|---------|
| `pending` | Row created, text extraction / LLM classification in progress |
| `processed` | Classified and persisted; not yet sent to vectorizer |
| `vectorized` | Successfully ingested by the external vectorizer pipeline |
| `skipped` | Intentionally excluded: password-protected, client/portfolio, or "other" type |
| `failed` | An unexpected error occurred during processing; will not be retried |

> **Note:** `failed` documents retain their `file_id` in the DB, so they are not re-downloaded. Fix the underlying issue, then delete the row to re-trigger processing.

---

## What Gets Skipped

These documents enter the DB as permanent tombstones but go no further in the pipeline:

| Reason | `doc_type` | `status` | When it happens |
|--------|-----------|----------|-----------------|
| File already known | — | — | Drive discovery (Stage 1) — not even downloaded |
| Duplicate content (same MD5) | — | — | Drive discovery (Stage 1) — not even downloaded |
| Download failed (4 attempts) | — | — | Stage 2 — no DB row written; retried next run |
| Text extraction failed | — | — | Stage 2 — no DB row written; retried next run |
| Password-protected | `password_protected` | `skipped` | Stage 4 — tombstone written |
| LLM flagged as `is_client = True` | `client` | `skipped` | Stage 4 — tombstone written |
| LLM classified as `other` | `other` | `skipped` | Stage 4 — tombstone written |
| Meeting-minutes-only deal | `client` | `skipped` | Stage 5.5 — retroactively relabelled |

Tombstone rows are visible in the DB but excluded from all API responses.

---

## What Is Hidden from the UI

The FastAPI routes (`document_routes.py`) apply additional filters on top of the DB statuses. The following are never returned by any API endpoint:

| Hidden because… | Details |
|-----------------|---------|
| `status NOT IN ('processed', 'vectorized', 'skipped')` | `pending` and `failed` docs don't appear anywhere |
| `doc_type IN ('client', 'other', 'password_protected')` | Excluded from deal document slots and archive listings |
| Deal went through full pipeline but `investment_type IS NULL` | Deal is hidden from `/deals` and `/deals/{id}` — vectorizer couldn't classify it |
| Deal's only current docs are `meeting_minutes` | `_is_minutes_only()` check — deal hidden from all endpoints |

**Password-protected files** are the exception: they appear on the dedicated `/documents/locked` endpoint (and nested inside each deal's `locked_files` array), but nowhere else.

**Superseded documents** (`version_status = "superseded"`) are returned as the `archived` array inside each deal response, not in the main document slots. They are never sent to the vectorizer.

---

## Deal Resolution Logic

**Module:** `deal_resolver.py`

Deal names go through three normalisation steps before any comparison:
1. Strip legal suffixes (Inc, Ltd, LLC, Corp, Holdings, Ventures, Capital, Partners, Fund, …)
2. Lowercase + remove all non-alphanumeric characters → `name_key`
3. Title-case the result → `name` (display label)

Examples: `"Acme Corp."` → key `"acme"`, name `"Acme"` · `"BETA HEALTH LLC"` → key `"betahealth"`, name `"Beta Health"`

**Lookup order:**
1. **Exact key match** in pre-fetched deal list — O(1), no extra query
2. **Fuzzy match** via `rapidfuzz.token_set_ratio` ≥ 85 across all existing deals — handles "Acme" vs "Acme Robotics"
3. **Create new deal** — appended to the pre-fetched list so the next document in the same batch sees it immediately

**Folder path signal** (`extract_deal_from_folder_path`): Walks folder segments left-to-right, returns the first non-generic segment. Generic segments include: `docs`, `archive`, `misc`, `portfolio`, `pipeline`, `deals`, `q1`–`q4`, years 2020–2026, and similar.

If both an LLM deal name and a folder path signal exist, the LLM name takes priority.

---

## Version Management Logic

**Module:** `worker.py` → `_bulk_mark_superseded()`

Version management runs once after all batches for a user are persisted, so docs ingested in different batches in the same run are compared correctly.

**Pass A — deal-scoped** (docs with a `deal_id`):
- Groups by `(user_id, doc_type, deal_id)`
- In each group, the doc with the latest `doc_created_date` is the "current" version
- All others that are currently `version_status = "current"` and have an older `doc_created_date` are updated to `"superseded"` in a single `UPDATE` statement

**Pass B — folder-scoped** (docs without a `deal_id` but with a `folder_path`):
- Groups by `(user_id, doc_type, folder_path)`
- Same logic as Pass A

Docs without `doc_created_date` are excluded from both passes — they neither supersede nor get superseded.

---

## Module Reference

| File | Responsibility |
|------|---------------|
| `worker.py` | Orchestrator — user loop, batch loop, stages 4–5.5, vectorize dispatch |
| `drive_ingestion.py` | Drive API: file discovery, download, checksum, credential management |
| `parser.py` | Text extraction: PDF, PPTX, DOCX; raises `PasswordProtectedError` |
| `batch_analyzer.py` | Batch LLM classification via OpenAI (chunked, parallel) |
| `deal_resolver.py` | Deal name normalisation, fuzzy matching, get-or-create |
| `summarizer.py` | Single-doc LLM summary (fallback path, rarely used) |
| `vectorizer.py` | 7-stage Invitus AI Insights pipeline per deal |
| `field_extractor.py` | ExtractFields API call + deal_fields persistence |
| `field_definitions.py` | Field definitions for Fund / Direct / Co-Investment types |

---

## Config Tuning

All worker tunables live in `app/config.py` and can be overridden via `.env`:

| Variable | Default | Effect |
|----------|---------|--------|
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for classification and summarization |
| `LLM_CHUNK_SIZE` | `30` | Documents per OpenAI API call |
| `LLM_TEXT_LIMIT` | `1500` | Characters of text sent per document to the LLM |
| `INGEST_BATCH_SIZE` | `500` | Files processed per download → LLM → persist cycle (caps peak RAM) |

---

## Logs

Each run writes a timestamped log file to `worker/logs/worker_YYYY-MM-DD_HH-MM-SS.log` and also streams to stdout.

Key log messages to watch:

| Message | Meaning |
|---------|---------|
| `No new files for user N` | Nothing to do — Drive folder unchanged |
| `Skipping already-processed file` | File known by ID — normal |
| `Skipping duplicate content` | Same bytes as an existing doc — normal |
| `'X' is password-protected` | File flagged, tombstone written |
| `Skipped 'X' — client/portfolio file` | LLM flagged `is_client = True` |
| `Skipped 'X' — unrelated document` | LLM returned `doc_type = "other"` |
| `Fuzzy match: 'X' → 'Y' (score=N)` | Deal name normalised to existing deal |
| `Created new deal: 'X'` | New deal record inserted |
| `Bulk supersede: marked N document(s)` | Version management results |
| `retired N meeting-minutes-only deal(s)` | Stage 5.5 retirement |
| `VECTORIZER_INGEST_URL not configured` | Vectorization skipped for this user |
| `Deal N vectorization thread raised` | Vectorizer error — deal will retry next run |
| `doc N has no vectorizer_doc_id — leaving status='processed'` | Partial vectorizer failure — auto-retried |
