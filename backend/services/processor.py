"""ImageMagick-based layout and optional OCR for ID scan workflow."""

from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("kopi.processor")

A4_W, A4_H = 2480, 3508
MAX_IMG_W = 2000
TOP_MARGIN = 200
STACK_GAP = 80


def _run_magick(args: list[str], timeout: float = 120.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["magick", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "ImageMagick (magick) not found"
    except subprocess.SubprocessError as e:
        return 1, str(e)
    err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
    return proc.returncode, err


def _identify_wh(path: Path) -> tuple[int, int] | None:
    try:
        proc = subprocess.run(
            ["magick", "identify", "-format", "%w %h", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            return None
        parts = (proc.stdout or "").strip().split()
        if len(parts) != 2:
            return None
        return int(parts[0]), int(parts[1])
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def compose_id_scans_to_a4_pdf(front_png: Path, back_png: Path, out_pdf: Path) -> tuple[bool, str]:
    """
    White A4 canvas (2480×3508), front above back, centered horizontally.
    """
    front_png = front_png.resolve()
    back_png = back_png.resolve()
    out_pdf = out_pdf.resolve()
    if not front_png.is_file() or not back_png.is_file():
        return False, "Missing front or back scan file"

    with tempfile.TemporaryDirectory(prefix="kopi-id-compose-") as td:
        tdir = Path(td)
        f_r = tdir / "front_r.png"
        b_r = tdir / "back_r.png"
        rc, msg = _run_magick([str(front_png), "-resize", f"{MAX_IMG_W}x", str(f_r)])
        if rc != 0:
            return False, msg or "magick resize front failed"
        rc, msg = _run_magick([str(back_png), "-resize", f"{MAX_IMG_W}x", str(b_r)])
        if rc != 0:
            return False, msg or "magick resize back failed"

        wh_f = _identify_wh(f_r)
        wh_b = _identify_wh(b_r)
        if not wh_f or not wh_b:
            return False, "Could not read resized image dimensions"

        wf, hf = wh_f
        wb, hb = wh_b
        x1 = (A4_W - wf) // 2
        x2 = (A4_W - wb) // 2
        y1 = TOP_MARGIN
        y2 = y1 + hf + STACK_GAP

        canvas = tdir / "canvas.png"
        rc, msg = _run_magick(["-size", f"{A4_W}x{A4_H}", "xc:white", str(canvas)])
        if rc != 0:
            return False, msg or "magick canvas failed"

        t1 = tdir / "t1.png"
        rc, msg = _run_magick(
            [str(canvas), str(f_r), "-geometry", f"+{x1}+{y1}", "-composite", str(t1)]
        )
        if rc != 0:
            return False, msg or "magick composite front failed"

        rc, msg = _run_magick(
            [str(t1), str(b_r), "-geometry", f"+{x2}+{y2}", "-composite", str(out_pdf)]
        )
        if rc != 0:
            return False, msg or "magick composite back / pdf failed"

    log.info("compose_id_pdf_ok out=%s", out_pdf)
    return True, ""


def apply_ocrmypdf(in_pdf: Path, out_pdf: Path, timeout: float = 300.0) -> tuple[bool, str]:
    """Run ocrmypdf on ``in_pdf`` → ``out_pdf`` (overwrites target)."""
    try:
        proc = subprocess.run(
            [
                "ocrmypdf",
                "--skip-text",
                "--optimize",
                "0",
                str(in_pdf),
                str(out_pdf),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "ocrmypdf not found; install ocrmypdf or disable ID Scan OCR in Admin"
    except subprocess.SubprocessError as e:
        return False, str(e)

    if proc.returncode != 0:
        err = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        return False, err or f"ocrmypdf exit {proc.returncode}"
    log.info("ocrmypdf_ok out=%s", out_pdf)
    return True, ""


def remove_blank_pages_from_pdf(
    in_pdf: Path,
    out_pdf: Path,
    *,
    density: int = 150,
    blank_mean_threshold: float = 0.988,
) -> tuple[bool, str]:
    """
    Rasterize each PDF page with ImageMagick, drop pages whose grayscale mean is above
    ``blank_mean_threshold`` (nearly white). If every page would be removed, keep the first page.
    """
    in_pdf = in_pdf.resolve()
    out_pdf = out_pdf.resolve()
    if not in_pdf.is_file():
        return False, "Missing input PDF"

    with tempfile.TemporaryDirectory(prefix="kopi-blank-") as td:
        tdir = Path(td)
        pattern = str(tdir / "page-%03d.png")
        rc, msg = _run_magick(
            ["-density", str(density), str(in_pdf), pattern],
            timeout=300,
        )
        if rc != 0:
            return False, msg or "magick rasterize failed"

        pages = sorted(tdir.glob("page-*.png"))
        if not pages:
            return False, "No pages rasterized from PDF"

        kept: list[Path] = []
        for p in pages:
            rc_m, mean_s = _run_magick(
                [str(p), "-colorspace", "Gray", "-format", "%[fx:mean]", "info:"],
                timeout=60,
            )
            if rc_m != 0:
                kept.append(p)
                continue
            try:
                mean = float((mean_s or "").strip())
            except ValueError:
                kept.append(p)
                continue
            if mean < blank_mean_threshold:
                kept.append(p)

        if not kept:
            kept = [pages[0]]

        args: list[str] = []
        for k in kept:
            args.append(str(k))
        args.append(str(out_pdf))
        rc2, msg2 = _run_magick(args, timeout=180)
        if rc2 != 0:
            return False, msg2 or "magick rebuild pdf failed"

    log.info("remove_blank_pages_ok kept=%d of %d out=%s", len(kept), len(pages), out_pdf)
    return True, ""


def pdf_to_preview_png_base64(pdf_path: Path, max_width: int = 1200) -> tuple[str | None, str]:
    """Rasterize first PDF page to PNG, return base64 or error."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        png_path = Path(tmp.name)
    try:
        rc, msg = _run_magick(
            [
                "-density",
                "150",
                str(pdf_path),
                "[0]",
                "-resize",
                f"{max_width}x>",
                str(png_path),
            ],
            timeout=90,
        )
        if rc != 0:
            return None, msg or "preview rasterize failed"
        data = png_path.read_bytes()
        return base64.standard_b64encode(data).decode("ascii"), ""
    finally:
        png_path.unlink(missing_ok=True)
