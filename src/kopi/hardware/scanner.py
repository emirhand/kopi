"""SANE / scanimage scanner implementation (Real & Pure-Python Mock)."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import img2pdf
from PIL import Image, ImageDraw

from kopi.processing.copy_enhance import enhance_scanned_image_file

from .base import ScanFileResult, ScannerBridge, ScanResult, ScanSource

log = logging.getLogger("kopi.scanner")

_NO_PAPER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"out\s+of\s+paper", re.I),
    re.compile(r"no\s+paper", re.I),
    re.compile(r"document\s+feeder\s+out\s+of\s+documents", re.I),
    re.compile(r"no\s+documents", re.I),
    re.compile(r"empty\s+(feeder|adf)", re.I),
)
_BUSY_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"device\s+busy", re.I),
    re.compile(r"sane_start:.*busy", re.I),
    re.compile(r"scanner\s+busy", re.I),
    re.compile(r"resource\s+busy", re.I),
    re.compile(r"could\s+not\s+open\s+device", re.I),
)

SCANNER_BUSY_RECOVERY_HINT: Final[str] = (
    " After a paper error, the device or driver may need several seconds to release. "
    "Clear the ADF, check the printer panel for a stuck job, then retry. "
    "If it keeps failing, power-cycle the MFP or restart the Kopi service."
)


def classify_scan_error(stderr: str) -> str | None:
    """Classify SANE stderr text into a human-friendly error category."""
    text = stderr or ""
    for pat in _NO_PAPER_PATTERNS:
        if pat.search(text):
            return "No Paper"
    for pat in _BUSY_PATTERNS:
        if pat.search(text):
            return "Scanner Busy"
    return None


def is_scanner_busy_error(stderr: str) -> bool:
    return classify_scan_error(stderr) == "Scanner Busy"


def busy_retry_settings() -> tuple[int, float]:
    retries = int(os.environ.get("KOPI_SCAN_BUSY_RETRIES", "4"))
    delay = float(os.environ.get("KOPI_SCAN_BUSY_DELAY_SEC", "3"))
    return max(0, retries), max(0.5, delay)


def _resolve_sane_source(duplex_scan: bool, source: ScanSource | None) -> str:
    if source is ScanSource.ADF_DUPLEX or (duplex_scan and source in (None, ScanSource.AUTO)):
        return "ADF Duplex"
    if source is ScanSource.ADF:
        return "ADF"
    return "Flatbed"


def _is_adf_source(duplex_scan: bool, source: ScanSource | None) -> bool:
    return _resolve_sane_source(duplex_scan, source) in ("ADF", "ADF Duplex")


_ORIGINAL_SIZE_MM: Final[dict[str, tuple[float, float]]] = {
    "a4": (210.0, 297.0),
    "letter": (215.9, 279.4),
    "legal": (215.9, 355.6),
    "a5": (148.0, 210.0),
    "4x6": (101.6, 152.4),
}


def resolve_original_size_mm(original_size: str | None) -> tuple[float, float]:
    """Return physical `(width_mm, height_mm)` for a paper size name (defaults to A4)."""
    key = (original_size or "A4").strip().lower()
    return _ORIGINAL_SIZE_MM.get(key, _ORIGINAL_SIZE_MM["a4"])


def _format_mm(val: float) -> str:
    return f"{val:g}"


def build_scanimage_document_cmd(
    *,
    duplex_scan: bool = False,
    source: ScanSource | None = None,
    device: str | None = None,
    output_format: str = "pdf",
    resolution_dpi: int = 300,
    color: bool = True,
    original_size: str | None = None,
    include_resolution: bool = True,
    include_mode: bool = True,
    output_path: str = "-",
) -> list[str]:
    """Build scanimage command arguments for single-frame document scans."""
    env = os.environ.copy()
    fmt_lower = output_format.lower()
    if fmt_lower in ("jpg", "jpeg"):
        fmt = "jpeg"
    elif fmt_lower == "png":
        fmt = "png"
    else:
        fmt = "pdf"

    cmd: list[str] = ["scanimage", f"--format={fmt}"]
    if include_mode:
        mode = "Color" if color else "Gray"
        cmd.extend(["--mode", mode])
    if include_resolution:
        cmd.extend(["--resolution", str(resolution_dpi)])

    dev = device or env.get("SCAN_DEVICE")
    if dev:
        cmd.extend(["-d", dev])

    cmd.extend(["--source", _resolve_sane_source(duplex_scan, source)])

    if original_size and original_size.strip():
        w_mm, h_mm = resolve_original_size_mm(original_size)
        cmd.extend(["-l", "0", "-t", "0", "-x", _format_mm(w_mm), "-y", _format_mm(h_mm)])

    extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())

    cmd.extend(["-o", output_path])
    return cmd


def build_scanimage_batch_cmd(
    *,
    batch_pattern: str,
    duplex_scan: bool = False,
    source: ScanSource | None = None,
    device: str | None = None,
    resolution_dpi: int = 300,
    color: bool = True,
    original_size: str | None = None,
    include_resolution: bool = True,
    include_mode: bool = True,
) -> list[str]:
    """Build scanimage command arguments for multi-page ADF batch scans."""
    env = os.environ.copy()
    cmd: list[str] = ["scanimage", "--format=png"]
    if include_mode:
        mode = "Color" if color else "Gray"
        cmd.extend(["--mode", mode])
    if include_resolution:
        cmd.extend(["--resolution", str(resolution_dpi)])

    dev = device or env.get("SCAN_DEVICE")
    if dev:
        cmd.extend(["-d", dev])

    cmd.extend(["--source", _resolve_sane_source(duplex_scan, source)])

    if original_size and original_size.strip():
        w_mm, h_mm = resolve_original_size_mm(original_size)
        cmd.extend(["-l", "0", "-t", "0", "-x", _format_mm(w_mm), "-y", _format_mm(h_mm)])

    extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())

    cmd.append(f"--batch={batch_pattern}")
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
        if not line.lower().startswith("device "):
            continue
        m_backtick = re.match(r"^device\s+`([^`]+)`\s+is\b", line)
        if m_backtick:
            devices.append(m_backtick.group(1))
            continue
        m_quote = re.match(r"^device\s+'([^']+)'\s+is\b", line)
        if m_quote:
            devices.append(m_quote.group(1))
            continue
        m_fallback = re.match(r"^device\s+(.+?)\s+is\b", line)
        if m_fallback:
            devices.append(m_fallback.group(1).strip("`'\""))
    filtered = [d for d in dict.fromkeys(devices) if not d.lower().startswith("v4l:")]
    return sorted(filtered)


def _kill_quiet(proc: asyncio.subprocess.Process) -> None:
    try:
        proc.kill()
    except ProcessLookupError:
        pass


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
        msg += " Hint: selected scanner entry may be incompatible; try another scanner device in Admin Settings."
    if _verbose_hardware_errors():
        msg += f" [device={device or 'default'} cmd={' '.join(cmd)} stderr={_compact_stderr(err_text)}]"
    return msg


def _normalize_pdf_bytes(raw: bytes) -> bytes:
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
    if not raw.startswith(b"\xff\xd8"):
        return raw
    end = raw.rfind(b"\xff\xd9")
    if end < 0:
        return raw
    return raw[: end + 2]


def _build_mock_pdf(text: str) -> bytes:
    """Minimal one-page PDF stamped with ``text``."""
    safe = "".join(c if 32 <= ord(c) < 127 else "?" for c in text)[:80]
    safe_escaped = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = (
        b"BT /F1 24 Tf 72 720 Td ("
        + safe_escaped.encode("latin-1", errors="replace")
        + b") Tj ET"
    )
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
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


def _mock_delay(default_sec: float = 0.25) -> float:
    raw = os.environ.get("KOPI_MOCK_DELAY_SEC", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return default_sec


class RealScannerBridge(ScannerBridge):
    def __init__(self) -> None:
        self._active_proc: asyncio.subprocess.Process | None = None
        self._cancel_requested: bool = False

    async def cancel_scan(self) -> bool:
        """Stop the currently running scanimage process immediately."""
        self._cancel_requested = True
        proc = self._active_proc
        if proc is None:
            return False
        try:
            proc.terminate()
            log.info("scan_cancel_sent mode=real")
            return True
        except ProcessLookupError:
            return False

    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        timeout_sec: int = 300,
        resolution_dpi: int = 300,
        color: bool = True,
        output_format: str = "pdf",
    ) -> ScanResult:
        self._cancel_requested = False
        fmt_key = "jpeg" if output_format.lower() in ("jpg", "jpeg") else "pdf"
        if fmt_key == "pdf":
            file_res = await self.scan_copy_file(
                duplex=duplex,
                source=source,
                device=device,
                resolution_dpi=resolution_dpi,
                color=color,
                timeout_sec=timeout_sec,
            )
            if not file_res.ok:
                return ScanResult(
                    ok=False,
                    stdout=b"",
                    stderr=file_res.stderr,
                    user_message=file_res.user_message,
                )
            p = Path(file_res.path)
            try:
                if p.suffix.lower() == ".pdf":
                    pdf_bytes = p.read_bytes()
                else:
                    converted = img2pdf.convert(str(p))
                    pdf_bytes = converted if converted else b""
            finally:
                p.unlink(missing_ok=True)
            if not pdf_bytes:
                return ScanResult(
                    ok=False,
                    stdout=b"",
                    stderr=file_res.stderr,
                    user_message="Failed to convert scanned page to PDF",
                )
            return ScanResult(ok=True, stdout=pdf_bytes, stderr=file_res.stderr, user_message=None)

        cmd = build_scanimage_document_cmd(
            duplex_scan=duplex,
            source=source,
            device=device,
            output_format=output_format,
            resolution_dpi=resolution_dpi,
            color=color,
            include_resolution=True,
            include_mode=True,
        )
        log.info(
            "scan_start mode=real duplex=%s source=%s fmt=%s dpi=%s color=%s device=%r cmd=%s",
            duplex,
            source,
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
                return 127, b"", str(e)

            self._active_proc = proc
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                _kill_quiet(proc)
                await proc.wait()
                return 124, b"", "timeout"
            finally:
                if self._active_proc is proc:
                    self._active_proc = None
            return proc.returncode or 0, stdout or b"", (stderr or b"").decode(errors="replace")

        max_r, delay_s = busy_retry_settings()

        async def run_once(run_cmd: list[str]) -> tuple[int, bytes, str]:
            last: tuple[int, bytes, str] = (1, b"", "")
            for attempt in range(max_r + 1):
                rc, out, err = await run_once_raw(run_cmd)
                last = (rc, out, err)
                if self._cancel_requested or rc in (0, 127, 124) or not is_scanner_busy_error(err):
                    return rc, out, err
                if attempt < max_r:
                    await asyncio.sleep(delay_s)
            return last

        rc, stdout, err_text = await run_once(cmd)
        if self._cancel_requested:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Cancelled")
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
                source=source,
                device=device,
                output_format=output_format,
                resolution_dpi=resolution_dpi,
                color=color,
                include_resolution=False,
                include_mode=True,
            )
            rc, stdout, err_text = await run_once(fallback_cmd)
            cmd = fallback_cmd

        if self._cancel_requested:
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message="Cancelled")

        if rc != 0:
            msg = _scan_error_message(
                err_text=err_text,
                returncode=rc,
                device=device,
                cmd=cmd,
            )
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)

        stdout = _normalize_pdf_bytes(stdout) if fmt_key == "pdf" else _trim_jpeg_bytes(stdout)
        if not stdout:
            msg = classify_scan_error(err_text) or "Scanner returned no data"
            return ScanResult(ok=False, stdout=b"", stderr=err_text, user_message=msg)

        if fmt_key == "pdf" and (not stdout.startswith(b"%PDF-") or b"%%EOF" not in stdout):
            return ScanResult(
                ok=False,
                stdout=b"",
                stderr=err_text,
                user_message="Scanner returned non-PDF data; check scanner backend format support.",
            )
        if fmt_key == "jpeg" and not stdout.startswith(b"\xff\xd8\xff"):
            return ScanResult(
                ok=False,
                stdout=b"",
                stderr=err_text,
                user_message="Scanner returned non-JPEG data; check scanner backend format support.",
            )

        return ScanResult(ok=True, stdout=stdout, stderr=err_text, user_message=None)

    async def scan_copy_file(
        self,
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        resolution_dpi: int = 300,
        color: bool = True,
        original_size: str = "A4",
        lighter_darker: int = 0,
        content_type: str = "mixed",
        resize_mode: str = "actual",
        resize_percent: int = 100,
        timeout_sec: int = 300,
    ) -> ScanFileResult:
        self._cancel_requested = False

        async def exec_once(run_cmd: list[str]) -> tuple[int, str]:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *run_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as e:
                return 127, str(e)
            self._active_proc = proc
            try:
                _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                _kill_quiet(proc)
                await proc.wait()
                return 124, "timeout"
            finally:
                if self._active_proc is proc:
                    self._active_proc = None
            return proc.returncode or 0, (stderr or b"").decode(errors="replace")

        max_r, delay_s = busy_retry_settings()

        if _is_adf_source(duplex, source):
            with tempfile.TemporaryDirectory(prefix="kopi-adf-batch-") as batch_td:
                batch_dir = Path(batch_td)
                batch_pattern = str(batch_dir / "page-%04d.png")
                cmd = build_scanimage_batch_cmd(
                    batch_pattern=batch_pattern,
                    duplex_scan=duplex,
                    source=source,
                    device=device,
                    resolution_dpi=resolution_dpi,
                    color=color,
                    original_size=original_size,
                )
                log.info("scan_adf_batch_start mode=real cmd=%s", " ".join(cmd))

                rc, err_text = -1, ""
                for attempt in range(max_r + 1):
                    rc, err_text = await exec_once(cmd)
                    if (
                        self._cancel_requested
                        or rc in (0, 127, 124)
                        or not is_scanner_busy_error(err_text)
                    ):
                        break
                    if attempt < max_r:
                        await asyncio.sleep(delay_s)

                if self._cancel_requested:
                    return ScanFileResult(
                        ok=False, path="", stderr=err_text, user_message="Cancelled"
                    )
                if rc == 127:
                    return ScanFileResult(
                        ok=False, path="", stderr=err_text, user_message="Scanner Not Found"
                    )
                if rc == 124:
                    return ScanFileResult(
                        ok=False,
                        path="",
                        stderr=err_text,
                        user_message="Scanner Busy." + SCANNER_BUSY_RECOVERY_HINT,
                    )

                pages = sorted(
                    p for p in batch_dir.glob("page-*.png") if p.is_file() and p.stat().st_size > 0
                )
                # In batch mode, scanimage loops until the ADF reports out-of-documents.
                # If at least 1 page was scanned before the feeder emptied, assemble the PDF!
                if pages and (rc == 0 or classify_scan_error(err_text) == "No Paper"):
                    fd_pdf, pdf_path = tempfile.mkstemp(prefix="kopi-copy-adf-", suffix=".pdf")
                    os.close(fd_pdf)
                    out_pdf = Path(pdf_path)
                    try:
                        for p in pages:
                            enhance_scanned_image_file(
                                p,
                                lighter_darker=lighter_darker,
                                content_type=content_type,
                                resize_mode=resize_mode,
                                resize_percent=resize_percent,
                            )
                        pdf_bytes = img2pdf.convert([str(p) for p in pages])
                        if not pdf_bytes:
                            out_pdf.unlink(missing_ok=True)
                            return ScanFileResult(
                                ok=False,
                                path="",
                                stderr=err_text,
                                user_message="Failed to assemble scanned pages into PDF",
                            )
                        out_pdf.write_bytes(pdf_bytes)
                    except Exception as e:
                        out_pdf.unlink(missing_ok=True)
                        return ScanFileResult(
                            ok=False,
                            path="",
                            stderr=str(e),
                            user_message=f"PDF assembly error: {e}",
                        )
                    log.info(
                        "scan_adf_batch_ok pages=%d path=%s",
                        len(pages),
                        pdf_path,
                    )
                    return ScanFileResult(
                        ok=True, path=pdf_path, stderr=err_text, user_message=None
                    )

                msg = _scan_error_message(
                    err_text=err_text, returncode=rc, device=device, cmd=cmd
                )
                return ScanFileResult(ok=False, path="", stderr=err_text, user_message=msg)

        # Flatbed single-page path
        fd, file_path = tempfile.mkstemp(prefix="kopi-copy-", suffix=".png")
        os.close(fd)
        output = Path(file_path)

        cmd = build_scanimage_document_cmd(
            duplex_scan=duplex,
            source=source,
            device=device,
            output_format="png",
            resolution_dpi=resolution_dpi,
            color=color,
            original_size=original_size,
            output_path=file_path,
        )

        rc, err_text = -1, ""
        for attempt in range(max_r + 1):
            rc, err_text = await exec_once(cmd)
            if (
                self._cancel_requested
                or rc in (0, 127, 124)
                or not is_scanner_busy_error(err_text)
            ):
                break
            if attempt < max_r:
                await asyncio.sleep(delay_s)

        if self._cancel_requested:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Cancelled")
        if rc == 127:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Scanner Not Found")
        if rc == 124:
            output.unlink(missing_ok=True)
            return ScanFileResult(
                ok=False,
                path="",
                stderr=err_text,
                user_message="Scanner Busy." + SCANNER_BUSY_RECOVERY_HINT,
            )
        if rc != 0:
            output.unlink(missing_ok=True)
            msg = _scan_error_message(err_text=err_text, returncode=rc, device=device, cmd=cmd)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message=msg)

        try:
            if output.stat().st_size <= 0:
                output.unlink(missing_ok=True)
                return ScanFileResult(
                    ok=False,
                    path="",
                    stderr=err_text,
                    user_message="Scanner returned no data",
                )
            enhance_scanned_image_file(
                output,
                lighter_darker=lighter_darker,
                content_type=content_type,
                resize_mode=resize_mode,
                resize_percent=resize_percent,
            )
        except OSError as e:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=str(e), user_message=str(e))

        return ScanFileResult(ok=True, path=file_path, stderr=err_text, user_message=None)

    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult:
        self._cancel_requested = False
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
            "--resolution",
            env.get("SCAN_RESOLUTION", "300"),
        ]
        dev = device or env.get("SCAN_DEVICE")
        if dev:
            cmd.extend(["-d", dev])
        extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
        if extra:
            cmd.extend(extra.split())
        cmd.extend(["-o", file_path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=str(e), user_message="Scanner Not Found")

        self._active_proc = proc
        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            _kill_quiet(proc)
            await proc.wait()
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr="timeout", user_message="Scanner Busy")
        finally:
            if self._active_proc is proc:
                self._active_proc = None

        err_text = (stderr or b"").decode(errors="replace")
        if self._cancel_requested:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Cancelled")
        if proc.returncode != 0:
            output.unlink(missing_ok=True)
            msg = classify_scan_error(err_text) or f"Scanner error: {err_text.strip() or proc.returncode}"
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message=msg)

        try:
            if output.stat().st_size <= 0:
                output.unlink(missing_ok=True)
                return ScanFileResult(
                    ok=False, path="", stderr=err_text, user_message="Scanner returned no data"
                )
        except OSError as e:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=str(e), user_message=str(e))

        return ScanFileResult(ok=True, path=file_path, stderr=err_text, user_message=None)


class MockScannerBridge(ScannerBridge):
    """Pure-Python mock scanner using Pillow (zero external binary dependencies)."""

    def __init__(self) -> None:
        self._cancel_requested: bool = False

    async def cancel_scan(self) -> bool:
        self._cancel_requested = True
        return True

    async def scan_pdf(
        self,
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        timeout_sec: int = 300,
        resolution_dpi: int = 300,
        color: bool = True,
        output_format: str = "pdf",
    ) -> ScanResult:
        _ = source, device, timeout_sec, resolution_dpi
        self._cancel_requested = False
        await asyncio.sleep(_mock_delay(0.3))
        if self._cancel_requested:
            return ScanResult(ok=False, stdout=b"", stderr="cancelled", user_message="Cancelled")
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if output_format.lower() in ("jpg", "jpeg"):
            mode = "RGB" if color else "L"
            bg = (245, 247, 250) if color else 245
            img = Image.new(mode, (400, 600), color=bg)
            draw = ImageDraw.Draw(img)
            draw.text((24, 40), f"MOCK JPEG {ts}", fill=(20, 20, 20) if color else 20)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return ScanResult(ok=True, stdout=buf.getvalue(), stderr="", user_message=None)

        body = f"MOCK SCAN {ts}{' (duplex)' if duplex else ''}"
        pdf = _build_mock_pdf(body)
        return ScanResult(ok=True, stdout=pdf, stderr="", user_message=None)

    async def scan_copy_file(
        self,
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        resolution_dpi: int = 300,
        color: bool = True,
        original_size: str = "A4",
        lighter_darker: int = 0,
        content_type: str = "mixed",
        resize_mode: str = "actual",
        resize_percent: int = 100,
        timeout_sec: int = 300,
    ) -> ScanFileResult:
        _ = duplex, source, device, resolution_dpi, timeout_sec
        self._cancel_requested = False
        await asyncio.sleep(_mock_delay(0.2))
        if self._cancel_requested:
            return ScanFileResult(ok=False, path="", stderr="cancelled", user_message="Cancelled")
        fd, file_path = tempfile.mkstemp(prefix="kopi-copy-mock-", suffix=".png")
        os.close(fd)
        mode = "RGB" if color else "L"
        bg = (255, 255, 255) if color else 255
        w_mm, h_mm = resolve_original_size_mm(original_size)
        mock_px_w = max(100, round(w_mm * (600.0 / 210.0)))
        mock_px_h = max(100, round(h_mm * (600.0 / 210.0)))
        img = Image.new(mode, (mock_px_w, mock_px_h), color=bg)
        draw = ImageDraw.Draw(img)
        draw.text(
            (40, 60),
            f"MOCK COPY PAGE ({original_size})",
            fill=(10, 10, 10) if color else 10,
        )
        img.save(file_path, format="PNG")
        enhance_scanned_image_file(
            Path(file_path),
            lighter_darker=lighter_darker,
            content_type=content_type,
            resize_mode=resize_mode,
            resize_percent=resize_percent,
        )
        return ScanFileResult(ok=True, path=file_path, stderr="", user_message=None)

    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult:
        _ = device, timeout_sec
        self._cancel_requested = False
        await asyncio.sleep(_mock_delay(0.15))
        if self._cancel_requested:
            return ScanFileResult(ok=False, path="", stderr="cancelled", user_message="Cancelled")
        fd, file_path = tempfile.mkstemp(prefix=f"kopi-id-{side_name}-", suffix=".png")
        os.close(fd)
        label = "FRONT" if "front" in side_name.lower() else "BACK"
        rgb = (45, 106, 79) if label == "FRONT" else (29, 53, 87)
        img = Image.new("RGB", (325, 204), color=rgb)
        draw = ImageDraw.Draw(img)
        draw.text((120, 90), label, fill=(255, 255, 255))
        img.save(file_path, format="PNG")
        return ScanFileResult(ok=True, path=file_path, stderr="", user_message=None)
