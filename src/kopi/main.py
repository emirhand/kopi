"""FastAPI application factory and CLI entry point for Kopi."""

from __future__ import annotations

import logging
import os
import socket
import sys
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from kopi.api import admin, copy, hardware, id_scan, pairing, scan, usb_print
from kopi.auth.dependencies import require_paired_client
from kopi.auth.pairing import get_pairing_provider
from kopi.config import get_settings_path, load_settings


def setup_logging() -> None:
    """Configure root logging for the Kopi service."""
    level_name = os.environ.get("KOPI_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _resolve_frontend_dist() -> Path:
    env_dist = os.environ.get("KOPI_FRONTEND_DIST", "").strip()
    if env_dist:
        return Path(env_dist)
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _resolve_cors_origins() -> list[str]:
    """Return allowed CORS origins, defaulting to the station's own origins.

    Note: Both the built SPA (served by FastAPI) and the Vite dev server (which
    proxies `/api` to the backend) make same-origin requests, so cross-origin
    access is not needed unless explicitly configured via `CORS_ORIGINS`.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        origins = [origin.strip() for origin in raw.split(",") if origin.strip() and origin.strip() != "*"]
        if origins:
            return origins
    hostname = socket.gethostname()
    port = int(os.environ.get("PORT", "8000"))
    return [
        f"http://{hostname}.local:{port}",
        f"http://{hostname}:{port}",
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
    ]


def create_app() -> FastAPI:
    """Create and configure the Kopi FastAPI application instance."""
    setup_logging()
    application = FastAPI(title="Kopi — Linux Smart Copier Appliance", version="0.1.0")

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    paired_deps = [Depends(require_paired_client)]
    application.include_router(pairing.router)
    application.include_router(hardware.router)
    application.include_router(copy.router, dependencies=paired_deps)
    application.include_router(scan.router, dependencies=paired_deps)
    application.include_router(id_scan.router, dependencies=paired_deps)
    application.include_router(usb_print.router, dependencies=paired_deps)
    application.include_router(admin.router)

    dist_dir = _resolve_frontend_dist()
    index_html = dist_dir / "index.html"
    if dist_dir.is_dir() and index_html.is_file():
        assets_dir = dist_dir / "assets"
        if assets_dir.is_dir():
            application.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="frontend-assets",
            )

        @application.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = (dist_dir / full_path).resolve()
            if (
                full_path
                and candidate.is_relative_to(dist_dir.resolve())
                and candidate.is_file()
            ):
                return FileResponse(str(candidate))
            return FileResponse(str(index_html))

    return application



app = create_app()


def _cli_status() -> None:
    settings = load_settings()
    hostname = socket.gethostname()
    print(f"Kopi Station ({hostname})")
    print(f"  Settings file : {get_settings_path()}")
    print(f"  Pairing PIN   : {settings.pairing_pin}")
    print(f"  Paired device : {settings.paired_device_label or 'Unpaired'}")
    if settings.paired_device_id:
        print(f"  Device ID     : {settings.paired_device_id} (since {settings.paired_at})")


def _cli_unpair() -> None:
    get_pairing_provider().unpair()
    print("Unpaired active tablet. Station is now ready for a new tablet to claim.")


def _cli_setup_sheet() -> None:
    settings = load_settings()
    hostname = socket.gethostname()
    port = int(os.environ.get("PORT", "8000"))
    print("========================================")
    print("       KOPI SMART COPIER STATION        ")
    print("========================================")
    print(f"Station URL : http://{hostname}.local:{port}")
    print(f"Pairing PIN : {settings.pairing_pin}")
    print("----------------------------------------")
    print("1. Connect tablet to the station Wi-Fi")
    print("2. Open the Station URL in Safari/Chrome")
    print("3. Enter the Pairing PIN above")
    print("4. Use 'Add to Home Screen' for fullscreen kiosk mode")
    print("========================================")


def run() -> None:
    """Entry point for `uv run kopi [serve|status|unpair|print-setup-sheet]`."""
    cmd = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "serve"
    if cmd == "status":
        _cli_status()
        return
    if cmd == "unpair":
        _cli_unpair()
        return
    if cmd in {"print-setup-sheet", "setup-sheet"}:
        _cli_setup_sheet()
        return

    port = int(os.environ.get("PORT", "8000"))
    reload_enabled = os.environ.get("KOPI_RELOAD", "1").strip().lower() in {"1", "true", "yes"}
    uvicorn.run("kopi.main:app", host="0.0.0.0", port=port, reload=reload_enabled)


if __name__ == "__main__":
    run()

