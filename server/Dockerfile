# ── Golden Ledger Backend ─────────────────────────────────────────────────────
# Single-stage build: all deps have pre-built wheels so no compiler needed.
# Build context: server/   (set Railway "Root Directory" → server)
FROM python:3.11-slim-bookworm

# Runtime lib for psycopg2-binary (bundles libpq but still needs the shared lib on some images)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Deps layer (cached unless requirements.txt changes) ──────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ─────────────────────────────────────────────────────────
COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

# ── Non-root user ─────────────────────────────────────────────────────────────
RUN useradd -m -u 1001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["sh", "docker-entrypoint.sh"]
