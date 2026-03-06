# Golden Ledger

**Investment Document Intelligence Platform** — automatically ingests, classifies, and analyses investment documents from Google Drive, surfaces the latest version of each document type per deal, and extracts structured deal fields using an external RAG pipeline.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Document Processing Pipeline](#document-processing-pipeline)
- [Why This Is Production-Grade](#why-this-is-production-grade)
- [API Endpoints](#api-endpoints)
- [Document Types](#document-types)
- [Deal Fields](#deal-fields)
- [Backend Setup](#backend-setup)
- [Frontend Setup](#frontend-setup)
- [Running the Worker](#running-the-worker)
- [Database Migrations](#database-migrations)
- [Deployment (Railway)](#deployment-railway)

---

## Overview

Golden Ledger connects to a user's Google Drive, runs a nightly worker that scans for new investment documents, and processes them through a multi-stage AI pipeline:

1. **Ingestion** — detects new files by Drive file ID (never reprocesses), downloads in parallel
2. **Classification** — batches up to 30 docs per `gpt-4o-mini` call to classify type, extract deal name, date, and summary
3. **Deal resolution** — fuzzy-matches document folder paths to deal records using `rapidfuzz`
4. **Version management** — automatically marks older versions of the same document type per deal as superseded
5. **Vectorization** — sends the latest document per type to an external ingestion API (Invitus AI Insights) for RAG indexing
6. **AI analysis** — calls the Analytical endpoint to determine `investment_type`, `deal_status`, and `deal_reason`
7. **Field extraction** — calls the ExtractFields endpoint to populate 13–16 structured deal fields (tailored per investment type: Fund, Direct, or Co-Investment)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Google Drive                            │
│              (user's investment document folder)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Drive API v3
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Nightly Worker                             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  Drive Ingest│  │ Batch LLM    │  │   Deal Resolver      │  │
│  │  (parallel   │→ │ Classifier   │→ │   (fuzzy match +     │  │
│  │   download)  │  │ gpt-4o-mini  │  │    folder heuristic) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                ↓                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   PostgreSQL                            │    │
│  │  users · documents · deals · deal_fields                │    │
│  └─────────────────────────────────────────────────────────┘    │
│                            ↓                                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Vectorizer Pipeline (per deal)              │   │
│  │  Stage 1: Create ingestion job                           │   │
│  │  Stage 2: Upload docs to SAS URLs (parallel)             │   │
│  │  Stage 3: Confirm upload                                 │   │
│  │  Stage 4: Poll until COMPLETED (25 min cap, backoff)     │   │
│  │  Stage 5: Persist vectorizer_doc_id                      │   │
│  │  Stage 6: Analytical → investment_type + deal_outcome    │   │
│  │  Stage 7: ExtractFields → 13–16 structured deal fields   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                             │
│         Rate-limited REST API · JWT auth · CORS                 │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   React + Vite Frontend                         │
│       Deal grid · Document slots · Structured field display     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
golden-ledger/
├── frontend/                    # React + Vite + Tailwind dashboard
│   ├── src/
│   │   ├── components/          # DocumentCard, Hero, Navbar, etc.
│   │   ├── pages/               # Index, DealDetail, NotFound
│   │   └── lib/api.ts           # Typed API client
│   └── package.json
└── server/
    ├── app/
    │   ├── config.py            # Pydantic settings with startup validation
    │   ├── database.py          # SQLAlchemy engine (pool_recycle, TCP keepalives)
    │   ├── main.py              # FastAPI app, CORS, rate limiting, body size guard
    │   ├── models/
    │   │   ├── user.py          # User (OAuth tokens encrypted at rest)
    │   │   ├── document.py      # Document (versioning, vectorizer_doc_id)
    │   │   ├── deal.py          # Deal (investment_type, deal_status, deal_reason)
    │   │   └── deal_field.py    # DealField (structured extracted fields)
    │   ├── routes/
    │   │   ├── auth_routes.py   # Google OAuth 2.0 flow + JWT issuance
    │   │   ├── document_routes.py # Deal list, deal detail, document slots
    │   │   ├── drive_routes.py  # Drive folder configuration
    │   │   └── sync_routes.py   # Sync status and document counts
    │   ├── schemas/             # Pydantic request/response models
    │   ├── services/            # document_service, drive_service, google_auth_service
    │   └── utils/
    │       ├── auth.py          # JWT bearer dependency
    │       └── encryption.py    # Fernet encryption for OAuth tokens
    ├── worker/
    │   ├── worker.py            # Orchestrator: batched ingest → LLM → vectorize
    │   ├── drive_ingestion.py   # File discovery, download, checksum
    │   ├── parser.py            # Text extraction (pdfminer / python-pptx / python-docx)
    │   ├── batch_analyzer.py    # Batch LLM classifier (30 docs/call, 10 parallel chunks)
    │   ├── deal_resolver.py     # Fuzzy folder-path → deal name matching
    │   ├── summarizer.py        # Per-doc summary generation
    │   ├── vectorizer.py        # 7-stage Invitus AI Insights pipeline
    │   ├── field_definitions.py # Fund / Direct / Co-Investment field definitions
    │   └── field_extractor.py   # ExtractFields API integration
    ├── alembic/                 # 7 incremental migrations
    ├── setup_db.sh              # DB bootstrap (local + Railway URL support)
    └── requirements.txt
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI 0.115 + Uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.0 + Alembic |
| Auth | Google OAuth 2.0 + JWT (`python-jose`) |
| Token security | Fernet symmetric encryption (`cryptography`) |
| Document parsing | pdfminer.six, python-pptx, python-docx |
| Classification | OpenAI `gpt-4o-mini` (batch, 30 docs/call) |
| Vectorization | Invitus AI Insights (Azure Functions RAG pipeline) |
| Fuzzy matching | rapidfuzz |
| Rate limiting | slowapi |
| Frontend | React 18 + Vite + Tailwind CSS + shadcn/ui |
| Package manager | Bun |
| Deployment | Railway (backend + DB) |

---

## Document Processing Pipeline

```
Google Drive folder
        │
        ▼
  Detect new files by Drive file ID
  (already-seen files are never reprocessed)
        │
        ▼
  Download files in parallel (20 threads)
  Extract text: PDF → pdfminer · PPTX → python-pptx · DOCX → python-docx
        │
        ▼
  Batch LLM classification (gpt-4o-mini, 30 docs/call, up to 10 parallel chunks)
  → doc_type, deal_name, doc_date, summary, is_client flag
        │
        ▼
  Fuzzy deal resolution (rapidfuzz folder-path matching)
  → link document to existing deal or create new deal record
        │
        ▼
  Persist to PostgreSQL
  Mark older versions of same (deal, doc_type) as superseded
        │
        ▼
  Step 4.5: retire meeting-minutes-only deals from pipeline
        │
        ▼
  Vectorizer pipeline — 2 deals in parallel, each runs 7 stages:
  1. POST /v1/api/ingestions          → job_id + SAS upload URLs
  2. PUT  <SAS_URL>                   → upload file bytes (4 threads/deal, 3 retries)
  3. POST /v1/api/jobs/{id}/confirm-upload
  4. GET  /v1/api/jobs/{id}           → poll with exponential backoff (5s→60s, 25 min cap)
  5. Persist vectorizer_doc_id on COMPLETED docs only
  6. POST /api/Analytical             → investment_type + deal_outcome (ACCEPTED/REJECTED)
  7. POST /api/ExtractFields          → 13–16 structured fields by investment type
        │
        ▼
  Deal fields stored in deal_fields table
  Surfaced in frontend DealDetail view
```

---

## Why This Is Production-Grade

### Reliability

- **Idempotent ingestion** — files are keyed by Drive file ID with a SHA-256 checksum. The worker can be rerun at any time without creating duplicates.
- **Automatic retry on failure** — docs that fail vectorization (no `vectorizer_doc_id` set) are automatically included in the next worker run. The worker never marks a doc as `vectorized` unless the external pipeline confirmed it.
- **HTTP retries with backoff** — all outbound HTTP calls (SAS uploads, ingestion API, Analytical, ExtractFields) retry up to 3 times with 5 s / 15 s / 30 s backoff before failing.
- **Vectorizer polling resilience** — Stage 4 uses exponential backoff (5 s → 60 s cap, ×1.5 multiplier) for up to 25 minutes and tolerates transient GET errors without aborting the job.
- **DB connection hardening** — `pool_recycle=300`, TCP keepalives (`keepalives_idle=30`), and a `SELECT 1` ping before every persist step with `engine.dispose()` on failure — prevents Railway's SSL proxy from silently dropping idle connections mid-run.
- **Single-instance lock** — `fcntl.LOCK_EX` prevents two worker processes from running simultaneously and corrupting state.

### Security

- **OAuth tokens encrypted at rest** — Google refresh tokens are encrypted with Fernet before being stored in PostgreSQL. The `ENCRYPTION_KEY` is validated at startup.
- **JWT authentication** — all API endpoints are protected by short-lived JWTs. The `SECRET_KEY` is validated to be ≥ 32 characters at startup via Pydantic.
- **Rate limiting** — `slowapi` enforces 200 req/min globally and 60 req/min on document endpoints, protecting against abuse.
- **Request body size cap** — `_BodySizeLimitMiddleware` rejects payloads over 10 MB with HTTP 413, preventing memory exhaustion attacks.
- **No secrets in code** — all credentials are loaded from `.env` via `pydantic-settings`. The config class validates `ENCRYPTION_KEY` is a valid Fernet key at import time.

### Scalability

- **Memory-bounded batching** — `INGEST_BATCH=500` caps peak RAM regardless of Drive folder size. A 10,000-file folder runs in 20 iterations, not one monolithic load.
- **Parallel downloads** — 20 concurrent Drive API threads per batch, saturating typical network bandwidth.
- **Parallel LLM classification** — 30 docs/call × up to 10 concurrent API calls = 300 docs classified simultaneously. 10,000 files complete in ~344 total API calls.
- **Per-deal isolation** — each deal runs its vectorizer pipeline in its own DB session (thread-safe, no shared SQLAlchemy state). 2 deals run concurrently — tuned to avoid throttling dev-tier Azure Functions.
- **Per-user isolation** — up to 5 users processed in parallel, each in their own DB session.

### Data Integrity

- **Incremental migrations** — 7 Alembic migrations in strict sequence (`0001`→`0007`). Schema changes are version-controlled and reproducible.
- **Unique constraints** — `(file_id)` on documents prevents duplicate ingestion; `(deal_id, field_name)` on deal_fields ensures one value per field per deal.
- **Version management** — older documents of the same `(user_id, doc_type, deal_id)` are automatically marked `superseded` when a newer version is ingested, so queries always return the latest.
- **Meeting-minutes guard** — deals whose only documents are meeting minutes are retired from the pipeline (not surfaced as deals), preventing false positives from governance documents.
- **Investment-type-specific fields** — Fund (13 fields), Direct (15 fields), and Co-Investment (16 fields) each have their own field definition set. Fields are always deleted and replaced atomically in a single transaction, preventing stale data.

### Observability

- **Timestamped log files** — every worker run writes to `worker/logs/worker_YYYY-MM-DD_HH-MM-SS.log` and stdout simultaneously.
- **Structured log messages** — every stage logs deal ID, document name, external doc IDs, status, and failure reasons. Failed field extractions log the specific field name and error.
- **Pipeline progress counters** — the worker logs total files, batch progress, docs already vectorized, dealless docs skipped, and deals retired at each step.

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/auth/login` | — | Redirect to Google OAuth consent screen |
| `GET` | `/auth/callback` | — | OAuth callback, issues JWT |
| `GET` | `/auth/me` | JWT | Current user profile |
| `POST` | `/drive/folder` | JWT | Configure root Drive folder path |
| `GET` | `/sync/status` | JWT | Sync state, document counts, last run time |
| `GET` | `/documents/deals` | JWT | All deals with latest doc slots and deal fields |
| `GET` | `/documents/deals/{id}` | JWT | Single deal with all docs and structured fields |
| `GET` | `/documents/latest` | JWT | Latest document per type (legacy flat list) |
| `GET` | `/health` | — | Liveness probe |

All authenticated endpoints require `Authorization: Bearer <token>`.

---

## Document Types

| Type | Description |
|------|-------------|
| `pitch_deck` | Investor presentation or company overview |
| `investment_memo` | Due diligence report, deal memo, term sheet analysis |
| `prescreening_report` | Initial assessment or first-look screening |
| `meeting_minutes` | Formal IC/Investment Committee session minutes only |
| `other` | Call notes, board updates, LP letters, operational docs |

> **Note:** `meeting_minutes` requires strong IC signals (motion, quorum, resolution, vote). Call notes and catch-up notes are classified as `other`.

---

## Deal Fields

Structured fields extracted from vectorized documents via the ExtractFields API. Field sets vary by investment type:

| Investment Type | Field Count | Sample Fields |
|----------------|-------------|---------------|
| Fund | 13 | `fundName`, `assetManager`, `fundSize`, `vintageYear`, `targetReturn` |
| Direct | 15 | `companyName`, `sector`, `stage`, `roundSize`, `preMoneyValuation`, `leadInvestor` |
| Co-Investment | 16 | All Direct fields + `leadSponsor`, `coInvestmentSize` |

Fields are grouped into sections (`Opportunity overview`, `Key terms`) and displayed in the DealDetail view with formatted values.

---

## Backend Setup

### 1. Clone and create environment

```bash
git clone https://github.com/sinanshamsudheen/golden-ledger.git
cd golden-ledger
conda create -n lokam python=3.11
conda activate lokam
```

### 2. Install dependencies

```bash
cd server
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp server/.env.example server/.env
```

Edit `server/.env`:

```env
# PostgreSQL
DATABASE_URL=postgresql://postgres:password@localhost:5432/golden_ledger

# Google OAuth (https://console.cloud.google.com/apis/credentials)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# OpenAI
OPENAI_API_KEY=sk-...

# Security — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<64-char hex string>

# Fernet key — generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=<Fernet base64 key>

FRONTEND_URL=http://localhost:5173

# Vectorizer (optional — worker skips if not set)
VECTORIZER_INGEST_URL=https://...
VECTORIZER_ANALYTICAL_URL=https://...
VECTORIZER_FUNCTION_KEY=...
RAG_FUNCTION_KEY=...
VECTORIZER_TENANT_ID=...
```

### 4. Set up the database

```bash
cd server
./setup_db.sh          # creates DB, runs all migrations
```

Or manually:

```bash
createdb golden_ledger
alembic upgrade head
```

### 5. Start the API server

```bash
# from server/
uvicorn app.main:app --reload --port 8000
```

API available at `http://localhost:8000`  
Interactive docs at `http://localhost:8000/docs`

---

## Frontend Setup

```bash
cd frontend
bun install
bun dev
```

Frontend runs at `http://localhost:5173` and proxies API requests to `http://localhost:8000` via Vite config.

---

## Running the Worker

```bash
# from server/
conda activate lokam
python worker/worker.py

# Vectorizer-only mode (skip Drive sync + LLM, just re-run vectorization)
python worker/worker.py --vectorize-only
```

**Schedule nightly at 2 AM via cron:**

```cron
0 2 * * * conda run -n lokam python /path/to/server/worker/worker.py >> /var/log/golden_ledger_worker.log 2>&1
```

Each run writes a timestamped log to `server/worker/logs/`.

---

## Database Migrations

| Migration | Description |
|-----------|-------------|
| `0001` | Initial schema: users, documents |
| `0002` | Add version management + deal_id to documents |
| `0003` | Add deals table |
| `0004` | Performance indexes for `get_latest_documents_per_type` |
| `0005` | Add vectorizer fields to documents and deals |
| `0006` | Add company_name to deals |
| `0007` | Add deal_fields table with indexes |

```bash
alembic upgrade head      # apply all migrations
alembic current           # check current revision
alembic downgrade -1      # roll back one step
```

---

## Deployment (Railway)

The backend is deployed to Railway with the following environment variables set in the Railway dashboard (same keys as `.env`). The `DATABASE_URL` is provided automatically by Railway's PostgreSQL plugin.

**Run migrations on Railway:**

```bash
DATABASE_URL=<railway_url> ./setup_db.sh
```

**Worker scheduling:** trigger `python worker/worker.py` via Railway's cron job feature or an external scheduler pointed at the deployed service.

> Google OAuth test users must be added at [Google Cloud Console → APIs & Services → OAuth consent screen → Test users](https://console.cloud.google.com/apis/credentials/consent) until the app passes Google's verification review.
