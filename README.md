# Golden Ledger

Investment Document Intelligence — Onboarding Pipeline (POC)

Golden Ledger connects to a user's Google Drive, automatically ingests investment documents overnight, classifies and summarises them using AI, and surfaces the latest document per category in a dashboard.

---

## Project Structure

```
golden-ledger/
├── frontend/          # React + Vite dashboard (pre-built)
└── server/
    ├── app/           # FastAPI application
    │   ├── models/    # SQLAlchemy ORM models
    │   ├── schemas/   # Pydantic request/response schemas
    │   ├── routes/    # API route handlers
    │   ├── services/  # Business logic (Drive, auth, documents)
    │   └── utils/     # JWT auth helpers
    ├── worker/        # Nightly processing pipeline
    │   ├── worker.py          # Entry point
    │   ├── drive_ingestion.py # Drive file detection & download
    │   ├── parser.py          # Azure Document Intelligence extraction
    │   ├── classifier.py      # Document type classification
    │   └── summarizer.py      # LLM description generation
    ├── alembic/       # Database migrations
    ├── alembic.ini
    ├── requirements.txt
    ├── .env.example
    └── how-to-setup.md  # Azure Document Intelligence setup guide
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Database | PostgreSQL + SQLAlchemy + Alembic |
| Auth | Google OAuth 2.0 + JWT |
| Document extraction | Azure Document Intelligence (`prebuilt-read`) |
| Classification & summarisation | OpenAI `gpt-4o-mini` |
| Drive integration | Google Drive API v3 |
| Frontend | React + Vite + Tailwind |

---

## Prerequisites

- Python 3.11+
- PostgreSQL running locally (or a connection string to a hosted instance)
- Google Cloud project with OAuth 2.0 credentials ([guide](https://console.cloud.google.com/apis/credentials))
- Azure Document Intelligence resource ([setup guide](server/how-to-setup.md))
- OpenAI API key (optional — falls back to heuristics if absent)

---

## Backend Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/sinanshamsudheen/golden-ledger.git
cd golden-ledger
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
cd server
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `server/.env` and fill in all values:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/golden_ledger
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=...
OPENAI_API_KEY=sk-...
SECRET_KEY=<random 32-byte hex string>
FRONTEND_URL=http://localhost:5173
```

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Create the database

```bash
createdb golden_ledger
```

### 5. Run migrations

```bash
# from server/
alembic upgrade head
```

### 6. Start the API server

```bash
# from project root
uvicorn server.app.main:app --reload
```

API is now available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

---

## Running the Worker

The worker processes all user Drive folders and stores classified documents in the database.

**Run manually:**

```bash
python server/worker/worker.py
```

**Schedule nightly at 2 AM via cron:**

```cron
0 2 * * * /path/to/.venv/bin/python /path/to/server/worker/worker.py
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/auth/login` | Redirect to Google OAuth |
| `GET` | `/auth/callback` | OAuth callback, issues JWT |
| `GET` | `/auth/me` | Current user profile |
| `POST` | `/drive/folder` | Configure Drive folder path |
| `GET` | `/sync/status` | Sync state and document counts |
| `GET` | `/documents/latest` | Latest document per type |
| `GET` | `/health` | Liveness probe |

All endpoints except `/auth/login`, `/auth/callback`, and `/health` require a `Bearer <token>` header.

---

## Document Types

| Type | Description |
|------|-------------|
| `pitch_deck` | Investor presentations |
| `investment_report` | Fund / portfolio performance reports |
| `deal_memo` | Deal analysis and term sheets |
| `financial_report` | P&L, balance sheets, cash flow statements |
| `other` | Everything else |

---

## Document Processing Pipeline

```
Google Drive folder
        │
        ▼
  Detect new files (by Drive file ID)
        │
        ▼
  Download via Drive API
        │
        ▼
  Extract text (Azure Document Intelligence)
        │
        ▼
  Classify type (keyword heuristic → GPT-4o-mini fallback)
        │
        ▼
  Extract date (regex → Drive creation date fallback)
        │
        ▼
  Generate description (GPT-4o-mini → text fallback)
        │
        ▼
  Store in PostgreSQL
        │
        ▼
  Select latest document per type
        │
        ▼
  Send to vectorizer pipeline
```

---

## Frontend Setup

```bash
cd frontend
bun install
bun dev
```

Frontend runs at `http://localhost:5173` and connects to the backend at `http://localhost:8000`.

---

## Azure Document Intelligence

See [server/how-to-setup.md](server/how-to-setup.md) for a step-by-step guide to creating the Azure resource and obtaining credentials.

> If Azure credentials are not set, the worker falls back to local parsing (pdfminer / python-pptx / python-docx). Scanned PDFs will not work without Azure.
