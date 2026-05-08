"""
Linux Smart Copier Appliance — FastAPI bridge to SANE, CUPS, USB, and msmtp.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from logging_config import setup_logging
from services import mailer, printer, scanner, usb_manager

setup_logging()
log = logging.getLogger("kopi.api")

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = Path(os.environ.get("SETTINGS_PATH", APP_ROOT / "config" / "settings.json"))

SCAN_TTL_SEC = int(os.environ.get("KOPI_SCAN_TTL_SEC", "300"))


class _ScanStore:
    """In-memory scan PDF cache with lazy TTL expiry."""

    def __init__(self, ttl_sec: int) -> None:
        self._ttl_sec = ttl_sec
        self._lock = asyncio.Lock()
        self._data: dict[str, tuple[float, bytes]] = {}

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._data.items() if exp <= now]
        for k in dead:
            del self._data[k]

    async def put(self, pdf: bytes) -> str:
        scan_id = uuid.uuid4().hex
        exp = time.monotonic() + self._ttl_sec
        async with self._lock:
            self._purge_unlocked()
            self._data[scan_id] = (exp, pdf)
        log.info("scan_cached scan_id=%s bytes=%d ttl_sec=%d", scan_id, len(pdf), self._ttl_sec)
        return scan_id

    async def pop(self, scan_id: str) -> bytes:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.pop(scan_id, None)
            if item is None:
                raise KeyError(scan_id)
            exp, pdf = item
            if exp <= time.monotonic():
                raise KeyError(scan_id)
            return pdf


SCAN_STORE = _ScanStore(SCAN_TTL_SEC)


def load_settings() -> dict:
    if not SETTINGS_PATH.is_file():
        raise FileNotFoundError(f"Missing settings file: {SETTINGS_PATH}")
    with SETTINGS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def verify_admin_password(settings: dict, password: str) -> bool:
    expected = str(settings.get("admin_password", ""))
    return bool(password) and password == expected


app = FastAPI(title="Linux Smart Copier Appliance", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanBody(BaseModel):
    duplex: bool = False


class PrintBody(BaseModel):
    scan_id: str = Field(..., min_length=8)
    duplex: bool = False


class ScanEmailBody(BaseModel):
    recipient: str = Field(..., min_length=3)


class AdminVerifyBody(BaseModel):
    password: str


class SmtpSettings(BaseModel):
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""
    tls: bool = True


class AdminSettingsUpdate(BaseModel):
    smtp: SmtpSettings
    scanner_device: str = ""
    printer_device: str = ""
    usb_roots: list[str] = Field(default_factory=list)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/hardware")
def api_hardware():
    settings = load_settings()
    roots = settings.get("usb_roots", [])
    usb_roots = [str(x).strip() for x in roots if str(x).strip()] if isinstance(roots, list) else None
    return {
        "scanners": scanner.list_scan_devices(),
        "printers": printer.list_printer_queues(),
        "usb_volumes": usb_manager.list_usb_mounts(roots=usb_roots, writable_only=False),
    }


@app.post("/api/scan")
async def api_scan(body: ScanBody):
    settings = load_settings()
    scan = await scanner.scan_pdf(
        duplex=body.duplex,
        device=str(settings.get("scanner_device", "")).strip() or None,
    )
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")
    scan_id = await SCAN_STORE.put(scan.stdout)
    return {"scan_id": scan_id, "bytes": len(scan.stdout)}


@app.post("/api/print")
async def api_print(body: PrintBody):
    settings = load_settings()
    try:
        pdf = await SCAN_STORE.pop(body.scan_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="Scan expired or not found. Please scan again.",
        ) from None

    result = await printer.print_pdf(
        pdf,
        duplex=body.duplex,
        job_name="kopi-copy",
        device=str(settings.get("printer_device", "")).strip() or None,
    )
    if not result.ok:
        await SCAN_STORE.put(pdf)
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")
    return {"ok": True, "message": "Print job submitted"}


@app.post("/api/scan/email")
async def api_scan_email(body: ScanEmailBody):
    settings = load_settings()
    scan = await scanner.scan_pdf(
        duplex=False,
        device=str(settings.get("scanner_device", "")).strip() or None,
    )
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    ok, err = mailer.send_pdf_email(
        scan.stdout,
        to_addr=body.recipient.strip(),
        subject=f"Scan {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        smtp=settings.get("smtp", {}),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "message": "Scan emailed"}


@app.post("/api/scan/usb")
async def api_scan_usb():
    settings = load_settings()
    try:
        roots = settings.get("usb_roots", [])
        mount = usb_manager.require_usb_path(
            roots=[str(x).strip() for x in roots if str(x).strip()] if isinstance(roots, list) else None
        )
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="USB Not Found")

    scan = await scanner.scan_pdf(
        duplex=False,
        device=str(settings.get("scanner_device", "")).strip() or None,
    )
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    name = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.pdf"
    dest = mount / name
    try:
        dest.write_bytes(scan.stdout)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Could not write to USB: {e}") from e

    return {"ok": True, "message": f"Saved to {dest}"}


@app.post("/api/admin/verify")
def api_admin_verify(body: AdminVerifyBody):
    settings = load_settings()
    valid = verify_admin_password(settings, body.password)
    return {"valid": valid}


@app.get("/api/admin/settings")
def api_admin_settings(x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")):
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    return {
        "smtp": settings.get("smtp", {}),
        "scanner_device": settings.get("scanner_device", ""),
        "printer_device": settings.get("printer_device", ""),
        "usb_roots": settings.get("usb_roots", []),
        "hardware_options": {
            "scanners": scanner.list_scan_devices(),
            "printers": printer.list_printer_queues(),
        },
    }


@app.put("/api/admin/settings")
def api_admin_settings_put(
    body: AdminSettingsUpdate,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")

    settings["smtp"] = body.smtp.model_dump()
    settings["scanner_device"] = body.scanner_device.strip()
    settings["printer_device"] = body.printer_device.strip()
    settings["usb_roots"] = [x.strip() for x in body.usb_roots if x.strip()]
    save_settings(settings)
    return {"ok": True, "message": "Settings saved"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
