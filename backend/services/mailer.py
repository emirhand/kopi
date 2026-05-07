"""Send mail with PDF attachment via msmtp."""

from __future__ import annotations

import os
import subprocess
import tempfile
from email.mime.application import MIMEApplication
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


def send_pdf_email(
    pdf_bytes: bytes,
    *,
    to_addr: str,
    subject: str,
    smtp: dict[str, Any],
    timeout_sec: int = 120,
) -> tuple[bool, str]:
    """Build a MIME message and pipe to msmtp -t using a temporary account file."""
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

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename="scan.pdf")
    msg.attach(attachment)

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
