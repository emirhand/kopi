"""Pure-Python SMTP email sender for scan-to-email workflows (smtplib + email.message)."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from kopi.config import SmtpConfig


def _coerce_smtp_config(smtp: SmtpConfig | dict[str, Any]) -> SmtpConfig:
    if isinstance(smtp, SmtpConfig):
        return smtp
    return SmtpConfig.model_validate(smtp)


def _mime_type_for_filename(filename: str) -> tuple[str, str]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    if ext in ("jpg", "jpeg"):
        return "image", "jpeg"
    if ext == "png":
        return "image", "png"
    if ext in ("tif", "tiff"):
        return "image", "tiff"
    return "application", "pdf"


DEFAULT_EMAIL_BODY = "Attached is your scanned document from Kopi."


def _sanitize_header_text(val: str) -> str:
    return " ".join((val or "").splitlines()).strip()


def send_attachments_email(
    attachments: list[tuple[str, bytes]],
    *,
    to_addr: str,
    subject: str,
    body: str | None = None,
    smtp: SmtpConfig | dict[str, Any],
    timeout_sec: int = 30,
) -> tuple[bool, str | None]:
    """Send one or more scanned document/image attachments via SMTP."""
    cfg = _coerce_smtp_config(smtp)
    host = cfg.host.strip()
    recipient = _sanitize_header_text(to_addr)
    if not recipient or "@" not in recipient:
        return False, "Valid recipient email address is required"
    if not host:
        return False, "SMTP host is not configured in Admin Settings"
    if not attachments:
        return False, "No attachments to send"

    sender = _sanitize_header_text(cfg.from_email or cfg.user or "kopi@localhost")
    clean_subject = _sanitize_header_text(subject) or "Scanned document from Kopi"
    body_text = (body or "").strip() or DEFAULT_EMAIL_BODY

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = clean_subject
    msg.set_content(body_text)

    for filename, payload in attachments:
        maintype, subtype = _mime_type_for_filename(filename)
        msg.add_attachment(
            payload,
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )

    try:
        with smtplib.SMTP(host, int(cfg.port), timeout=timeout_sec) as server:
            server.ehlo()
            if cfg.tls:
                server.starttls()
                server.ehlo()
            if cfg.user.strip():
                server.login(cfg.user.strip(), cfg.password)
            server.send_message(msg)
        return True, None
    except Exception as e:
        return False, f"SMTP error: {e}"


def send_attachment_email(
    payload: bytes,
    *,
    filename: str,
    to_addr: str,
    subject: str,
    body: str | None = None,
    smtp: SmtpConfig | dict[str, Any],
    timeout_sec: int = 30,
) -> tuple[bool, str | None]:
    """Send a single scanned document attachment via SMTP."""
    return send_attachments_email(
        [(filename, payload)],
        to_addr=to_addr,
        subject=subject,
        body=body,
        smtp=smtp,
        timeout_sec=timeout_sec,
    )


def send_pdf_email(
    pdf_bytes: bytes,
    *,
    to_addr: str,
    subject: str,
    body: str | None = None,
    smtp: SmtpConfig | dict[str, Any],
    filename: str = "id-scan.pdf",
) -> tuple[bool, str | None]:
    """Send a PDF attachment via SMTP."""
    return send_attachment_email(
        pdf_bytes,
        filename=filename,
        to_addr=to_addr,
        subject=subject,
        body=body,
        smtp=smtp,
    )
