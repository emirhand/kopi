"""Print from USB endpoints: browse (/api/usb/files), preview (/api/usb/preview), and print (/api/usb/print)."""

from __future__ import annotations

import io
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import img2pdf
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from pypdf import PdfReader

from kopi.config import load_settings
from kopi.hardware import (
    DuplexMode,
    HardwareBusyError,
    get_hardware_lock,
    get_printer,
    list_usb_volumes,
    resolve_writable_usb_mount,
)

log = logging.getLogger("kopi.api.usb_print")
router = APIRouter(prefix="/api/usb", tags=["usb-print"])

_PRINTABLE_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt"}
)


def _format_bytes(size: int) -> str:
    num = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024.0 or unit == "GB":
            return f"{int(num)} B" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{int(size)} B"


def _resolve_confined_usb_path(
    *,
    mount_path: str | None,
    device: str | None,
    rel_path: str,
) -> tuple[Path, Path]:
    """Resolve USB root mount and ensure rel_path stays strictly inside it."""
    vols = list_usb_volumes()
    try:
        usb_root = resolve_writable_usb_mount(
            mount_path,
            device=device,
            volumes=vols,
        ).resolve()
    except (FileNotFoundError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e) or "USB drive not available") from e

    clean_rel = (rel_path or "").strip().lstrip("/\\")
    if not clean_rel:
        return usb_root, usb_root

    candidate = (usb_root / clean_rel).resolve()
    if not candidate.is_relative_to(usb_root):
        raise HTTPException(status_code=400, detail="Invalid path outside USB drive")
    return usb_root, candidate


def _inspect_page_count(path: Path) -> int:
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            return max(1, len(PdfReader(str(path)).pages))
        except Exception:
            return 1
    if ext in (".tif", ".tiff"):
        try:
            with Image.open(path) as im:
                return int(getattr(im, "n_frames", 1) or 1)
        except Exception:
            return 1
    return 1


def _render_text_preview_png(text: str, *, title: str = "") -> bytes:
    canvas = Image.new("RGB", (620, 877), color=(255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    y = 32
    if title:
        draw.text((32, y), title, fill=(80, 80, 90))
        y += 28
        draw.line((32, y, 588, y), fill=(210, 210, 220), width=1)
        y += 16
    for line in text.splitlines()[:42]:
        draw.text((32, y), line[:85], fill=(20, 20, 25))
        y += 18
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/files")
async def api_usb_list_files(
    mount_path: str | None = Query(default=None),
    device: str | None = Query(default=None),
    subpath: str = Query(default=""),
) -> dict[str, Any]:
    """List folders and printable files inside the selected USB flash drive."""
    usb_root, current_dir = _resolve_confined_usb_path(
        mount_path=mount_path,
        device=device,
        rel_path=subpath,
    )
    if not current_dir.exists() or not current_dir.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found on USB drive")

    entries: list[dict[str, Any]] = []
    try:
        children = list(current_dir.iterdir())
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot read USB directory: {e}") from e

    for item in children:
        name = item.name
        if name.startswith(".") or name.startswith("$"):
            continue
        try:
            resolved_item = item.resolve()
            if not resolved_item.is_relative_to(usb_root):
                continue
            is_dir = item.is_dir()
            if is_dir:
                rel = str(resolved_item.relative_to(usb_root)).replace("\\", "/")
                entries.append(
                    {
                        "name": name,
                        "rel_path": rel,
                        "is_dir": True,
                        "ext": "",
                        "size_bytes": 0,
                        "size_label": "Folder",
                        "pages": 0,
                    }
                )
            elif item.is_file():
                ext = item.suffix.lower()
                if ext not in _PRINTABLE_EXTENSIONS:
                    continue
                st = item.stat()
                rel = str(resolved_item.relative_to(usb_root)).replace("\\", "/")
                entries.append(
                    {
                        "name": name,
                        "rel_path": rel,
                        "is_dir": False,
                        "ext": ext.lstrip("."),
                        "size_bytes": st.st_size,
                        "size_label": _format_bytes(st.st_size),
                        "pages": _inspect_page_count(resolved_item),
                    }
                )
        except OSError:
            continue

    entries.sort(key=lambda e: (not bool(e["is_dir"]), str(e["name"]).lower()))
    rel_current = (
        ""
        if current_dir == usb_root
        else str(current_dir.relative_to(usb_root)).replace("\\", "/")
    )
    return {
        "mount_path": str(usb_root),
        "subpath": rel_current,
        "entries": entries,
    }


@router.get("/preview")
async def api_usb_preview_file(
    path: str = Query(..., min_length=1),
    page: int = Query(default=0, ge=0),
    mount_path: str | None = Query(default=None),
    device: str | None = Query(default=None),
) -> Response:
    """Render a PNG preview of a printable file on the USB drive."""
    _usb_root, target = _resolve_confined_usb_path(
        mount_path=mount_path,
        device=device,
        rel_path=path,
    )
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found on USB drive")

    ext = target.suffix.lower()
    if ext not in _PRINTABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format for preview")

    if ext == ".txt":
        text_content = target.read_text(encoding="utf-8", errors="replace")
        png_bytes = _render_text_preview_png(text_content, title=target.name)
        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    if ext == ".pdf":
        try:
            reader = PdfReader(str(target))
            if page < 0 or page >= len(reader.pages):
                raise HTTPException(status_code=404, detail="Page index out of range")
            pdf_page = reader.pages[page]
            if pdf_page.images:
                with Image.open(io.BytesIO(pdf_page.images[0].data)) as src_im:
                    im: Image.Image = src_im.convert("RGB")
                    rot = int(pdf_page.get("/Rotate", 0) or 0) % 360
                    if rot == 90:
                        im = im.transpose(Image.Transpose.ROTATE_270)
                    elif rot == 180:
                        im = im.transpose(Image.Transpose.ROTATE_180)
                    elif rot == 270:
                        im = im.transpose(Image.Transpose.ROTATE_90)
                    im.thumbnail((900, 1200))
                    buf = io.BytesIO()
                    im.save(buf, format="PNG")
                    return Response(
                        content=buf.getvalue(),
                        media_type="image/png",
                        headers={"Cache-Control": "no-store"},
                    )
            extracted = (pdf_page.extract_text() or "").strip()
            fallback_text = extracted or f"[PDF Document: {target.name} — Page {page + 1} of {len(reader.pages)}]"
            png_bytes = _render_text_preview_png(
                fallback_text,
                title=f"{target.name} (Page {page + 1}/{len(reader.pages)})",
            )
            return Response(
                content=png_bytes,
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not preview PDF: {e}") from e

    # Image formats (.png, .jpg, .jpeg, .tif, .tiff)
    try:
        with Image.open(target) as src_im:
            n_frames = int(getattr(src_im, "n_frames", 1) or 1)
            if page >= n_frames:
                raise HTTPException(status_code=404, detail="Page index out of range")
            if page > 0 and hasattr(src_im, "seek"):
                src_im.seek(page)
            rgb = src_im.convert("RGB")
            rgb.thumbnail((900, 1200))
            buf = io.BytesIO()
            rgb.save(buf, format="PNG")
            return Response(
                content=buf.getvalue(),
                media_type="image/png",
                headers={"Cache-Control": "no-store"},
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not preview image: {e}") from e


class UsbPrintBody(BaseModel):
    path: str = Field(..., min_length=1)
    device: str | None = None
    mount_path: str | None = None
    copies: int = Field(default=1, ge=1, le=99)
    duplex: bool = False
    page_flip: str = "long_edge"
    color: bool = True
    paper_size: str = "A4"
    collate: bool = True
    resize_mode: str = "fit_to_page"
    quality: str = "normal"


def _prepare_printable_file(target: Path) -> tuple[str, Path | None]:
    """Ensure images/multi-frame TIFFs are wrapped into a temporary PDF for reliable CUPS printing."""
    ext = target.suffix.lower()
    if ext in (".pdf", ".txt"):
        return str(target), None

    fd_pdf, pdf_path = tempfile.mkstemp(prefix="kopi-usb-print-", suffix=".pdf")
    os.close(fd_pdf)
    temp_pdf = Path(pdf_path)
    try:
        if ext in (".tif", ".tiff"):
            frame_pngs: list[bytes] = []
            with Image.open(target) as src_im:
                n_frames = int(getattr(src_im, "n_frames", 1) or 1)
                for idx in range(n_frames):
                    if idx > 0 and hasattr(src_im, "seek"):
                        src_im.seek(idx)
                    rgb = src_im.convert("RGB")
                    buf = io.BytesIO()
                    rgb.save(buf, format="PNG")
                    frame_pngs.append(buf.getvalue())
            pdf_bytes = img2pdf.convert(frame_pngs)
        else:
            with Image.open(target) as src_im:
                rgb = src_im.convert("RGB")
                buf = io.BytesIO()
                rgb.save(buf, format="PNG")
                pdf_bytes = img2pdf.convert([buf.getvalue()])
        if not pdf_bytes:
            temp_pdf.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Could not convert image for printing")
        temp_pdf.write_bytes(bytes(pdf_bytes))
        return str(temp_pdf), temp_pdf
    except HTTPException:
        raise
    except Exception as e:
        temp_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not prepare image for printing: {e}") from e


@router.post("/print")
async def api_usb_print_file(body: UsbPrintBody) -> dict[str, Any]:
    """Print a selected file from a USB flash drive via CUPS."""
    _usb_root, target = _resolve_confined_usb_path(
        mount_path=body.mount_path,
        device=body.device,
        rel_path=body.path,
    )
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Selected file not found on USB drive")
    if target.suffix.lower() not in _PRINTABLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format for printing")

    print_path, temp_pdf = _prepare_printable_file(target)
    effective_duplex: bool | DuplexMode = (
        DuplexMode.SHORT_EDGE
        if (body.duplex and body.page_flip.strip().lower() == "short_edge")
        else body.duplex
    )

    settings = load_settings()
    lock = get_hardware_lock()
    try:
        async with lock.acquire("usb-print", wait=False):
            result = await get_printer().print_file(
                print_path,
                copies=body.copies,
                duplex=effective_duplex,
                color=body.color,
                paper_size=body.paper_size,
                collate=body.collate,
                resize_mode=body.resize_mode,
                quality=body.quality,
                job_name=f"kopi-usb-{target.name}",
                device=settings.printer_device.strip() or None,
            )
    except HardwareBusyError as e:
        if temp_pdf is not None:
            temp_pdf.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(e)) from e
    finally:
        if temp_pdf is not None:
            temp_pdf.unlink(missing_ok=True)

    if not result.ok:
        raise HTTPException(status_code=400, detail=result.user_message or "Print failed")

    return {
        "ok": True,
        "filename": target.name,
        "copies": body.copies,
        "job_id": result.job_id,
        "destination": result.destination,
        "message": f"Printing {target.name} ({body.copies} {'copy' if body.copies == 1 else 'copies'})",
    }
