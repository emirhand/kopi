"""Send mail with PDF attachment via msmtp."""

from __future__ import annotations

import os
import subprocess
import tempfile
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any


def _write_msmtprc(
    path: Path,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    from_email: str,
    tls: bool,
) -> None:
    tls_on = "on" if tls else "off"
    starttls = "on" if tls else "off"
    content = f"""defaults
auth on
tls {tls_on}
tls_starttls {starttls}
logfile /dev/null

account kiosk
host {host}
port {port}
from {from_email}
user {user}
password {password}

account default : kiosk
"""
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)


def _attachment_part(data: bytes, filename: str) -> MIMEApplication | MIMEImage:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        part: MIMEApplication | MIMEImage = MIMEApplication(data, _subtype="pdf")
    elif lower.endswith((".jpg", ".jpeg")):
        part = MIMEImage(data, _subtype="jpeg")
    else:
        part = MIMEApplication(data, _subtype="octet-stream")
    part.add_header("Content-Disposition", "attachment", filename=filename)
    return part


def send_pdf_email(
    pdf_bytes: bytes,
    *,
    to_addr: str,
    subject: str,
    smtp: dict[str, Any],
    timeout_sec: int = 120,
) -> tuple[bool, str]:
    """Build a MIME message and pipe to msmtp -t using a temporary account file."""
    return send_attachment_email(
        pdf_bytes,
        filename="scan.pdf",
        to_addr=to_addr,
        subject=subject,
        smtp=smtp,
        timeout_sec=timeout_sec,
    )


def send_attachment_email(
    data: bytes,
    *,
    filename: str,
    to_addr: str,
    subject: str,
    smtp: dict[str, Any],
    timeout_sec: int = 120,
) -> tuple[bool, str]:
    """Send one attachment (PDF or JPEG) via msmtp."""
    host = str(smtp.get("host", "")).strip()
    port = int(smtp.get("port", 587))
    user = str(smtp.get("user", ""))
    password = str(smtp.get("password", ""))
    from_email = str(smtp.get("from_email", user or "copier@localhost"))
    tls = bool(smtp.get("tls", True))

    if not host:
        return False, "SMTP host is not configured"

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_addr
    msg.attach(MIMEText("Scan attached.", "plain", "utf-8"))
    msg.attach(_attachment_part(data, filename))

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".msmtprc",
        delete=False,
    ) as tmp:
        rc_path = Path(tmp.name)

    try:
        _write_msmtprc(
            rc_path,
            host=host,
            port=port,
            user=user,
            password=password,
            from_email=from_email,
            tls=tls,
        )
        env = os.environ.copy()
        proc = subprocess.run(
            ["msmtp", "--file", str(rc_path), "-t"],
            input=msg.as_bytes(),
            capture_output=True,
            timeout=timeout_sec,
            env=env,
        )
        err = (proc.stderr or b"").decode(errors="replace")
        if proc.returncode != 0:
            return False, f"Mail error: {err.strip() or proc.returncode}"
        return True, ""
    finally:
        try:
            rc_path.unlink(missing_ok=True)
        except OSError:
            pass
