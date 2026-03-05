import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import settings
from .routes import auth_routes, drive_routes, document_routes, sync_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s – %(message)s",
)

logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── Body size limit ───────────────────────────────────────────────────────────
_MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


class _BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds _MAX_BODY_BYTES with HTTP 413."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            return Response("Request body too large", status_code=413)
        return await call_next(request)


app = FastAPI(
    title="Golden Ledger API",
    description="Investment Document Intelligence – Onboarding Pipeline (POC)",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(_BodySizeLimitMiddleware)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allow the Vite dev server and any configured frontend origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_routes.router)
app.include_router(drive_routes.router)
app.include_router(document_routes.router)
app.include_router(sync_routes.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
def health_check():
    """Simple liveness probe."""
    return {"status": "ok"}


# ── Catch-all browser redirect ────────────────────────────────────────────────
# When someone navigates directly to an API path in the browser (no Auth header,
# accepts HTML) redirect them to the frontend instead of returning a raw 404.
@app.api_route(
    "/{full_path:path}",
    methods=["GET"],
    include_in_schema=False,
)
async def redirect_browser_to_frontend(request: Request, full_path: str):
    accept = request.headers.get("accept", "")
    # Only redirect genuine browser navigations (text/html).
    # Programmatic API calls (accept: application/json) still get a 404.
    if "text/html" in accept:
        return RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": "Not Found"}, status_code=404)
