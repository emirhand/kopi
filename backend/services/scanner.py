"""SANE / scanimage façade — delegates to :mod:`services.hardware`."""

from __future__ import annotations

import logging
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

log = logging.getLogger("kopi.scanner")


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


def build_scanimage_pdf_cmd(
    *,
    duplex_scan: bool = False,
    device: str | None = None,
    include_resolution: bool = True,
) -> list[str]:
    """Arguments for `scanimage` emitting PDF on stdout (ends with `-o -`)."""
    env = os.environ.copy()
    cmd: list[str] = ["scanimage", "--format=pdf", "--mode=Color"]
    if include_resolution:
        cmd.extend(["--resolution", env.get("SCAN_RESOLUTION", "300")])

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


def list_scan_devices(timeout_sec: int = 8) -> list[str]:
    """Return scanner device names from `scanimage -L` output."""
    try:
        proc = subprocess.run(
            ["scanimage", "-L"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    devices: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^device\s+`([^`]+)`\s+is\b", line)
        if not m:
            continue
        devices.append(m.group(1))
    return devices


async def scan_pdf(
    *,
    duplex: bool = False,
    device: str | None = None,
    timeout_sec: int = 300,
) -> ScanResult:
    """Run ``scanimage`` (or Mock) and capture PDF bytes on stdout."""
    from .hardware import get_scanner

    result = await get_scanner().scan_pdf(
        duplex=duplex, device=device, timeout_sec=timeout_sec
    )
    log.info(
        "scan_facade duplex=%s ok=%s bytes=%d user_message=%r",
        duplex,
        result.ok,
        len(result.stdout) if result.ok else 0,
        result.user_message,
    )
    return result
