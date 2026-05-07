"""SANE / scanimage subprocess wrapper."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Final

_NO_PAPER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"out\s+of\s+paper", re.I),
    re.compile(r"no\s+paper", re.I),
    re.compile(r"document\s+feeder\s+out\s+of\s+documents", re.I),
    re.compile(r"no\s+documents", re.I),
    re.compile(r"empty\s+(feeder|adf)", re.I),
)
_BUSY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"device\s+busy", re.I),
    re.compile(r"scanner\s+busy", re.I),
    re.compile(r"resource\s+busy", re.I),
    re.compile(r"could\s+not\s+open\s+device", re.I),
)


@dataclass(frozen=True)
class ScanResult:
    ok: bool
    stdout: bytes
    stderr: str
    user_message: str | None


def classify_scan_error(stderr: str) -> str | None:
    text = stderr or ""
    for pat in _NO_PAPER_PATTERNS:
        if pat.search(text):
            return "No Paper"
    for pat in _BUSY_PATTERNS:
        if pat.search(text):
            return "Scanner Busy"
    return None


def build_scanimage_pdf_cmd(*, duplex_scan: bool = False, device: str | None = None) -> list[str]:
    """Arguments for `scanimage` emitting PDF on stdout (ends with `-o -`)."""
    env = os.environ.copy()
    cmd: list[str] = ["scanimage", "--format=pdf", "--mode=Color", "--resolution", "300"]

    dev = device or env.get("SCAN_DEVICE")
    if dev:
        cmd.extend(["-d", dev])

    if duplex_scan:
        cmd.extend(["--source", "ADF", "--duplex"])

    extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())

    cmd.extend(["-o", "-"])
    return cmd


def scan_pdf_to_stdout(
    *,
    duplex_scan: bool = False,
    device: str | None = None,
    timeout_sec: int = 300,
) -> ScanResult:
    """
    Run scanimage and capture PDF bytes on stdout.
    Duplex ADF flags are best-effort; backends differ (override with SCANIMAGE_EXTRA_ARGS).
    """
    env = os.environ.copy()
    cmd = build_scanimage_pdf_cmd(duplex_scan=duplex_scan, device=device)

    proc = subprocess.run(cmd, capture_output=True, timeout=timeout_sec, env=env)
    stderr = (proc.stderr or b"").decode(errors="replace")
    if proc.returncode != 0:
        msg = classify_scan_error(stderr) or f"Scanner error: {stderr.strip() or proc.returncode}"
        return ScanResult(ok=False, stdout=b"", stderr=stderr, user_message=msg)
    if not proc.stdout:
        msg = classify_scan_error(stderr) or "Scanner returned no data"
        return ScanResult(ok=False, stdout=b"", stderr=stderr, user_message=msg)
    return ScanResult(ok=True, stdout=proc.stdout, stderr=stderr, user_message=None)
