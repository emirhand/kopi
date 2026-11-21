"""Pure-Python PDF blank page detection and removal using pypdf and Pillow."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageStat
from pypdf import PdfReader, PdfWriter


def is_image_blank(
    img: Image.Image,
    *,
    mean_min: float = 248.0,
    stddev_max: float = 6.0,
) -> bool:
    """Return True if an image is nearly uniform white/light background."""
    gray = img.convert("L")
    stat = ImageStat.Stat(gray)
    mean_val = float(stat.mean[0])
    stddev_val = float(stat.stddev[0])
    return mean_val >= mean_min and stddev_val <= stddev_max


def _is_pdf_page_blank(page: object) -> bool:
    """Inspect a pypdf PageObject for embedded images or text to determine if it is blank."""
    images = getattr(page, "images", None)
    if images:
        for img_file in images:
            data = getattr(img_file, "data", b"")
            if not data:
                continue
            try:
                with Image.open(io.BytesIO(data)) as pil_img:
                    if not is_image_blank(pil_img):
                        return False
            except Exception:
                return False
        return True

    extract_text = getattr(page, "extract_text", None)
    if callable(extract_text):
        try:
            text = str(extract_text() or "").strip()
            if text:
                return False
        except Exception:
            return False
    return False


def remove_blank_pages_from_pdf(
    input_pdf: Path,
    output_pdf: Path,
) -> tuple[bool, str | None]:
    """Remove blank pages from ``input_pdf`` and write the result to ``output_pdf``."""
    if not input_pdf.is_file():
        return False, "Input PDF does not exist"

    try:
        reader = PdfReader(str(input_pdf))
        total = len(reader.pages)
        if total == 0:
            return False, "Input PDF has no pages"

        writer = PdfWriter()
        kept = 0
        for page in reader.pages:
            if not _is_pdf_page_blank(page):
                writer.add_page(page)
                kept += 1

        # Never produce an empty 0-page PDF; keep page 1 if all pages looked blank
        if kept == 0:
            writer.add_page(reader.pages[0])

        with output_pdf.open("wb") as f:
            writer.write(f)
        return True, None
    except Exception as e:
        return False, f"Blank page removal error: {e}"
