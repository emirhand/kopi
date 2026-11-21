"""Pure-Python A4 ID Card layout composer and preview renderer (Pillow + img2pdf + pypdf)."""

from __future__ import annotations

import base64
import io
import subprocess
from pathlib import Path

import img2pdf
from PIL import Image, ImageOps
from pypdf import PdfReader

# 300 DPI A4 dimensions (210mm x 297mm)
_A4_WIDTH_PX = 2480
_A4_HEIGHT_PX = 3508

# Standard ID-1 card (85.6mm x 54mm) at 300 DPI -> ~1011 x 638 px
_CARD_WIDTH_PX = 1016
_CARD_HEIGHT_PX = 638


def compose_id_scans_to_a4_pdf(
    front_png: Path,
    back_png: Path,
    output_pdf: Path,
) -> tuple[bool, str | None]:
    """Place front and back ID card images centered vertically on a single A4 PDF page."""
    if not front_png.is_file() or not back_png.is_file():
        return False, "Front or back ID scan file is missing"

    try:
        canvas = Image.new("RGB", (_A4_WIDTH_PX, _A4_HEIGHT_PX), color=(255, 255, 255))

        with Image.open(front_png) as f_src, Image.open(back_png) as b_src:
            front_img = f_src.convert("RGB").resize(
                (_CARD_WIDTH_PX, _CARD_HEIGHT_PX), Image.Resampling.LANCZOS
            )
            back_img = b_src.convert("RGB").resize(
                (_CARD_WIDTH_PX, _CARD_HEIGHT_PX), Image.Resampling.LANCZOS
            )

        front_bordered = ImageOps.expand(front_img, border=2, fill=(180, 180, 180))
        back_bordered = ImageOps.expand(back_img, border=2, fill=(180, 180, 180))

        x_front = (_A4_WIDTH_PX - front_bordered.width) // 2
        y_front = int(_A4_HEIGHT_PX * 0.22)

        x_back = (_A4_WIDTH_PX - back_bordered.width) // 2
        y_back = int(_A4_HEIGHT_PX * 0.54)

        canvas.paste(front_bordered, (x_front, y_front))
        canvas.paste(back_bordered, (x_back, y_back))

        png_buf = io.BytesIO()
        canvas.save(png_buf, format="PNG", dpi=(300, 300))

        a4_pt = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
        layout_fun = img2pdf.get_layout_fun(a4_pt)
        pdf_bytes = img2pdf.convert(png_buf.getvalue(), layout_fun=layout_fun)
        if not pdf_bytes:
            return False, "Failed to convert composed A4 canvas to PDF"

        output_pdf.write_bytes(pdf_bytes)
        return True, None
    except Exception as e:
        return False, f"ID card composition failed: {e}"


def pdf_to_preview_png_base64(
    pdf_path: Path,
    *,
    max_width: int = 900,
) -> tuple[str | None, str | None]:
    """Extract the first page image from a composed PDF and return base64 PNG preview."""
    if not pdf_path.is_file():
        return None, "PDF file not found"

    try:
        reader = PdfReader(str(pdf_path))
        if not reader.pages:
            return None, "PDF has no pages"
        images = reader.pages[0].images
        if not images:
            return None, "No embedded image found in PDF page"

        with Image.open(io.BytesIO(images[0].data)) as src:
            w, h = src.size
            if w > max_width:
                ratio = max_width / float(w)
                preview_img: Image.Image = src.resize(
                    (max_width, max(1, int(round(h * ratio)))),
                    Image.Resampling.LANCZOS,
                )
            else:
                preview_img = src.copy()

            out_buf = io.BytesIO()
            preview_img.save(out_buf, format="PNG")
            encoded = base64.b64encode(out_buf.getvalue()).decode("ascii")
            return encoded, None
    except Exception as e:
        return None, f"Preview extraction failed: {e}"


def apply_ocrmypdf(
    input_pdf: Path,
    output_pdf: Path,
    *,
    timeout_sec: int = 120,
) -> tuple[bool, str | None]:
    """Run optional `ocrmypdf` CLI on a composed PDF when enabled in Admin settings."""
    try:
        proc = subprocess.run(
            ["ocrmypdf", "--skip-text", str(input_pdf), str(output_pdf)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError:
        return False, "ocrmypdf is not installed on the server"
    except subprocess.TimeoutExpired:
        return False, "ocrmypdf timed out"
    except OSError as e:
        return False, str(e)

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, f"ocrmypdf failed: {err or proc.returncode}"
    return True, None
