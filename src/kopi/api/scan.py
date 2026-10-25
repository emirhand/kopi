"""Scan workflows: Scan to Email (/api/scan/email), Scan to USB (/api/scan/usb), Scan to Archive (/api/scan/archive)."""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import os
import re
import tempfile
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import img2pdf
from fastapi import APIRouter, Body, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
from pypdf import PdfReader

from kopi.api.copy import SCAN_STORE
from kopi.config import load_settings
from kopi.hardware import (
    HardwareBusyError,
    ScanSource,
    get_hardware_lock,
    get_scanner,
    list_usb_volumes,
    resolve_writable_usb_mount,
)
from kopi.processing import mailer
from kopi.processing.pdf import remove_blank_pages_from_pdf

log = logging.getLogger("kopi.api.scan")
router = APIRouter(prefix="/api/scan", tags=["scan"])

ScanOutputFormat = Literal["pdf", "jpg", "jpeg", "png", "tiff", "tif"]


def _get_archive_dir() -> Path:
    env_dir = os.environ.get("KOPI_ARCHIVE_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "archive"


def _dpi_from_resolution_label(label: str) -> int:
    val = (label or "").strip().lower()
    if val == "best":
        return 600
    if val == "high":
        return 300
    return 150


def _normalize_scan_format(fmt: str) -> str:
    f = (fmt or "pdf").strip().lower()
    if f in ("jpg", "jpeg"):
        return "jpeg"
    if f == "png":
        return "png"
    if f in ("tif", "tiff"):
        return "tiff"
    return "pdf"


def _scan_file_extension(fmt_norm: str) -> str:
    if fmt_norm == "jpeg":
        return "jpg"
    if fmt_norm == "png":
        return "png"
    if fmt_norm == "tiff":
        return "tiff"
    return "pdf"


def _sanitize_filename_stem(raw_filename: str | None) -> str:
    raw = (raw_filename or "").strip()
    if not raw:
        return ""
    base = Path(raw.replace("\\", "/")).name
    base = re.sub(r"\.(pdf|jpe?g|png|tiff?)$", "", base, flags=re.IGNORECASE)
    stem = re.sub(r"\s+", "_", base.strip())
    return re.sub(r"[^A-Za-z0-9._-]", "", stem).strip("._-")


def _resolve_scan_filename(
    raw_filename: str | None,
    *,
    fmt_norm: str,
    target_dir: Path | None = None,
    for_email: bool = False,
) -> str:
    """Sanitize an optional user-supplied filename and resolve collisions on disk."""
    ext = _scan_file_extension(fmt_norm)
    stem = _sanitize_filename_stem(raw_filename)

    if not stem:
        if for_email:
            return f"scan.{ext}"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"scan-{ts}-{uuid.uuid4().hex[:8]}.{ext}"

    candidate = f"{stem}.{ext}"
    if target_dir is not None and (target_dir / candidate).exists():
        idx = 1
        while (target_dir / f"{stem}-{idx}.{ext}").exists():
            idx += 1
        candidate = f"{stem}-{idx}.{ext}"
    return candidate


def _resolve_numbered_scan_filenames(
    raw_filename: str | None,
    *,
    page_count: int,
    fmt_norm: str,
    target_dir: Path | None = None,
    for_email: bool = False,
) -> list[str]:
    """Resolve 1 or more filenames (sequentially numbered -1, -2, ... when page_count > 1)."""
    if page_count <= 1:
        return [
            _resolve_scan_filename(
                raw_filename,
                fmt_norm=fmt_norm,
                target_dir=target_dir,
                for_email=for_email,
            )
        ]

    ext = _scan_file_extension(fmt_norm)
    stem = _sanitize_filename_stem(raw_filename)
    if not stem:
        if for_email:
            stem = "scan"
        else:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            stem = f"scan-{ts}-{uuid.uuid4().hex[:6]}"

    names: list[str] = []
    for idx in range(1, page_count + 1):
        candidate = f"{stem}-{idx}.{ext}"
        if target_dir is not None and (target_dir / candidate).exists():
            dup = 1
            while (target_dir / f"{stem}-{idx}-{dup}.{ext}").exists():
                dup += 1
            candidate = f"{stem}-{idx}-{dup}.{ext}"
        names.append(candidate)
    return names


def _extract_pil_images_from_paths(page_paths: list[str]) -> list[Image.Image]:
    """Load each scanned page (whether PNG/JPEG files or an ADF PDF) as a PIL Image."""
    images: list[Image.Image] = []
    for p in page_paths:
        path = Path(p)
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            for pdf_page in reader.pages:
                if not pdf_page.images:
                    continue
                with Image.open(io.BytesIO(pdf_page.images[0].data)) as src_im:
                    im: Image.Image = src_im.convert("RGB")
                    rot = int(pdf_page.get("/Rotate", 0) or 0) % 360
                    if rot == 90:
                        im = im.transpose(Image.Transpose.ROTATE_270)
                    elif rot == 180:
                        im = im.transpose(Image.Transpose.ROTATE_180)
                    elif rot == 270:
                        im = im.transpose(Image.Transpose.ROTATE_90)
                    images.append(im)
        else:
            with Image.open(path) as src_im:
                images.append(src_im.convert("RGB"))
    return images


def _encode_pil_images(images: list[Image.Image], *, fmt_norm: str) -> list[bytes]:
    """Encode PIL images into per-page bytes (JPEG/PNG) or a single multi-page TIFF."""
    if not images:
        raise HTTPException(status_code=400, detail="No scanned page images found")

    if fmt_norm == "tiff":
        buf = io.BytesIO()
        first, rest = images[0], images[1:]
        first.save(
            buf,
            format="TIFF",
            save_all=True,
            append_images=rest,
        )
        return [buf.getvalue()]

    out: list[bytes] = []
    pil_fmt = "PNG" if fmt_norm == "png" else "JPEG"
    for im in images:
        buf = io.BytesIO()
        if pil_fmt == "JPEG":
            im.save(buf, format="JPEG", quality=90)
        else:
            im.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def _assemble_cached_pages_to_payloads(
    page_paths: list[str],
    *,
    fmt_norm: str,
    remove_blank_pages: bool,
) -> list[bytes]:
    """Convert cached page file(s) into 1 or more output file payloads."""
    if not page_paths:
        raise HTTPException(status_code=400, detail="No scanned pages found")

    if fmt_norm == "pdf":
        if len(page_paths) == 1 and Path(page_paths[0]).suffix.lower() == ".pdf":
            raw_pdf = Path(page_paths[0]).read_bytes()
        else:
            pdf_bytes = img2pdf.convert(page_paths)
            if not pdf_bytes:
                raise HTTPException(status_code=400, detail="Failed to assemble multi-page PDF")
            raw_pdf = bytes(pdf_bytes)
        return [
            _finalize_scan_bytes(
                raw_pdf,
                fmt_norm="pdf",
                remove_blank_pages=remove_blank_pages,
            )
        ]

    pil_images = _extract_pil_images_from_paths(page_paths)
    return _encode_pil_images(pil_images, fmt_norm=fmt_norm)


def _finalize_scan_bytes(
    raw: bytes,
    *,
    fmt_norm: str,
    remove_blank_pages: bool,
) -> bytes:
    if fmt_norm != "pdf" or not remove_blank_pages:
        return raw
    fd_in, path_in = tempfile.mkstemp(prefix="kopi-scan-", suffix=".pdf")
    os.close(fd_in)
    fd_out, path_out = tempfile.mkstemp(prefix="kopi-scan-blank-", suffix=".pdf")
    os.close(fd_out)
    p_in = Path(path_in)
    p_out = Path(path_out)
    try:
        p_in.write_bytes(raw)
        ok, err = remove_blank_pages_from_pdf(p_in, p_out)
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Blank page removal failed")
        return p_out.read_bytes()
    finally:
        p_in.unlink(missing_ok=True)
        p_out.unlink(missing_ok=True)


def _convert_direct_scan_bytes(
    raw_bytes: bytes,
    *,
    scanner_fmt: Literal["pdf", "jpg", "jpeg"],
    fmt_norm: str,
    remove_blank_pages: bool,
) -> list[bytes]:
    """Convert direct scan_pdf bytes into the requested target format(s)."""
    if fmt_norm == "pdf":
        return [
            _finalize_scan_bytes(
                raw_bytes,
                fmt_norm="pdf",
                remove_blank_pages=remove_blank_pages,
            )
        ]
    if fmt_norm == "jpeg" and scanner_fmt in ("jpg", "jpeg"):
        return [raw_bytes]

    # Convert from PDF or image bytes via Pillow
    images: list[Image.Image] = []
    if scanner_fmt == "pdf":
        reader = PdfReader(io.BytesIO(raw_bytes))
        for page in reader.pages:
            if page.images:
                with Image.open(io.BytesIO(page.images[0].data)) as im:
                    images.append(im.convert("RGB"))
    else:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            images.append(im.convert("RGB"))
    return _encode_pil_images(images, fmt_norm=fmt_norm)


@contextlib.asynccontextmanager
async def _acquire_or_assemble_scan(
    *,
    operation_name: str,
    scan_id: str | None,
    duplex: bool,
    source: ScanSource | None,
    color: bool,
    dpi: int,
    output_format: ScanOutputFormat,
    fmt_norm: str,
    remove_blank_pages: bool,
) -> AsyncIterator[list[bytes]]:
    """Either assemble a cached multi-step/preview scan_id or run a direct hardware scan."""
    if scan_id and scan_id.strip():
        async with SCAN_STORE.consume_paths(
            scan_id.strip(),
            missing_detail="Scanned pages expired or not found. Please scan again.",
        ) as page_paths:
            payloads = _assemble_cached_pages_to_payloads(
                page_paths,
                fmt_norm=fmt_norm,
                remove_blank_pages=remove_blank_pages,
            )
            yield payloads
        return

    settings = load_settings()
    # Direct hardware scan uses "pdf" for multi-page/PNG/TIFF or "jpg" for single-page JPEG
    scanner_fmt: Literal["pdf", "jpg", "jpeg"] = (
        "jpg" if (fmt_norm == "jpeg" and not duplex) else "pdf"
    )
    _ = output_format
    lock = get_hardware_lock()
    try:
        async with lock.acquire(operation_name, wait=False):
            scan = await get_scanner().scan_pdf(
                duplex=duplex,
                source=source,
                device=settings.scanner_device.strip() or None,
                resolution_dpi=dpi,
                color=color,
                output_format=scanner_fmt,
            )
    except HardwareBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    payloads = _convert_direct_scan_bytes(
        scan.stdout,
        scanner_fmt=scanner_fmt,
        fmt_norm=fmt_norm,
        remove_blank_pages=remove_blank_pages,
    )
    yield payloads


class ScanEmailBody(BaseModel):
    recipient: str = Field(..., min_length=3)
    subject: str | None = None
    body: str | None = None
    filename: str | None = None
    scan_id: str | None = None
    duplex: bool = False
    source: ScanSource | None = None
    color: bool = True
    resolution: Literal["standard", "high", "best"] = "standard"
    output_format: ScanOutputFormat = "pdf"
    remove_blank_pages: bool = False


class ScanUsbBody(BaseModel):
    device: str | None = None
    mount_path: str | None = None
    filename: str | None = None
    scan_id: str | None = None
    duplex: bool = False
    source: ScanSource | None = None
    color: bool = True
    resolution: Literal["standard", "high", "best"] = "standard"
    output_format: ScanOutputFormat = "pdf"
    remove_blank_pages: bool = False


class ScanArchiveBody(BaseModel):
    filename: str | None = None
    scan_id: str | None = None
    duplex: bool = False
    source: ScanSource | None = None
    color: bool = True
    resolution: Literal["standard", "high", "best"] = "standard"
    output_format: ScanOutputFormat = "pdf"
    remove_blank_pages: bool = False


@router.get("/usb/drives")
async def api_list_usb_drives() -> dict[str, Any]:
    """List removable USB mass-storage drives (filtered to storage volumes only)."""
    vols = await asyncio.to_thread(list_usb_volumes)
    return {"drives": [v.to_dict() for v in vols]}


@router.post("/email")
async def api_scan_email(body: ScanEmailBody) -> dict[str, Any]:
    settings = load_settings()
    dpi = _dpi_from_resolution_label(body.resolution)
    fmt_norm = _normalize_scan_format(body.output_format)

    async with _acquire_or_assemble_scan(
        operation_name="scan-email",
        scan_id=body.scan_id,
        duplex=body.duplex,
        source=body.source,
        color=body.color,
        dpi=dpi,
        output_format=body.output_format,
        fmt_norm=fmt_norm,
        remove_blank_pages=body.remove_blank_pages,
    ) as payloads:
        filenames = _resolve_numbered_scan_filenames(
            body.filename,
            page_count=len(payloads),
            fmt_norm=fmt_norm,
            for_email=True,
        )
        default_subject = (
            f"Scan: {filenames[0]} ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)"
        )
        subject = (body.subject or "").strip() or default_subject
        email_body = (body.body or "").strip() or None
        if len(payloads) == 1:
            ok, err = mailer.send_attachment_email(
                payloads[0],
                filename=filenames[0],
                to_addr=body.recipient.strip(),
                subject=subject,
                body=email_body,
                smtp=settings.smtp,
            )
        else:
            ok, err = mailer.send_attachments_email(
                list(zip(filenames, payloads, strict=True)),
                to_addr=body.recipient.strip(),
                subject=subject,
                body=email_body,
                smtp=settings.smtp,
            )
        if not ok:
            raise HTTPException(status_code=400, detail=err or "Failed to send email")

    return {
        "ok": True,
        "filename": filenames[0],
        "filenames": filenames,
        "message": f"Scan emailed ({', '.join(filenames)})",
    }


@router.post("/usb")
async def api_scan_usb(body: ScanUsbBody = Body(default_factory=ScanUsbBody)) -> dict[str, Any]:
    vols = await asyncio.to_thread(list_usb_volumes)
    try:
        mount = await asyncio.to_thread(
            resolve_writable_usb_mount,
            body.mount_path,
            device=body.device,
            volumes=vols,
        )
    except (FileNotFoundError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "USB Not Found") from e

    dpi = _dpi_from_resolution_label(body.resolution)
    fmt_norm = _normalize_scan_format(body.output_format)

    async with _acquire_or_assemble_scan(
        operation_name="scan-usb",
        scan_id=body.scan_id,
        duplex=body.duplex,
        source=body.source,
        color=body.color,
        dpi=dpi,
        output_format=body.output_format,
        fmt_norm=fmt_norm,
        remove_blank_pages=body.remove_blank_pages,
    ) as payloads:
        filenames = _resolve_numbered_scan_filenames(
            body.filename,
            page_count=len(payloads),
            fmt_norm=fmt_norm,
            target_dir=mount,
        )
        saved_paths: list[Path] = []
        try:
            for name, data in zip(filenames, payloads, strict=True):
                dest = mount / name
                with dest.open("wb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                saved_paths.append(dest)
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Could not write to USB: {e}") from e

    msg = (
        f"Saved to {saved_paths[0]}"
        if len(saved_paths) == 1
        else f"Saved {len(saved_paths)} files ({filenames[0]} … {filenames[-1]}) to {mount}"
    )
    return {
        "ok": True,
        "filename": filenames[0],
        "filenames": filenames,
        "message": msg,
    }


@router.post("/archive")
async def api_scan_archive(body: ScanArchiveBody) -> dict[str, Any]:
    dpi = _dpi_from_resolution_label(body.resolution)
    fmt_norm = _normalize_scan_format(body.output_format)

    async with _acquire_or_assemble_scan(
        operation_name="scan-archive",
        scan_id=body.scan_id,
        duplex=body.duplex,
        source=body.source,
        color=body.color,
        dpi=dpi,
        output_format=body.output_format,
        fmt_norm=fmt_norm,
        remove_blank_pages=body.remove_blank_pages,
    ) as payloads:
        archive_dir = _get_archive_dir()
        archive_dir.mkdir(parents=True, exist_ok=True)
        filenames = _resolve_numbered_scan_filenames(
            body.filename,
            page_count=len(payloads),
            fmt_norm=fmt_norm,
            target_dir=archive_dir,
        )
        saved_paths: list[Path] = []
        try:
            for name, data in zip(filenames, payloads, strict=True):
                dest = archive_dir / name
                dest.write_bytes(data)
                saved_paths.append(dest)
        except OSError as e:
            raise HTTPException(status_code=400, detail=f"Could not write archive file: {e}") from e

    msg = (
        f"Saved to {saved_paths[0]}"
        if len(saved_paths) == 1
        else f"Saved {len(saved_paths)} files ({filenames[0]} … {filenames[-1]}) to {archive_dir}"
    )
    return {
        "ok": True,
        "filename": filenames[0],
        "filenames": filenames,
        "message": msg,
    }
