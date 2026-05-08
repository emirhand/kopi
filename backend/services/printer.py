"""CUPS / lp façade — delegates to :mod:`services.hardware`."""

from __future__ import annotations

import logging
import re
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

log = logging.getLogger("kopi.printer")


@dataclass(frozen=True)
class PrintResult:
    ok: bool
    stderr: str
    user_message: str | None


def classify_print_error(stderr: str) -> str | None:
    text = stderr or ""
    for pat in _NO_PAPER_PATTERNS:
        if pat.search(text):
            return "No Paper"
    for pat in _BUSY_PATTERNS:
        if pat.search(text):
            return "Printer Busy"
    return None


async def print_pdf(
    pdf_bytes: bytes,
    *,
    duplex: bool = False,
    job_name: str = "kopi-copy",
    timeout_sec: int = 120,
) -> PrintResult:
    """Send ``pdf_bytes`` to the default (or ``CUPS_DEST``) queue via ``lp``."""
    from .hardware import get_printer

    result = await get_printer().print_pdf(
        pdf_bytes,
        duplex=duplex,
        job_name=job_name,
        timeout_sec=timeout_sec,
    )
    log.info(
        "print_facade duplex=%s ok=%s user_message=%r",
        duplex,
        result.ok,
        result.user_message,
    )
    return result
