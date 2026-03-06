from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Worker tuning ─────────────────────────────────────────────────────────
    LLM_CHUNK_SIZE: int = 30    # docs per LLM call in batch_analyzer
    LLM_TEXT_LIMIT: int = 1500  # chars of text sent per doc to LLM
    INGEST_BATCH_SIZE: int = 500  # max files per download → LLM → persist cycle

    # ── External vectorizer (Invitus AI Insights) — all optional ─────────────
    # If VECTORIZER_INGEST_URL is not set the worker skips the vectorization step.
    # Base URL for the document ingestion API  (e.g. https://ingestion.azurewebsites.net)
    VECTORIZER_INGEST_URL: Optional[str] = None
    # Base URL for the RAG / Analytical gateway (may differ from ingestion host)
    VECTORIZER_ANALYTICAL_URL: Optional[str] = None
    # Azure Functions host key for document ingestion endpoint
    VECTORIZER_FUNCTION_KEY: Optional[str] = None
    # Azure Functions host key for the RAG / Analytical endpoint (if different)
    RAG_FUNCTION_KEY: Optional[str] = None
    # Tenant identifier assigned to your organisation
    VECTORIZER_TENANT_ID: Optional[str] = None
    # Deployment region tag sent in the ingestion payload
    VECTORIZER_REGION: str = "uae"
    # Module and use-case identifiers (configure to match your Invitus setup)
    VECTORIZER_MODULE_ID: str = "invictus-deals"
    VECTORIZER_USE_CASE_ID: str = "due-diligence"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def encryption_key_must_be_valid_fernet(cls, v: str) -> str:
        try:
            from cryptography.fernet import Fernet
            Fernet(v.encode())
        except Exception:
            raise ValueError(
                "ENCRYPTION_KEY must be a valid Fernet key. "
                "Generate one with: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        return v

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
