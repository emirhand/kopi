"""Hardware abstraction layer.

Detects whether we're running on the Linux appliance (real scanner/printer)
or a developer machine (Mock implementations) and exposes lazy bridge
singletons via :func:`get_scanner` / :func:`get_printer`.

Mode resolution order:

1. ``KOPI_HARDWARE_MODE`` env var: ``real`` | ``mock`` | ``auto`` (default ``auto``)
2. In ``auto``, return ``REAL`` iff ``os.uname().sysname == "Linux"`` else ``MOCK``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum

from .printer import PrintResult, classify_print_error
from .scanner import ScanResult, build_scanimage_pdf_cmd, classify_scan_error

log = logging.getLogger("kopi.hardware")


class HardwareMode(str, Enum):
    REAL = "real"
    MOCK = "mock"


_MODE_ENV = "KOPI_HARDWARE_MODE"


def detect_mode() -> HardwareMode:
    raw = os.environ.get(_MODE_ENV, "auto").strip().lower()
    if raw == "real":
        return HardwareMode.REAL
    if raw == "mock":
        return HardwareMode.MOCK
    try:
        sysname = os.uname().sysname
    except AttributeError:
        sysname = ""
    return HardwareMode.REAL if sysname == "Linux" else HardwareMode.MOCK


class ScannerBridge(ABC):
    @abstractmethod
    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        device: str | None = None,
        timeout_sec: int = 300,
    ) -> ScanResult: ...


class PrinterBridge(ABC):
    @abstractmethod
    async def print_pdf(
        self,
        pdf_bytes: bytes,
        *,
        duplex: bool = False,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult: ...


def _kill_quiet(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.kill()
    except ProcessLookupError:
        pass


def _content_stream(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return (
        b"BT /F1 24 Tf 72 720 Td ("
        + safe.encode("latin-1", errors="replace")
        + b") Tj ET"
    )


def _compact_stderr(stderr: str, limit: int = 240) -> str:
    compact = re.sub(r"\s+", " ", (stderr or "").strip())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "..."


def _verbose_hardware_errors() -> bool:
    raw = os.environ.get("KOPI_VERBOSE_HARDWARE_ERRORS", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _scan_error_message(
    *,
    err_text: str,
    returncode: int,
    device: str | None,
    cmd: list[str],
) -> str:
    msg = classify_scan_error(err_text) or f"Scanner error: {err_text.strip() or returncode}"
    if "initialize parameter is error" in err_text.lower():
        msg += " Hint: selected scanner entry may be incompatible; try another Canon scanner device in Admin Settings."
    if _verbose_hardware_errors():
        msg += f" [device={device or 'default'} cmd={' '.join(cmd)} stderr={_compact_stderr(err_text)}]"
    return msg


def _build_mock_pdf(text: str) -> bytes:
    """Hand-rolled minimal one-page PDF stamped with ``text``. No external deps."""
    safe = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)[:80]
    stream = _content_stream(safe)
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
        + f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


class RealScannerBridge(ScannerBridge):
    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        device: str | None = None,
        timeout_sec: int = 300,
    ) -> ScanResult:
        cmd = build_scanimage_pdf_cmd(
            duplex_scan=duplex,
            device=device,
            include_resolution=True,
            include_mode=True,
        )
        log.info("scan_start mode=real duplex=%s device=%r cmd=%s", duplex, device, " ".join(cmd))

        async def run_once(run_cmd: list[str]) -> tuple[int, bytes, str]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as e:
                log.error("scan_fail mode=real reason=binary_missing err=%s", e)
                return 127, b"", str(e)

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                log.error("scan_timeout mode=real timeout=%ss cmd=%s", timeout_sec, " ".join(run_cmd))
                _kill_quiet(proc)
                await proc.wait()
                return 124, b"", "timeout"
            return proc.returncode, stdout, (stderr or b"").decode(errors="replace")

        rc, stdout, err_text = await run_once(cmd)
        if rc == 127:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Not Found")
        if rc == 124:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Busy")

        if rc != 0 and "--resolution" in err_text and "unrecognized option" in err_text:
            fallback_cmd = build_scanimage_pdf_cmd(
                duplex_scan=duplex,
                device=device,
                include_resolution=False,
                include_mode=True,
            )
            log.warning("scan_retry_no_resolution mode=real device=%r cmd=%s", device, " ".join(fallback_cmd))
            rc, stdout, err_text = await run_once(fallback_cmd)
            cmd = fallback_cmd

        if rc != 0 and "initialize parameter is error" in err_text.lower():
            safe_cmd = build_scanimage_pdf_cmd(
                duplex_scan=False,
                device=device,
                include_resolution=False,
                include_mode=False,
                source="Flatbed",
                include_output_file_flag=False,
            )
            log.warning("scan_retry_safe_profile mode=real device=%r cmd=%s", device, " ".join(safe_cmd))
            rc, stdout, err_text = await run_once(safe_cmd)
            cmd = safe_cmd

        if rc == 127:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Not Found")
        if rc == 124:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Busy")
        if rc != 0:
            msg = _scan_error_message(
                err_text=err_text,
                returncode=rc,
                device=device,
                cmd=cmd,
            )
            log.error("scan_fail mode=real rc=%s msg=%r", rc, msg)
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)
        if not stdout:
            no_data_cmd = build_scanimage_pdf_cmd(
                duplex_scan=False,
                device=device,
                include_resolution=False,
                include_mode=False,
                source="Flatbed",
                include_output_file_flag=False,
            )
            log.warning("scan_retry_no_data_flatbed mode=real device=%r cmd=%s", device, " ".join(no_data_cmd))
            retry_rc, retry_stdout, retry_err = await run_once(no_data_cmd)
            if retry_rc == 0 and retry_stdout:
                log.info("scan_ok mode=real retry=no_data_flatbed bytes=%d", len(retry_stdout))
                return ScanResult(ok=True, stdout=retry_stdout, stderr=retry_err, user_message=None)

            msg = classify_scan_error(retry_err or err_text) or "Scanner returned no data"
            if _verbose_hardware_errors():
                msg += (
                    f" [device={device or 'default'} cmd={' '.join(cmd)} "
                    f"fallback_cmd={' '.join(no_data_cmd)} stderr={_compact_stderr(retry_err or err_text)}]"
                )
            log.error("scan_fail mode=real reason=empty msg=%r", msg)
            return ScanResult(ok=False, stdout=b"", stderr=(retry_err or err_text), user_message=msg)

        log.info("scan_ok mode=real bytes=%d", len(stdout))
        return ScanResult(ok=True, stdout=stdout, stderr=err_text, user_message=None)


class RealPrinterBridge(PrinterBridge):
    async def print_pdf(
        self,
        pdf_bytes: bytes,
        *,
        duplex: bool = False,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        cmd: list[str] = ["lp", "-t", job_name]
        if duplex:
            cmd.extend(["-o", "sides=two-sided-long-edge"])
        dest = device or os.environ.get("CUPS_DEST")
        if dest:
            cmd.extend(["-d", dest])

        log.info(
            "print_start mode=real duplex=%s device=%r bytes=%d cmd=%s",
            duplex,
            device,
            len(pdf_bytes),
            " ".join(cmd),
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            log.error("print_fail mode=real reason=binary_missing err=%s", e)
            return PrintResult(
                ok=False, stderr=str(e), user_message="Printer Not Found"
            )

        try:
            _stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=pdf_bytes), timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            log.error("print_timeout mode=real timeout=%ss", timeout_sec)
            _kill_quiet(proc)
            await proc.wait()
            return PrintResult(
                ok=False, stderr="timeout", user_message="Printer Busy"
            )

        err_text = (stderr or b"").decode(errors="replace")
        if proc.returncode != 0:
            msg = (
                classify_print_error(err_text)
                or f"Print error: {err_text.strip() or proc.returncode}"
            )
            log.error("print_fail mode=real rc=%s msg=%r", proc.returncode, msg)
            return PrintResult(ok=False, stderr=err_text, user_message=msg)

        log.info("print_ok mode=real")
        return PrintResult(ok=True, stderr=err_text, user_message=None)


class MockScannerBridge(ScannerBridge):
    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        device: str | None = None,
        timeout_sec: int = 300,
    ) -> ScanResult:
        _ = timeout_sec
        delay = random.uniform(3.0, 5.0)
        log.info(
            "scan_start mode=mock duplex=%s device=%r delay=%.2fs",
            duplex,
            device,
            delay,
        )
        await asyncio.sleep(delay)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        body = f"MOCK SCAN {ts}{' (duplex)' if duplex else ''}"
        pdf = _build_mock_pdf(body)
        log.info("scan_ok mode=mock bytes=%d", len(pdf))
        return ScanResult(ok=True, stdout=pdf, stderr="", user_message=None)


class MockPrinterBridge(PrinterBridge):
    async def print_pdf(
        self,
        pdf_bytes: bytes,
        *,
        duplex: bool = False,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        delay = random.uniform(1.0, 2.0)
        cmd_preview = ["lp", "-t", "application/pdf", "-J", job_name]
        if duplex:
            cmd_preview.extend(["-o", "sides=two-sided-long-edge"])
        log.info(
            "print_start mode=mock duplex=%s device=%r bytes=%d cmd=%s delay=%.2fs",
            duplex,
            device,
            len(pdf_bytes),
            " ".join(cmd_preview),
            delay,
        )
        await asyncio.sleep(delay)
        log.info("print_ok mode=mock")
        return PrintResult(ok=True, stderr="", user_message=None)


_scanner: ScannerBridge | None = None
_printer: PrinterBridge | None = None


def get_scanner() -> ScannerBridge:
    global _scanner
    if _scanner is None:
        mode = detect_mode()
        log.info("scanner_bridge_init mode=%s", mode.value)
        _scanner = (
            RealScannerBridge() if mode is HardwareMode.REAL else MockScannerBridge()
        )
    return _scanner


def get_printer() -> PrinterBridge:
    global _printer
    if _printer is None:
        mode = detect_mode()
        log.info("printer_bridge_init mode=%s", mode.value)
        _printer = (
            RealPrinterBridge() if mode is HardwareMode.REAL else MockPrinterBridge()
        )
    return _printer


def reset_bridges() -> None:
    """Reset the cached singletons. Intended for tests."""
    global _scanner, _printer
    _scanner = None
    _printer = None
