"""Pure-Python image, PDF, ID card, and SMTP processing utilities for Kopi."""

from .copy_enhance import apply_copy_enhancements_to_image, enhance_scanned_image_file
from .id_card import (
    apply_ocrmypdf,
    compose_id_scans_to_a4_pdf,
    pdf_to_preview_png_base64,
)
from .mailer import send_attachment_email, send_pdf_email
from .pdf import is_image_blank, remove_blank_pages_from_pdf

__all__ = [
    "apply_copy_enhancements_to_image",
    "apply_ocrmypdf",
    "compose_id_scans_to_a4_pdf",
    "enhance_scanned_image_file",
    "is_image_blank",
    "pdf_to_preview_png_base64",
    "remove_blank_pages_from_pdf",
    "send_attachment_email",
    "send_pdf_email",
]
