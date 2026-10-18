"""CUPS / lp printer implementation (Real & Mock)."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Final

from .base import DuplexMode, PrinterBridge, PrintResult

log = logging.getLogger("kopi.printer")

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


def classify_print_error(stderr: str) -> str | None:
    """Classify CUPS lp stderr output into a user-facing error category."""
    text = stderr or ""
    for pat in _NO_PAPER_PATTERNS:
        if pat.search(text):
            return "No Paper"
    for pat in _BUSY_PATTERNS:
        if pat.search(text):
            return "Printer Busy"
    return None


def _resolve_duplex_option(duplex: bool | DuplexMode) -> str | None:
    if isinstance(duplex, DuplexMode):
        if duplex is DuplexMode.NONE:
            return None
        return str(duplex.value)
    if duplex:
        return str(DuplexMode.LONG_EDGE.value)
    return None


def build_lp_cmd(
    file_path: str,
    *,
    job_name: str = "kopi-job",
    device: str | None = None,
    copies: int = 1,
    duplex: bool | DuplexMode = False,
    color: bool = True,
    paper_size: str | None = None,
    collate: bool | None = None,
    resize_mode: str | None = None,
    quality: str | None = None,
) -> list[str]:
    """Construct the `lp` command argv for a print/copy job."""
    cmd: list[str] = ["lp", "-t", job_name]
    dest = (device or os.environ.get("CUPS_DEST") or "").strip()
    if dest:
        cmd.extend(["-d", dest])

    safe_copies = max(1, min(99, int(copies)))
    if safe_copies > 1:
        cmd.extend(["-n", str(safe_copies)])
        if collate is not None:
            cmd.extend(["-o", f"collate={'true' if collate else 'false'}"])

    sides_opt = _resolve_duplex_option(duplex)
    if sides_opt:
        cmd.extend(["-o", f"sides={sides_opt}"])

    if not color:
        cmd.extend(["-o", "ColorModel=Gray"])

    if paper_size and paper_size.strip():
        cmd.extend(["-o", f"media={paper_size.strip()}"])

    if resize_mode:
        rmode = resize_mode.strip().lower()
        if rmode == "fit_to_page":
            cmd.extend(["-o", "fit-to-page"])
        elif rmode == "two_on_one":
            cmd.extend(["-o", "number-up=2"])

    if quality:
        q = quality.strip().lower()
        if q == "draft":
            cmd.extend(["-o", "print-quality=3"])
        elif q == "normal":
            cmd.extend(["-o", "print-quality=4"])
        elif q == "best":
            cmd.extend(["-o", "print-quality=5"])

    cmd.append(file_path)
    return cmd


def list_printer_queues(timeout_sec: int = 8) -> list[str]:
    """Return available CUPS destination names."""

    def _run(cmd: list[str]) -> str:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            return (proc.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    destinations: list[str] = []
    for output in (_run(["lpstat", "-a"]), _run(["lpstat", "-e"])):
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            dest = line.split()[0]
            if dest:
                destinations.append(dest)
    return sorted(dict.fromkeys(destinations))


def _kill_quiet(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _mock_delay(default_sec: float = 0.15) -> float:
    raw = os.environ.get("KOPI_MOCK_DELAY_SEC", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return default_sec


class RealPrinterBridge(PrinterBridge):
    def __init__(self) -> None:
        self._last_job_id: str | None = None
        self._last_destination: str | None = None

    async def cancel_print(self, job_id: str | None = None) -> bool:
        """Cancel the active CUPS job; the page already in the printer paper path will finish ejecting."""
        target_job = (job_id or self._last_job_id or "").strip()
        cmd = ["cancel", target_job] if target_job else ["cancel", "-a"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15)
            log.info("print_cancel mode=real cmd=%s rc=%s", " ".join(cmd), proc.returncode)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, OSError):
            return False

    async def print_pdf(
        self,
        pdf_bytes: bytes,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        collate: bool | None = None,
        resize_mode: str | None = None,
        quality: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
        try:
            return await self.print_file(
                str(tmp_path),
                copies=copies,
                duplex=duplex,
                color=color,
                paper_size=paper_size,
                collate=collate,
                resize_mode=resize_mode,
                quality=quality,
                job_name=job_name,
                device=device,
                timeout_sec=timeout_sec,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

    async def print_file(
        self,
        file_path: str,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        collate: bool | None = None,
        resize_mode: str | None = None,
        quality: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        cmd = build_lp_cmd(
            file_path,
            job_name=job_name,
            device=device,
            copies=copies,
            duplex=duplex,
            color=color,
            paper_size=paper_size,
            collate=collate,
            resize_mode=resize_mode,
            quality=quality,
        )
        dest = (device or os.environ.get("CUPS_DEST") or "").strip()
        log.info("print_start mode=real cmd=%s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            return PrintResult(ok=False, stderr=str(e), user_message="Printer Not Found")

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            _kill_quiet(proc)
            await proc.wait()
            return PrintResult(ok=False, stderr="timeout", user_message="Printer Busy")

        out_text = (stdout or b"").decode(errors="replace")
        err_text = (stderr or b"").decode(errors="replace")
        if proc.returncode != 0:
            msg = (
                classify_print_error(err_text)
                or f"Print error: {err_text.strip() or proc.returncode}"
            )
            return PrintResult(
                ok=False,
                stderr=err_text,
                user_message=msg,
                stdout=out_text,
                destination=dest,
            )

        job_match = re.search(r"request id is (\S+)", out_text)
        job_id = job_match.group(1) if job_match else ""
        self._last_job_id = job_id or None
        self._last_destination = dest or None
        return PrintResult(
            ok=True,
            stderr=err_text,
            user_message=None,
            stdout=out_text,
            job_id=job_id,
            destination=dest,
        )


class MockPrinterBridge(PrinterBridge):
    async def cancel_print(self, job_id: str | None = None) -> bool:
        _ = job_id
        return True

    async def print_pdf(
        self,
        pdf_bytes: bytes,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        collate: bool | None = None,
        resize_mode: str | None = None,
        quality: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        _ = (
            pdf_bytes,
            copies,
            duplex,
            color,
            paper_size,
            collate,
            resize_mode,
            quality,
            job_name,
            timeout_sec,
        )
        await asyncio.sleep(_mock_delay())
        return PrintResult(
            ok=True,
            stderr="",
            user_message=None,
            job_id="mock-job-1",
            destination=device or "mock-printer",
        )

    async def print_file(
        self,
        file_path: str,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        collate: bool | None = None,
        resize_mode: str | None = None,
        quality: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        _ = (
            file_path,
            copies,
            duplex,
            color,
            paper_size,
            collate,
            resize_mode,
            quality,
            job_name,
            timeout_sec,
        )
        await asyncio.sleep(_mock_delay())
        return PrintResult(
            ok=True,
            stderr="",
            user_message=None,
            job_id="mock-job-1",
            destination=device or "mock-printer",
        )
