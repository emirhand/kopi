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

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from logging_config import setup_logging
from services import mailer, printer, processor, scanner, usb_manager

setup_logging()
log = logging.getLogger("kopi.api")

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = Path(os.environ.get("SETTINGS_PATH", APP_ROOT / "config" / "settings.json"))

SCAN_TTL_SEC = int(os.environ.get("KOPI_SCAN_TTL_SEC", "300"))
ID_SCAN_TTL_SEC = int(os.environ.get("KOPI_ID_SCAN_TTL_SEC", "600"))


class _ScanStore:
    """In-memory copy artifact cache with lazy TTL expiry."""

    def __init__(self, ttl_sec: int) -> None:
        self._ttl_sec = ttl_sec
        self._lock = asyncio.Lock()
        self._data: dict[str, tuple[float, str]] = {}

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._data.items() if exp <= now]
        for k in dead:
            _exp, path = self._data.pop(k)
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    async def put_path(self, path: str) -> str:
        scan_id = uuid.uuid4().hex
        exp = time.monotonic() + self._ttl_sec
        async with self._lock:
            self._purge_unlocked()
            self._data[scan_id] = (exp, path)
        log.info("scan_cached scan_id=%s path=%s ttl_sec=%d", scan_id, path, self._ttl_sec)
        return scan_id

    async def pop_path(self, scan_id: str) -> str:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.pop(scan_id, None)
            if item is None:
                raise KeyError(scan_id)
            exp, path = item
            if exp <= time.monotonic():
                raise KeyError(scan_id)
            return path


SCAN_STORE = _ScanStore(SCAN_TTL_SEC)


class _IdScanStore:
    """Session state for two-sided ID scan → one PDF."""

    def __init__(self, ttl_sec: int) -> None:
        self._ttl_sec = ttl_sec
        self._lock = asyncio.Lock()
        self._data: dict[str, tuple[float, dict[str, str | None]]] = {}

    def _cleanup_payload(self, payload: dict[str, str | None]) -> None:
        for key in ("front", "back", "pdf"):
            p = payload.get(key)
            if p:
                try:
                    Path(str(p)).unlink(missing_ok=True)
                except OSError:
                    pass

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._data.items() if exp <= now]
        for k in dead:
            _exp, payload = self._data.pop(k)
            self._cleanup_payload(payload)

    async def create_session(self) -> str:
        sid = uuid.uuid4().hex
        async with self._lock:
            self._purge_unlocked()
            self._data[sid] = (
                time.monotonic() + self._ttl_sec,
                {"front": None, "back": None, "pdf": None},
            )
        return sid

    async def set_front(self, sid: str, path: str) -> bool:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.get(sid)
            if not item:
                return False
            exp, pl = item
            if exp <= time.monotonic():
                self._data.pop(sid, None)
                self._cleanup_payload(pl)
                return False
            old = pl.get("front")
            if old:
                try:
                    Path(str(old)).unlink(missing_ok=True)
                except OSError:
                    pass
            pl["front"] = path
            self._data[sid] = (time.monotonic() + self._ttl_sec, pl)
        return True

    async def set_back(self, sid: str, path: str) -> bool:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.get(sid)
            if not item:
                return False
            exp, pl = item
            if exp <= time.monotonic():
                self._data.pop(sid, None)
                self._cleanup_payload(pl)
                return False
            old = pl.get("back")
            if old:
                try:
                    Path(str(old)).unlink(missing_ok=True)
                except OSError:
                    pass
            pl["back"] = path
            self._data[sid] = (time.monotonic() + self._ttl_sec, pl)
        return True

    async def set_pdf(self, sid: str, path: str) -> bool:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.get(sid)
            if not item:
                return False
            exp, pl = item
            if exp <= time.monotonic():
                self._data.pop(sid, None)
                self._cleanup_payload(pl)
                return False
            old = pl.get("pdf")
            if old:
                try:
                    Path(str(old)).unlink(missing_ok=True)
                except OSError:
                    pass
            pl["pdf"] = path
            self._data[sid] = (time.monotonic() + self._ttl_sec, pl)
        return True

    async def get_payload(self, sid: str) -> dict[str, str | None] | None:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.get(sid)
            if not item:
                return None
            exp, pl = item
            if exp <= time.monotonic():
                self._data.pop(sid, None)
                self._cleanup_payload(pl)
                return None
            self._data[sid] = (time.monotonic() + self._ttl_sec, pl)
            return dict(pl)

    async def discard(self, sid: str) -> None:
        async with self._lock:
            item = self._data.pop(sid, None)
            if item:
                self._cleanup_payload(item[1])


ID_SCAN_STORE = _IdScanStore(ID_SCAN_TTL_SEC)


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
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
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
    id_scan_ocr: bool = False


class IdScanSessionBody(BaseModel):
    session_id: str = Field(..., min_length=8)


class IdScanEmailBody(BaseModel):
    session_id: str = Field(..., min_length=8)
    recipient: str = Field(..., min_length=3)


class UsbMountBody(BaseModel):
    device: str = Field(..., min_length=4, description="Block device e.g. /dev/sdb1")


class ScanUsbBody(BaseModel):
    mount_path: Optional[str] = None


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/hardware")
def api_hardware():
    return {
        "scanners": scanner.list_scan_devices(),
        "printers": printer.list_printer_queues(),
        "usb_volumes": [v.to_dict() for v in usb_manager.list_usb_volumes()],
    }


@app.get("/api/settings/public")
def api_settings_public():
    settings = load_settings()
    return {"id_scan_ocr": bool(settings.get("id_scan_ocr", False))}


@app.post("/api/usb/mount")
def api_usb_mount(body: UsbMountBody):
    vols = usb_manager.list_usb_volumes()
    vol = next((v for v in vols if v.device == body.device.strip()), None)
    if vol is None:
        raise HTTPException(
            status_code=400,
            detail="Device not found. Plug in the USB drive, then open USB storage again.",
        )
    if vol.mounted and vol.mountpoint:
        return {"ok": True, "mountpoint": vol.mountpoint, "message": f"Already mounted at {vol.mountpoint}"}
    mp, err = usb_manager.mount_usb_partition(vol.device)
    if err or not mp:
        raise HTTPException(status_code=400, detail=err or "Mount failed")
    return {"ok": True, "mountpoint": mp, "message": f"Mounted at {mp}"}


@app.post("/api/id-scan/front")
async def api_id_scan_front():
    settings = load_settings()
    dev = str(settings.get("scanner_device", "")).strip() or None
    sid = await ID_SCAN_STORE.create_session()
    res = await scanner.scan_id_side("front", device=dev)
    if not res.ok:
        await ID_SCAN_STORE.discard(sid)
        raise HTTPException(status_code=400, detail=res.user_message or "Scan failed")
    if not await ID_SCAN_STORE.set_front(sid, res.path):
        Path(res.path).unlink(missing_ok=True)
        await ID_SCAN_STORE.discard(sid)
        raise HTTPException(status_code=500, detail="Session error")
    return {"ok": True, "session_id": sid}


@app.post("/api/id-scan/back")
async def api_id_scan_back(body: IdScanSessionBody):
    settings = load_settings()
    dev = str(settings.get("scanner_device", "")).strip() or None
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    if not pl or not pl.get("front"):
        raise HTTPException(status_code=400, detail="Invalid or expired session. Scan the front again.")
    res = await scanner.scan_id_side("back", device=dev)
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.user_message or "Scan failed")
    if not await ID_SCAN_STORE.set_back(body.session_id, res.path):
        Path(res.path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Session error")
    return {"ok": True}


@app.post("/api/id-scan/compose")
async def api_id_scan_compose(body: IdScanSessionBody):
    import tempfile

    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    if not pl or not pl.get("front") or not pl.get("back"):
        raise HTTPException(status_code=400, detail="Scan both sides before composing.")
    front = Path(str(pl["front"]))
    back = Path(str(pl["back"]))
    fd, tmp = tempfile.mkstemp(prefix="kopi-id-composed-", suffix=".pdf")
    os.close(fd)
    out_pdf = Path(tmp)
    ok, err = processor.compose_id_scans_to_a4_pdf(front, back, out_pdf)
    if not ok:
        out_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err or "Compose failed")

    ocr_requested = bool(settings.get("id_scan_ocr", False))
    ocr_applied = False
    final_pdf = out_pdf
    if ocr_requested:
        fd2, tmp2 = tempfile.mkstemp(prefix="kopi-id-ocr-", suffix=".pdf")
        os.close(fd2)
        ocr_out = Path(tmp2)
        ocr_ok, ocr_err = processor.apply_ocrmypdf(out_pdf, ocr_out)
        if not ocr_ok:
            out_pdf.unlink(missing_ok=True)
            ocr_out.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=ocr_err)
        out_pdf.unlink(missing_ok=True)
        final_pdf = ocr_out
        ocr_applied = True

    if not await ID_SCAN_STORE.set_pdf(body.session_id, str(final_pdf)):
        final_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Session error")

    b64, prev_err = processor.pdf_to_preview_png_base64(final_pdf)
    if b64 is None:
        log.warning("id_scan_preview_fail: %s", prev_err)

    return {
        "ok": True,
        "session_id": body.session_id,
        "preview_base64": b64,
        "ocr_applied": ocr_applied,
    }


@app.post("/api/id-scan/print")
async def api_id_scan_print(body: IdScanSessionBody):
    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    pdf_path = str(pl.get("pdf") or "") if pl else ""
    if not pdf_path or not Path(pdf_path).is_file():
        raise HTTPException(status_code=400, detail="Compose the ID scan before printing.")
    result = await printer.print_file(
        pdf_path,
        duplex=False,
        job_name="kopi-id-scan",
        device=str(settings.get("printer_device", "")).strip() or None,
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")
    msg = "Print job submitted"
    if result.job_id:
        msg += f" ({result.job_id})"
    if result.destination:
        msg += f" to {result.destination}"
    return {"ok": True, "message": msg, "job_id": result.job_id, "destination": result.destination}


@app.post("/api/id-scan/email")
async def api_id_scan_email(body: IdScanEmailBody):
    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    pdf_path = str(pl.get("pdf") or "") if pl else ""
    if not pdf_path or not Path(pdf_path).is_file():
        raise HTTPException(status_code=400, detail="Compose the ID scan before emailing.")
    try:
        pdf_bytes = Path(pdf_path).read_bytes()
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ok, err = mailer.send_pdf_email(
        pdf_bytes,
        to_addr=body.recipient.strip(),
        subject=f"ID scan {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        smtp=settings.get("smtp", {}),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "message": "ID scan emailed"}


@app.post("/api/id-scan/discard")
async def api_id_scan_discard(body: IdScanSessionBody):
    await ID_SCAN_STORE.discard(body.session_id)
    return {"ok": True}


@app.post("/api/scan")
async def api_scan(body: ScanBody):
    settings = load_settings()
    scan = await scanner.scan_copy_image_file(
        duplex=body.duplex,
        device=str(settings.get("scanner_device", "")).strip() or None,
    )
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")
    scan_id = await SCAN_STORE.put_path(scan.path)
    try:
        bytes_size = Path(scan.path).stat().st_size
    except OSError:
        bytes_size = 0
    return {"scan_id": scan_id, "bytes": bytes_size}


@app.post("/api/print")
async def api_print(body: PrintBody):
    settings = load_settings()
    try:
        image_path = await SCAN_STORE.pop_path(body.scan_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="Scan expired or not found. Please scan again.",
        ) from None

    result = await printer.print_file(
        image_path,
        duplex=body.duplex,
        job_name="kopi-copy",
        device=str(settings.get("printer_device", "")).strip() or None,
    )
    if not result.ok:
        await SCAN_STORE.put_path(image_path)
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")
    try:
        Path(image_path).unlink(missing_ok=True)
    except OSError:
        pass
    message = "Print job submitted"
    if result.job_id:
        message += f" ({result.job_id})"
    if result.destination:
        message += f" to {result.destination}"
    return {"ok": True, "message": message, "job_id": result.job_id, "destination": result.destination}


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
async def api_scan_usb(body: ScanUsbBody = Body(default_factory=ScanUsbBody)):
    settings = load_settings()
    vols = usb_manager.list_usb_volumes()
    try:
        mount = usb_manager.resolve_writable_usb_mount(body.mount_path, volumes=vols)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e) or "USB Not Found") from e
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
        "id_scan_ocr": bool(settings.get("id_scan_ocr", False)),
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
    settings["id_scan_ocr"] = bool(body.id_scan_ocr)
    save_settings(settings)
    return {"ok": True, "message": "Settings saved"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
