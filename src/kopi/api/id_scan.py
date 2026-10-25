"""ID Card Copy / Scan workflow endpoints (/api/id-scan/*)."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from kopi.config import load_settings
from kopi.hardware import (
    HardwareBusyError,
    get_hardware_lock,
    get_printer,
    get_scanner,
)
from kopi.processing import mailer
from kopi.processing.id_card import (
    apply_ocrmypdf,
    compose_id_scans_to_a4_pdf,
    pdf_to_preview_png_base64,
)

log = logging.getLogger("kopi.api.id_scan")
router = APIRouter(prefix="/api", tags=["id-scan"])

ID_SCAN_TTL_SEC = int(os.environ.get("KOPI_ID_SCAN_TTL_SEC", "600"))


class IdScanStore:
    """Session state for two-sided ID scan -> one composed A4 PDF."""

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

    async def set_side(self, sid: str, side_key: str, path: str) -> bool:
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
            old = pl.get(side_key)
            if old:
                try:
                    Path(str(old)).unlink(missing_ok=True)
                except OSError:
                    pass
            pl[side_key] = path
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


ID_SCAN_STORE = IdScanStore(ID_SCAN_TTL_SEC)


class IdScanSessionBody(BaseModel):
    session_id: str = Field(..., min_length=8)


class IdScanEmailBody(BaseModel):
    session_id: str = Field(..., min_length=8)
    recipient: str = Field(..., min_length=3)
    subject: str | None = None
    body: str | None = None


@router.post("/id-scan/front")
async def api_id_scan_front() -> dict[str, Any]:
    settings = load_settings()
    dev = settings.scanner_device.strip() or None
    sid = await ID_SCAN_STORE.create_session()
    lock = get_hardware_lock()
    try:
        async with lock.acquire("id-scan-front", wait=False):
            res = await get_scanner().scan_id_side("front", device=dev)
    except HardwareBusyError as e:
        await ID_SCAN_STORE.discard(sid)
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not res.ok:
        await ID_SCAN_STORE.discard(sid)
        raise HTTPException(status_code=400, detail=res.user_message or "Scan failed")
    if not await ID_SCAN_STORE.set_side(sid, "front", res.path):
        Path(res.path).unlink(missing_ok=True)
        await ID_SCAN_STORE.discard(sid)
        raise HTTPException(status_code=500, detail="Session error")
    return {"ok": True, "session_id": sid}


@router.post("/id-scan/back")
async def api_id_scan_back(body: IdScanSessionBody) -> dict[str, Any]:
    settings = load_settings()
    dev = settings.scanner_device.strip() or None
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    if not pl or not pl.get("front"):
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired session. Scan the front again.",
        )

    lock = get_hardware_lock()
    try:
        async with lock.acquire("id-scan-back", wait=False):
            res = await get_scanner().scan_id_side("back", device=dev)
    except HardwareBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not res.ok:
        raise HTTPException(status_code=400, detail=res.user_message or "Scan failed")
    if not await ID_SCAN_STORE.set_side(body.session_id, "back", res.path):
        Path(res.path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Session error")
    return {"ok": True}


@router.post("/id-scan/compose")
async def api_id_scan_compose(body: IdScanSessionBody) -> dict[str, Any]:
    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    if not pl or not pl.get("front") or not pl.get("back"):
        raise HTTPException(status_code=400, detail="Scan both sides before composing.")

    front = Path(str(pl["front"]))
    back = Path(str(pl["back"]))
    fd, tmp = tempfile.mkstemp(prefix="kopi-id-composed-", suffix=".pdf")
    os.close(fd)
    out_pdf = Path(tmp)

    ok, err = compose_id_scans_to_a4_pdf(front, back, out_pdf)
    if not ok:
        out_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=err or "Compose failed")

    ocr_requested = bool(settings.id_scan_ocr)
    ocr_applied = False
    final_pdf = out_pdf
    if ocr_requested:
        fd2, tmp2 = tempfile.mkstemp(prefix="kopi-id-ocr-", suffix=".pdf")
        os.close(fd2)
        ocr_out = Path(tmp2)
        ocr_ok, ocr_err = apply_ocrmypdf(out_pdf, ocr_out)
        if not ocr_ok:
            out_pdf.unlink(missing_ok=True)
            ocr_out.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=ocr_err or "OCR failed")
        out_pdf.unlink(missing_ok=True)
        final_pdf = ocr_out
        ocr_applied = True

    if not await ID_SCAN_STORE.set_side(body.session_id, "pdf", str(final_pdf)):
        final_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Session error")

    b64, prev_err = pdf_to_preview_png_base64(final_pdf)
    if b64 is None:
        log.warning("id_scan_preview_fail: %s", prev_err)

    return {
        "ok": True,
        "session_id": body.session_id,
        "preview_base64": b64,
        "ocr_applied": ocr_applied,
    }


@router.post("/id-scan/print")
async def api_id_scan_print(body: IdScanSessionBody) -> dict[str, Any]:
    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    pdf_path = str(pl.get("pdf") or "") if pl else ""
    if not pdf_path or not Path(pdf_path).is_file():
        raise HTTPException(status_code=400, detail="Compose the ID scan before printing.")

    lock = get_hardware_lock()
    try:
        async with lock.acquire("id-scan-print", wait=False):
            result = await get_printer().print_file(
                pdf_path,
                duplex=False,
                job_name="kopi-id-scan",
                device=settings.printer_device.strip() or None,
            )
    except HardwareBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not result.ok:
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")
    msg = "Print job submitted"
    if result.job_id:
        msg += f" ({result.job_id})"
    if result.destination:
        msg += f" to {result.destination}"
    return {
        "ok": True,
        "message": msg,
        "job_id": result.job_id,
        "destination": result.destination,
    }


@router.post("/id-scan/email")
async def api_id_scan_email(body: IdScanEmailBody) -> dict[str, Any]:
    settings = load_settings()
    pl = await ID_SCAN_STORE.get_payload(body.session_id)
    pdf_path = str(pl.get("pdf") or "") if pl else ""
    if not pdf_path or not Path(pdf_path).is_file():
        raise HTTPException(status_code=400, detail="Compose the ID scan before emailing.")
    try:
        pdf_bytes = Path(pdf_path).read_bytes()
    except OSError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    default_subject = f"ID scan {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
    subject = (body.subject or "").strip() or default_subject
    email_body = (body.body or "").strip() or None
    ok, err = mailer.send_pdf_email(
        pdf_bytes,
        to_addr=body.recipient.strip(),
        subject=subject,
        body=email_body,
        smtp=settings.smtp,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err or "Failed to send email")
    return {"ok": True, "message": "ID scan emailed"}


@router.post("/id-scan/discard")
async def api_id_scan_discard(body: IdScanSessionBody) -> dict[str, Any]:
    await ID_SCAN_STORE.discard(body.session_id)
    return {"ok": True}
