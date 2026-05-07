"""CUPS / lp subprocess wrapper."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Final

_NO_PAPER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"no\s+paper", re.I),
    re.compile(r"paper\s+out", re.I),
    re.compile(r"media\s+empty", re.I),
    re.compile(r"load\s+paper", re.I),
)
_BUSY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"printer\s+is\s+busy", re.I),
    re.compile(r"not\s+accepting\s+jobs", re.I),
)


@dataclass(frozen=True)
class PrintResult:
    ok: bool
    stderr: str
    user_message: str | None


def _classify_lp_error(stderr: str) -> str | None:
    text = stderr or ""
    for pat in _NO_PAPER_PATTERNS:
        if pat.search(text):
            return "No Paper"
    for pat in _BUSY_PATTERNS:
        if pat.search(text):
            return "Printer Busy"
    return None


def print_pdf_stream(
    pdf_bytes: bytes,
    *,
    duplex: bool = False,
    job_name: str = "kiosk-copy",
    timeout_sec: int = 120,
) -> PrintResult:
    """Send a PDF to the default (or CUPS_DEST) queue via lp."""
    env = os.environ.copy()
    cmd: list[str] = ["lp", "-t", "application/pdf", "-J", job_name]
    if duplex:
        cmd.extend(["-o", "sides=two-sided-long-edge"])
    dest = env.get("CUPS_DEST")
    if dest:
        cmd.extend(["-d", dest])

    proc = subprocess.run(
        cmd,
        input=pdf_bytes,
        capture_output=True,
        timeout=timeout_sec,
        env=env,
    )
    stderr = (proc.stderr or b"").decode(errors="replace")
    if proc.returncode != 0:
        msg = _classify_lp_error(stderr) or f"Print error: {stderr.strip() or proc.returncode}"
        return PrintResult(ok=False, stderr=stderr, user_message=msg)
    return PrintResult(ok=True, stderr=stderr, user_message=None)


def print_from_scanimage_pipe(
    *,
    duplex: bool = False,
    scan_cmd: list[str],
    timeout_sec: int = 300,
) -> PrintResult:
    """
    Pipe scanimage directly to lp: scanimage ... | lp ...
    scan_cmd should be the full scanimage argument list (including output to stdout).
    """
    env = os.environ.copy()
    scan = subprocess.Popen(
        scan_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    lp_cmd: list[str] = ["lp", "-t", "application/pdf", "-J", "kiosk-copy-pipe"]
    if duplex:
        lp_cmd.extend(["-o", "sides=two-sided-long-edge"])
    dest = env.get("CUPS_DEST")
    if dest:
        lp_cmd.extend(["-d", dest])

    lp = subprocess.Popen(
        lp_cmd,
        stdin=scan.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if scan.stdout:
        scan.stdout.close()

    _, lp_err = lp.communicate(timeout=timeout_sec)
    scan_err_b = b""
    if scan.stderr:
        scan_err_b = scan.stderr.read() or b""
    scan.wait(timeout=5)

    stderr = (lp_err or b"").decode(errors="replace")
    scan_stderr = scan_err_b.decode(errors="replace")
    combined = f"{scan_stderr}\n{stderr}".strip()

    if scan.returncode not in (0, None):
        from .scanner import classify_scan_error

        msg = classify_scan_error(scan_stderr) or f"Scan error: {scan_stderr.strip() or scan.returncode}"
        return PrintResult(ok=False, stderr=combined, user_message=msg)

    if lp.returncode != 0:
        msg = _classify_lp_error(stderr) or f"Print error: {stderr.strip() or lp.returncode}"
        return PrintResult(ok=False, stderr=combined, user_message=msg)

    return PrintResult(ok=True, stderr=combined, user_message=None)
