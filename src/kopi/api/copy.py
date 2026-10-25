"""Copy workflow endpoints: two-step (/api/scan + /api/print) and direct (/api/copy)."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import img2pdf
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter

from kopi.config import CopyDefaultsConfig, load_settings, save_settings
from kopi.hardware import (
    DuplexMode,
    HardwareBusyError,
    ScanSource,
    get_hardware_lock,
    get_printer,
    get_scanner,
)

log = logging.getLogger("kopi.api.copy")
router = APIRouter(prefix="/api", tags=["copy"])

SCAN_TTL_SEC = int(os.environ.get("KOPI_SCAN_TTL_SEC", "300"))


class ScanStore:
    """In-memory copy artifact cache with lazy TTL expiry, multi-page batching, and retry restoration."""

    def __init__(self, ttl_sec: int) -> None:
        self._ttl_sec = ttl_sec
        self._lock = asyncio.Lock()
        self._data: dict[str, tuple[float, list[str]]] = {}

    def _purge_unlocked(self) -> int:
        now = time.monotonic()
        dead = [k for k, (exp, _) in self._data.items() if exp <= now]
        for k in dead:
            _exp, paths = self._data.pop(k)
            for p in paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
        return len(dead)

    async def purge_expired(self) -> int:
        """Acquire lock and remove all expired scan entries and their temporary files."""
        async with self._lock:
            return self._purge_unlocked()

    async def put_path(self, path: str, *, scan_id: str | None = None) -> str:
        return await self.put_paths([path], scan_id=scan_id)

    async def put_paths(self, paths: list[str], *, scan_id: str | None = None) -> str:
        sid = scan_id or uuid.uuid4().hex
        exp = time.monotonic() + self._ttl_sec
        async with self._lock:
            self._purge_unlocked()
            self._data[sid] = (exp, list(paths))
        log.info("scan_cached scan_id=%s pages=%d ttl_sec=%d", sid, len(paths), self._ttl_sec)
        return sid

    async def append_path(self, path: str, *, scan_id: str | None = None) -> tuple[str, int]:
        sid = scan_id or uuid.uuid4().hex
        exp = time.monotonic() + self._ttl_sec
        async with self._lock:
            self._purge_unlocked()
            existing = self._data.get(sid)
            if existing is not None and existing[0] > time.monotonic():
                pages = list(existing[1]) + [path]
            else:
                pages = [path]
            self._data[sid] = (exp, pages)
        log.info("scan_page_appended scan_id=%s pages=%d ttl_sec=%d", sid, len(pages), self._ttl_sec)
        return sid, len(pages)

    async def peek_paths(self, scan_id: str) -> list[str]:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.get(scan_id)
            if item is None:
                raise KeyError(scan_id)
            exp, paths = item
            if exp <= time.monotonic():
                self._data.pop(scan_id, None)
                for p in paths:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except OSError:
                        pass
                raise KeyError(scan_id)
            # Refresh TTL on active preview interaction
            self._data[scan_id] = (time.monotonic() + self._ttl_sec, list(paths))
            return list(paths)

    async def pop_paths(self, scan_id: str) -> list[str]:
        async with self._lock:
            self._purge_unlocked()
            item = self._data.pop(scan_id, None)
            if item is None:
                raise KeyError(scan_id)
            exp, paths = item
            if exp <= time.monotonic():
                for p in paths:
                    try:
                        Path(p).unlink(missing_ok=True)
                    except OSError:
                        pass
                raise KeyError(scan_id)
            return paths

    async def pop_path(self, scan_id: str) -> str:
        paths = await self.pop_paths(scan_id)
        return paths[0]

    async def discard(self, scan_id: str) -> None:
        async with self._lock:
            item = self._data.pop(scan_id, None)
        if item is not None:
            for p in item[1]:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass


SCAN_STORE = ScanStore(SCAN_TTL_SEC)


class ScanBody(BaseModel):
    duplex: bool = False
    color: bool = True
    resolution_dpi: int = Field(default=300, ge=72, le=600)
    source: ScanSource = ScanSource.AUTO
    original_size: str = "A4"
    lighter_darker: int = Field(default=0, ge=-4, le=4)
    content_type: str = "mixed"
    resize_mode: str = "actual"
    resize_percent: int = Field(default=100, ge=25, le=400)
    append_to_scan_id: str | None = None


class PrintBody(BaseModel):
    scan_id: str = Field(..., min_length=8)
    copies: int = Field(default=1, ge=1, le=99)
    duplex: bool | DuplexMode = False
    page_flip: str = "long_edge"
    color: bool = True
    paper_size: str | None = Field(default="A4")
    collate: bool | None = True
    resize_mode: str | None = "actual"
    quality: str | None = "normal"


class CopyBody(BaseModel):
    copies: int = Field(default=1, ge=1, le=99)
    duplex: bool | DuplexMode = False
    scan_duplex: bool | None = None
    print_duplex: bool | DuplexMode | None = None
    page_flip: str = "long_edge"
    color: bool = True
    resolution_dpi: int = Field(default=300, ge=72, le=600)
    source: ScanSource = ScanSource.AUTO
    original_size: str = "A4"
    paper_size: str | None = Field(default="A4")
    lighter_darker: int = Field(default=0, ge=-4, le=4)
    content_type: str = "mixed"
    resize_mode: str = "actual"
    resize_percent: int = Field(default=100, ge=25, le=400)
    collate: bool | None = True
    quality: str | None = "normal"


def _is_duplex_requested(duplex: bool | DuplexMode) -> bool:
    if isinstance(duplex, DuplexMode):
        return duplex is not DuplexMode.NONE
    return bool(duplex)


def _resolve_print_duplex(duplex: bool | DuplexMode, page_flip: str) -> bool | DuplexMode:
    if isinstance(duplex, DuplexMode):
        return duplex
    if duplex and page_flip.strip().lower() == "short_edge":
        return DuplexMode.SHORT_EDGE
    return duplex


@router.get("/copy/defaults")
async def get_copy_defaults() -> dict[str, Any]:
    """Return persistent default settings for the Copy menu."""
    settings = load_settings()
    return settings.copy_defaults.model_dump(mode="json")


@router.put("/copy/defaults")
async def put_copy_defaults(body: CopyDefaultsConfig) -> dict[str, Any]:
    """Save persistent default settings for the Copy menu."""
    settings = load_settings()
    settings.copy_defaults = body
    save_settings(settings)
    return {"ok": True, "defaults": settings.copy_defaults.model_dump(mode="json")}


@router.post("/scan")
async def api_scan(body: ScanBody) -> dict[str, Any]:
    settings = load_settings()
    lock = get_hardware_lock()
    try:
        async with lock.acquire("scan", wait=False):
            scan = await get_scanner().scan_copy_file(
                duplex=body.duplex,
                source=body.source,
                device=settings.scanner_device.strip() or None,
                resolution_dpi=body.resolution_dpi,
                color=body.color,
                original_size=body.original_size,
                lighter_darker=body.lighter_darker,
                content_type=body.content_type,
                resize_mode=body.resize_mode,
                resize_percent=body.resize_percent,
            )
    except HardwareBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not scan.ok:
        if scan.user_message == "Cancelled":
            return {"cancelled": True, "scan_id": "", "pages": 0, "bytes": 0}
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    scan_id, page_count = await SCAN_STORE.append_path(
        scan.path, scan_id=body.append_to_scan_id
    )
    if page_count == 1 and Path(scan.path).suffix.lower() == ".pdf":
        try:
            page_count = len(PdfReader(scan.path).pages)
        except Exception:
            page_count = 1
    try:
        bytes_size = Path(scan.path).stat().st_size
    except OSError:
        bytes_size = 0
    return {
        "cancelled": False,
        "scan_id": scan_id,
        "pages": page_count,
        "bytes": bytes_size,
    }


@router.get("/copy/preview/{scan_id}")
async def get_copy_preview(scan_id: str, page: int = 0) -> Response:
    """Serve a PNG preview of a scanned page (supports both PNG pages and ADF PDFs)."""
    try:
        paths = await SCAN_STORE.peek_paths(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Scan preview expired or not found") from None

    if len(paths) == 1 and Path(paths[0]).suffix.lower() == ".pdf":
        try:
            reader = PdfReader(paths[0])
            if page < 0 or page >= len(reader.pages):
                raise HTTPException(status_code=404, detail="Page index out of range")
            pdf_page = reader.pages[page]
            images = pdf_page.images
            if not images:
                raise HTTPException(status_code=404, detail="No embedded page image found")
            with Image.open(io.BytesIO(images[0].data)) as src_img:
                img: Image.Image = src_img
                rot = int(pdf_page.get("/Rotate", 0) or 0) % 360
                if rot == 90:
                    img = img.transpose(Image.Transpose.ROTATE_270)
                elif rot == 180:
                    img = img.transpose(Image.Transpose.ROTATE_180)
                elif rot == 270:
                    img = img.transpose(Image.Transpose.ROTATE_90)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return Response(
                    content=buf.getvalue(),
                    media_type="image/png",
                    headers={"Cache-Control": "no-store"},
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Preview render error: {e}") from e

    if page < 0 or page >= len(paths):
        raise HTTPException(status_code=404, detail="Page index out of range")
    target = Path(paths[page])
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Page file missing")
    return Response(
        content=target.read_bytes(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/copy/preview/{scan_id}/rotate")
async def rotate_copy_preview_page(scan_id: str, page: int = 0) -> dict[str, Any]:
    """Rotate a scanned page 90 degrees clockwise in-place."""
    try:
        paths = await SCAN_STORE.peek_paths(scan_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Scan expired or not found") from None

    if len(paths) == 1 and Path(paths[0]).suffix.lower() == ".pdf":
        pdf_path = Path(paths[0])
        reader = PdfReader(str(pdf_path))
        if page < 0 or page >= len(reader.pages):
            raise HTTPException(status_code=404, detail="Page index out of range")
        writer = PdfWriter()
        for idx, p in enumerate(reader.pages):
            if idx == page:
                p.rotate(90)
            writer.add_page(p)
        with pdf_path.open("wb") as f:
            writer.write(f)
        return {"ok": True, "page": page}

    if page < 0 or page >= len(paths):
        raise HTTPException(status_code=404, detail="Page index out of range")
    target = Path(paths[page])
    with Image.open(target) as img:
        rotated = img.transpose(Image.Transpose.ROTATE_270)
        rotated.save(target, format="PNG")
    return {"ok": True, "page": page}


@router.post("/copy/cancel")
async def api_copy_cancel(scan_id: str | None = None) -> dict[str, Any]:
    """Stop active scan or cancel active print job (the page currently printing finishes ejecting)."""
    if scan_id:
        await SCAN_STORE.discard(scan_id)
    scan_cancelled = await get_scanner().cancel_scan()
    print_cancelled = await get_printer().cancel_print()
    return {
        "ok": True,
        "scan_cancelled": scan_cancelled,
        "print_cancelled": print_cancelled,
    }


@router.post("/print")
async def api_print(body: PrintBody) -> dict[str, Any]:
    settings = load_settings()
    try:
        page_paths = await SCAN_STORE.pop_paths(body.scan_id)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail="Scan expired or not found. Please scan again.",
        ) from None

    temp_combined_pdf: Path | None = None
    if len(page_paths) == 1:
        print_target = page_paths[0]
    else:
        fd_pdf, pdf_path = tempfile.mkstemp(prefix="kopi-flatbed-multi-", suffix=".pdf")
        os.close(fd_pdf)
        temp_combined_pdf = Path(pdf_path)
        try:
            pdf_bytes = img2pdf.convert(page_paths)
            if not pdf_bytes:
                temp_combined_pdf.unlink(missing_ok=True)
                await SCAN_STORE.put_paths(page_paths, scan_id=body.scan_id)
                raise HTTPException(status_code=400, detail="Failed to assemble multi-page PDF")
            temp_combined_pdf.write_bytes(pdf_bytes)
            print_target = str(temp_combined_pdf)
        except HTTPException:
            raise
        except Exception as e:
            temp_combined_pdf.unlink(missing_ok=True)
            await SCAN_STORE.put_paths(page_paths, scan_id=body.scan_id)
            raise HTTPException(status_code=400, detail=f"PDF assembly error: {e}") from e

    effective_duplex = _resolve_print_duplex(body.duplex, body.page_flip)
    lock = get_hardware_lock()
    try:
        async with lock.acquire("print", wait=False):
            result = await get_printer().print_file(
                print_target,
                copies=body.copies,
                duplex=effective_duplex,
                color=body.color,
                paper_size=body.paper_size,
                collate=body.collate,
                resize_mode=body.resize_mode,
                quality=body.quality,
                job_name="kopi-copy",
                device=settings.printer_device.strip() or None,
            )
    except HardwareBusyError as e:
        await SCAN_STORE.put_paths(page_paths, scan_id=body.scan_id)
        raise HTTPException(status_code=409, detail=str(e)) from e
    except BaseException:
        await SCAN_STORE.put_paths(page_paths, scan_id=body.scan_id)
        raise
    finally:
        if temp_combined_pdf is not None:
            temp_combined_pdf.unlink(missing_ok=True)

    if not result.ok:
        await SCAN_STORE.put_paths(page_paths, scan_id=body.scan_id)
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")

    for p in page_paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass

    message = f"Print job submitted ({body.copies} {'copy' if body.copies == 1 else 'copies'})"
    if result.job_id:
        message += f" [{result.job_id}]"
    if result.destination:
        message += f" to {result.destination}"
    return {
        "ok": True,
        "copies": body.copies,
        "message": message,
        "job_id": result.job_id,
        "destination": result.destination,
    }


@router.post("/copy")
async def api_copy(body: CopyBody) -> dict[str, Any]:
    """One-step copy operation: scan document and immediately print N copies."""
    settings = load_settings()
    lock = get_hardware_lock()
    effective_scan_duplex = (
        body.scan_duplex if body.scan_duplex is not None else _is_duplex_requested(body.duplex)
    )
    raw_print_duplex = (
        body.print_duplex if body.print_duplex is not None else body.duplex
    )
    effective_print_duplex = _resolve_print_duplex(raw_print_duplex, body.page_flip)

    try:
        async with lock.acquire("copy", wait=False):
            scan = await get_scanner().scan_copy_file(
                duplex=effective_scan_duplex,
                source=body.source,
                device=settings.scanner_device.strip() or None,
                resolution_dpi=body.resolution_dpi,
                color=body.color,
                original_size=body.original_size,
                lighter_darker=body.lighter_darker,
                content_type=body.content_type,
                resize_mode=body.resize_mode,
                resize_percent=body.resize_percent,
            )
            if not scan.ok:
                if scan.user_message == "Cancelled":
                    return {"ok": False, "cancelled": True, "copies": 0, "message": "Copy cancelled"}
                raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

            try:
                result = await get_printer().print_file(
                    scan.path,
                    copies=body.copies,
                    duplex=effective_print_duplex,
                    color=body.color,
                    paper_size=body.paper_size,
                    collate=body.collate,
                    resize_mode=body.resize_mode,
                    quality=body.quality,
                    job_name="kopi-copy",
                    device=settings.printer_device.strip() or None,
                )
            finally:
                Path(scan.path).unlink(missing_ok=True)
    except HardwareBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not result.ok:
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")

    message = f"Copy job submitted ({body.copies} {'copy' if body.copies == 1 else 'copies'})"
    if result.job_id:
        message += f" [{result.job_id}]"
    if result.destination:
        message += f" to {result.destination}"
    return {
        "ok": True,
        "copies": body.copies,
        "message": message,
        "job_id": result.job_id,
        "destination": result.destination,
    }
