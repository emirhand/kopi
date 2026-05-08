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
from .scanner import (
    SCANNER_BUSY_RECOVERY_HINT,
    ScanResult,
    ScanFileResult,
    build_scanimage_document_cmd,
    busy_retry_settings,
    classify_scan_error,
    is_scanner_busy_error,
)

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
        resolution_dpi: int = 300,
        color: bool = True,
        output_format: str = "pdf",
    ) -> ScanResult: ...

    @abstractmethod
    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult: ...


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

    @abstractmethod
    async def print_file(
        self,
        file_path: str,
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
    classified = classify_scan_error(err_text)
    if classified == "Scanner Busy":
        msg = "Scanner Busy." + SCANNER_BUSY_RECOVERY_HINT
    else:
        msg = classified or f"Scanner error: {err_text.strip() or returncode}"
    if "initialize parameter is error" in err_text.lower():
        msg += " Hint: selected scanner entry may be incompatible; try another Canon scanner device in Admin Settings."
    if _verbose_hardware_errors():
        msg += f" [device={device or 'default'} cmd={' '.join(cmd)} stderr={_compact_stderr(err_text)}]"
    return msg


def _normalize_pdf_bytes(raw: bytes) -> bytes:
    """Trim scanner stdout to the first complete PDF envelope."""
    if not raw:
        return b""
    start = raw.find(b"%PDF-")
    if start < 0:
        return raw
    end = raw.rfind(b"%%EOF")
    if end < 0 or end < start:
        return raw
    return raw[start : end + len(b"%%EOF")]


def _trim_jpeg_bytes(raw: bytes) -> bytes:
    """Trim scanner stdout to one JPEG SOI…EOI envelope."""
    if not raw.startswith(b"\xff\xd8"):
        return raw
    end = raw.rfind(b"\xff\xd9")
    if end < 0:
        return raw
    return raw[: end + 2]


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
        resolution_dpi: int = 300,
        color: bool = True,
        output_format: str = "pdf",
    ) -> ScanResult:
        fmt_key = "jpeg" if output_format.lower() in ("jpg", "jpeg") else "pdf"
        cmd = build_scanimage_document_cmd(
            duplex_scan=duplex,
            device=device,
            output_format=output_format,
            resolution_dpi=resolution_dpi,
            color=color,
            include_resolution=True,
            include_mode=True,
        )
        log.info(
            "scan_start mode=real duplex=%s fmt=%s dpi=%s color=%s device=%r cmd=%s",
            duplex,
            fmt_key,
            resolution_dpi,
            color,
            device,
            " ".join(cmd),
        )

        async def run_once_raw(run_cmd: list[str]) -> tuple[int, bytes, str]:
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
            return proc.returncode, stdout or b"", (stderr or b"").decode(errors="replace")

        max_r, delay_s = busy_retry_settings()

        async def run_once(run_cmd: list[str]) -> tuple[int, bytes, str]:
            """Re-run on transient SANE ‘device busy’ (common after mis-feeds)."""
            last: tuple[int, bytes, str] = (1, b"", "")
            for attempt in range(max_r + 1):
                rc, out, err = await run_once_raw(run_cmd)
                last = (rc, out, err)
                if rc == 0 or rc == 127 or rc == 124:
                    return rc, out, err
                if not is_scanner_busy_error(err):
                    return rc, out, err
                if attempt < max_r:
                    log.warning(
                        "scan_retry_device_busy mode=real attempt=%s/%s delay=%ss stderr=%s",
                        attempt + 1,
                        max_r,
                        delay_s,
                        _compact_stderr(err),
                    )
                    await asyncio.sleep(delay_s)
            return last

        rc, stdout, err_text = await run_once(cmd)
        if rc == 127:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Not Found")
        if rc == 124:
            return ScanResult(
                ok=False,
                stdout=b"",
                stderr=err_text,
                user_message="Scanner Busy." + SCANNER_BUSY_RECOVERY_HINT,
            )

        if rc != 0 and "--resolution" in err_text and "unrecognized option" in err_text:
            fallback_cmd = build_scanimage_document_cmd(
                duplex_scan=duplex,
                device=device,
                output_format=output_format,
                resolution_dpi=resolution_dpi,
                color=color,
                include_resolution=False,
                include_mode=True,
            )
            log.warning("scan_retry_no_resolution mode=real device=%r cmd=%s", device, " ".join(fallback_cmd))
            rc, stdout, err_text = await run_once(fallback_cmd)
            cmd = fallback_cmd

        if rc != 0 and "initialize parameter is error" in err_text.lower():
            safe_cmd = build_scanimage_document_cmd(
                duplex_scan=False,
                device=device,
                output_format=output_format,
                resolution_dpi=resolution_dpi,
                color=color,
                include_resolution=False,
                include_mode=False,
            )
            log.warning("scan_retry_safe_profile mode=real device=%r cmd=%s", device, " ".join(safe_cmd))
            rc, stdout, err_text = await run_once(safe_cmd)
            cmd = safe_cmd

        if rc == 127:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Scanner Not Found")
        if rc == 124:
            return ScanResult(
                ok=False,
                stdout=b"",
                stderr=err_text,
                user_message="Scanner Busy." + SCANNER_BUSY_RECOVERY_HINT,
            )
        if rc != 0:
            msg = _scan_error_message(
                err_text=err_text,
                returncode=rc,
                device=device,
                cmd=cmd,
            )
            log.error("scan_fail mode=real rc=%s msg=%r", rc, msg)
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)

        if fmt_key == "pdf":
            stdout = _normalize_pdf_bytes(stdout)
        else:
            stdout = _trim_jpeg_bytes(stdout)

        if not stdout:
            no_data_cmd = build_scanimage_document_cmd(
                duplex_scan=False,
                device=device,
                output_format=output_format,
                resolution_dpi=resolution_dpi,
                color=color,
                include_resolution=False,
                include_mode=False,
            )
            log.warning("scan_retry_no_data_flatbed mode=real device=%r cmd=%s", device, " ".join(no_data_cmd))
            retry_rc, retry_stdout, retry_err = await run_once(no_data_cmd)
            if retry_rc == 0 and retry_stdout:
                if fmt_key == "pdf":
                    retry_stdout = _normalize_pdf_bytes(retry_stdout)
                else:
                    retry_stdout = _trim_jpeg_bytes(retry_stdout)
                if retry_stdout:
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

        if fmt_key == "pdf":
            if not stdout.startswith(b"%PDF-") or b"%%EOF" not in stdout:
                msg = "Scanner returned non-PDF data; check scanner backend format support."
                if _verbose_hardware_errors():
                    msg += f" [device={device or 'default'} cmd={' '.join(cmd)}]"
                log.error("scan_fail mode=real reason=non_pdf msg=%r", msg)
                return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)
        elif not stdout.startswith(b"\xff\xd8\xff"):
            msg = "Scanner returned non-JPEG data; check scanner backend format support."
            if _verbose_hardware_errors():
                msg += f" [device={device or 'default'} cmd={' '.join(cmd)}]"
            log.error("scan_fail mode=real reason=non_jpeg msg=%r", msg)
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)

        log.info("scan_ok mode=real bytes=%d", len(stdout))
        return ScanResult(ok=True, stdout=stdout, stderr=err_text, user_message=None)

    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult:
        import tempfile
        from pathlib import Path

        fd, file_path = tempfile.mkstemp(prefix=f"kopi-id-{side_name}-", suffix=".png")
        os.close(fd)
        output = Path(file_path)
        env = os.environ
        cmd: list[str] = [
            "scanimage",
            "--format=png",
            "-l",
            "0",
            "-t",
            "0",
            "-x",
            "86",
            "-y",
            "54",
        ]
        res_arg = env.get("SCAN_RESOLUTION", "300")
        cmd.extend(["--resolution", res_arg])
        dev = device or env.get("SCAN_DEVICE")
        if dev:
            cmd.extend(["-d", dev])
        extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
        if extra:
            cmd.extend(extra.split())
        cmd.extend(["-o", file_path])

        log.info("scan_id_side mode=real side=%s device=%r cmd=%s", side_name, device, " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=str(e), user_message="Scanner Not Found")

        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            log.error("scan_id_side_timeout mode=real side=%s", side_name)
            _kill_quiet(proc)
            await proc.wait()
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr="timeout", user_message="Scanner Busy")

        err_text = (stderr or b"").decode(errors="replace")
        if proc.returncode != 0 and "--resolution" in err_text and "unrecognized option" in err_text:
            cmd_no_res: list[str] = []
            skip_next = False
            for c in cmd:
                if skip_next:
                    skip_next = False
                    continue
                if c == "--resolution":
                    skip_next = True
                    continue
                cmd_no_res.append(c)
            log.warning("scan_id_side_retry_no_resolution side=%s", side_name)
            try:
                proc2 = await asyncio.create_subprocess_exec(
                    *cmd_no_res,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _stdout2, stderr = await asyncio.wait_for(proc2.communicate(), timeout=timeout_sec)
                err_text = (stderr or b"").decode(errors="replace")
                proc = proc2
            except (FileNotFoundError, asyncio.TimeoutError) as e:
                output.unlink(missing_ok=True)
                return ScanFileResult(
                    ok=False,
                    path="",
                    stderr=str(e),
                    user_message="Scanner Busy" if isinstance(e, asyncio.TimeoutError) else str(e),
                )

        if proc.returncode != 0:
            output.unlink(missing_ok=True)
            msg = classify_scan_error(err_text) or f"Scanner error: {err_text.strip() or proc.returncode}"
            log.error("scan_id_side_fail mode=real rc=%s msg=%r", proc.returncode, msg)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message=msg)

        try:
            if output.stat().st_size <= 0:
                output.unlink(missing_ok=True)
                return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Scanner returned no data")
        except OSError as e:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=str(e), user_message=str(e))

        log.info("scan_id_side_ok mode=real side=%s path=%s", side_name, file_path)
        return ScanFileResult(ok=True, path=file_path, stderr=err_text, user_message=None)


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
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = Path(tmp.name)
        try:
            return await self.print_file(
                str(tmp_path),
                duplex=duplex,
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
        cmd.append(file_path)

        log.info(
            "print_start mode=real duplex=%s device=%r path=%s cmd=%s",
            duplex,
            device,
            file_path,
            " ".join(cmd),
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            log.error("print_fail mode=real reason=binary_missing err=%s", e)
            return PrintResult(
                ok=False, stderr=str(e), user_message="Printer Not Found"
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except asyncio.TimeoutError:
            log.error("print_timeout mode=real timeout=%ss", timeout_sec)
            _kill_quiet(proc)
            await proc.wait()
            return PrintResult(
                ok=False, stderr="timeout", user_message="Printer Busy"
            )

        out_text = (stdout or b"").decode(errors="replace")
        err_text = (stderr or b"").decode(errors="replace")
        if proc.returncode != 0:
            msg = (
                classify_print_error(err_text)
                or f"Print error: {err_text.strip() or proc.returncode}"
            )
            log.error("print_fail mode=real rc=%s msg=%r", proc.returncode, msg)
            return PrintResult(
                ok=False,
                stderr=err_text,
                user_message=msg,
                stdout=out_text,
                destination=dest or "",
            )

        job_match = re.search(r"request id is (\S+)", out_text)
        job_id = job_match.group(1) if job_match else ""

        async def job_visible_in_cups(check_job_id: str) -> bool | None:
            try:
                lpstat_proc = await asyncio.create_subprocess_exec(
                    "lpstat",
                    "-W",
                    "all",
                    "-o",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                return None
            lpstat_out, _lpstat_err = await lpstat_proc.communicate()
            if lpstat_proc.returncode != 0:
                return None
            text = (lpstat_out or b"").decode(errors="replace")
            return check_job_id in text

        if job_id:
            visible = await job_visible_in_cups(job_id)
            if visible is False:
                msg = (
                    f'Print command accepted but CUPS queue does not show job "{job_id}". '
                    "Check selected printer queue and CUPS status."
                )
                if _verbose_hardware_errors():
                    msg += f" [dest={dest or 'default'} lp_stdout={_compact_stderr(out_text)}]"
                log.error("print_fail mode=real reason=job_not_visible job_id=%s", job_id)
                return PrintResult(
                    ok=False,
                    stderr=err_text,
                    user_message=msg,
                    stdout=out_text,
                    job_id=job_id,
                    destination=dest or "",
                )

        log.info("print_ok mode=real")
        return PrintResult(
            ok=True,
            stderr=err_text,
            user_message=None,
            stdout=out_text,
            job_id=job_id,
            destination=dest or "",
        )


class MockScannerBridge(ScannerBridge):
    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        device: str | None = None,
        timeout_sec: int = 300,
        resolution_dpi: int = 300,
        color: bool = True,
        output_format: str = "pdf",
    ) -> ScanResult:
        _ = timeout_sec, resolution_dpi, color
        delay = random.uniform(3.0, 5.0)
        log.info(
            "scan_start mode=mock duplex=%s fmt=%s device=%r delay=%.2fs",
            duplex,
            output_format,
            device,
            delay,
        )
        await asyncio.sleep(delay)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if output_format.lower() in ("jpg", "jpeg"):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "magick",
                    "xc:white",
                    "-resize",
                    "400x600!",
                    "jpeg:-",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                jpeg_out, magick_err = await asyncio.wait_for(proc.communicate(), timeout=15)
                err_txt = (magick_err or b"").decode(errors="replace")
                if proc.returncode == 0 and jpeg_out and jpeg_out.startswith(b"\xff\xd8"):
                    log.info("scan_ok mode=mock jpeg bytes=%d", len(jpeg_out))
                    return ScanResult(ok=True, stdout=jpeg_out, stderr=err_txt, user_message=None)
            except (FileNotFoundError, asyncio.TimeoutError, OSError) as e:
                log.warning("mock_jpeg_fail reason=%s", e)
            return ScanResult(
                ok=False,
                stdout=b"",
                stderr="magick failed or unavailable",
                user_message="Mock JPEG requires ImageMagick (`magick`) on PATH",
            )

        body = f"MOCK SCAN {ts}{' (duplex)' if duplex else ''}"
        pdf = _build_mock_pdf(body)
        log.info("scan_ok mode=mock bytes=%d", len(pdf))
        return ScanResult(ok=True, stdout=pdf, stderr="", user_message=None)

    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult:
        import tempfile
        from pathlib import Path

        _ = device, timeout_sec
        delay = random.uniform(0.4, 1.2)
        log.info("scan_id_side mode=mock side=%s delay=%.2fs", side_name, delay)
        await asyncio.sleep(delay)
        fd, file_path = tempfile.mkstemp(prefix=f"kopi-id-{side_name}-", suffix=".png")
        os.close(fd)
        from . import scanner as scanner_mod

        scanner_mod.write_mock_id_scan_png(file_path, side_name)
        log.info("scan_id_side_ok mode=mock path=%s", file_path)
        return ScanFileResult(ok=True, path=file_path, stderr="", user_message=None)


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

    async def print_file(
        self,
        file_path: str,
        *,
        duplex: bool = False,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
    ) -> PrintResult:
        _ = timeout_sec
        delay = random.uniform(1.0, 2.0)
        cmd_preview = ["lp", "-t", job_name]
        if duplex:
            cmd_preview.extend(["-o", "sides=two-sided-long-edge"])
        if device:
            cmd_preview.extend(["-d", device])
        cmd_preview.append(file_path)
        log.info(
            "print_file_start mode=mock duplex=%s device=%r path=%s cmd=%s delay=%.2fs",
            duplex,
            device,
            file_path,
            " ".join(cmd_preview),
            delay,
        )
        await asyncio.sleep(delay)
        log.info("print_file_ok mode=mock")
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
