#!/usr/bin/env python3
"""
start_server.py – Launch the Golden Ledger FastAPI backend.

Usage (from project root):
    conda activate lokam && python server/start_server.py

Usage (from server/):
    conda activate lokam && python start_server.py

Env vars (override defaults):
    HOST     – bind address   (default: 0.0.0.0)
    PORT     – bind port      (default: 8000)
    RELOAD   – hot-reload     (default: true in dev, false if --no-reload flag passed)
    LOG_LEVEL – uvicorn log level (default: info)
"""

import os
import sys
import argparse

# ── Ensure server/ is on sys.path so `app.*` imports resolve ─────────────────
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import uvicorn                                          # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Golden Ledger API server")
    parser.add_argument("--host",      default=os.environ.get("HOST", "0.0.0.0"),   help="Bind host")
    parser.add_argument("--port",      default=int(os.environ.get("PORT", 8000)),   type=int, help="Bind port")
    parser.add_argument("--no-reload", action="store_true",                          help="Disable hot-reload (use in production)")
    parser.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "info"), help="Uvicorn log level")
    args = parser.parse_args()

    reload = not args.no_reload

    print(
        f"\n🪙  Golden Ledger API\n"
        f"   Host      : {args.host}:{args.port}\n"
        f"   Hot-reload: {reload}\n"
        f"   Log level : {args.log_level}\n"
        f"   Docs      : http://localhost:{args.port}/docs\n"
    )

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=reload,
        reload_dirs=[SERVER_DIR] if reload else None,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
