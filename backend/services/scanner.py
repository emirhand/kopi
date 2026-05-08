"""SANE / scanimage façade — delegates to :mod:`services.hardware`."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import struct
import subprocess
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
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


@dataclass(frozen=True)
class ScanFileResult:
    ok: bool
    path: str
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
    include_mode: bool = True,
    source: str | None = None,
    include_output_file_flag: bool = True,
) -> list[str]:
    """Arguments for `scanimage` emitting PDF on stdout (ends with `-o -`)."""
    env = os.environ.copy()
    cmd: list[str] = ["scanimage", "--format=pdf"]
    if include_mode:
        cmd.extend(["--mode", env.get("SCAN_MODE", "Color")])
    if include_resolution:
        cmd.extend(["--resolution", env.get("SCAN_RESOLUTION", "300")])

    dev = device or env.get("SCAN_DEVICE")
    if dev:
        cmd.extend(["-d", dev])

    if duplex_scan:
        cmd.extend(["--source", "ADF", "--duplex"])
    elif source:
        cmd.extend(["--source", source])

    extra = env.get("SCANIMAGE_EXTRA_ARGS", "").strip()
    if extra:
        cmd.extend(extra.split())

    if include_output_file_flag:
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
    return sorted(dict.fromkeys(devices))


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


async def scan_copy_image_file(
    *,
    duplex: bool = False,
    device: str | None = None,
    timeout_sec: int = 300,
) -> ScanFileResult:
    """Run ``scanimage`` to a temporary PNG file for robust copy-print path."""
    env = os.environ.copy()
    fd, file_path = tempfile.mkstemp(prefix="kopi-copy-", suffix=".png")
    os.close(fd)
    output = Path(file_path)

    base_cmd = ["scanimage", "--format=png"]
    dev = device or env.get("SCAN_DEVICE")
    if dev:
        base_cmd.extend(["-d", dev])
    if duplex:
        base_cmd.extend(["--source", "ADF", "--duplex"])
    cmd = base_cmd + ["-o", file_path]

    async def run(run_cmd: list[str]) -> tuple[int, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                *run_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            return 127, str(e)
        try:
            _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            return 124, "timeout"
        return proc.returncode, (stderr or b"").decode(errors="replace")

    rc, err_text = await run(cmd)
    if rc != 0 and "--resolution" in err_text and "unrecognized option" in err_text:
        cmd = base_cmd + ["-o", file_path]
        rc, err_text = await run(cmd)
    if rc != 0 and "initialize parameter is error" in err_text.lower():
        safe_cmd = ["scanimage", "--format=png"]
        if dev:
            safe_cmd.extend(["-d", dev])
        safe_cmd.extend(["--source", "Flatbed", "-o", file_path])
        cmd = safe_cmd
        rc, err_text = await run(cmd)

    if rc == 127:
        output.unlink(missing_ok=True)
        return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Scanner Not Found")
    if rc == 124:
        output.unlink(missing_ok=True)
        return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Scanner Busy")
    if rc != 0:
        output.unlink(missing_ok=True)
        return ScanFileResult(
            ok=False,
            path="",
            stderr=err_text,
            user_message=classify_scan_error(err_text) or f"Scanner error: {err_text.strip() or rc}",
        )
    try:
        if output.stat().st_size <= 0:
            output.unlink(missing_ok=True)
            return ScanFileResult(ok=False, path="", stderr=err_text, user_message="Scanner returned no data")
    except OSError as e:
        output.unlink(missing_ok=True)
        return ScanFileResult(ok=False, path="", stderr=str(e), user_message=f"Scan output file error: {e}")

    log.info("scan_copy_file_ok duplex=%s device=%r path=%s", duplex, dev, file_path)
    return ScanFileResult(ok=True, path=file_path, stderr=err_text, user_message=None)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def _write_solid_png_rgb(path: str, width: int, height: int, rgb: tuple[int, int, int]) -> None:
    r, g, b = rgb
    raw = bytearray()
    for _y in range(height):
        raw.append(0)
        raw.extend(bytes([r, g, b]) * width)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    Path(path).write_bytes(png)


def write_mock_id_scan_png(path: str, side_name: str) -> None:
    """
    325×204 mock ID scan for non-Linux / mock hardware.
    Prefer ImageMagick label; fall back to solid RGB rectangle.
    """
    label = "FRONT" if "front" in side_name.lower() else "BACK"
    color = "#2d6a4f" if label == "FRONT" else "#1d3557"
    try:
        subprocess.run(
            [
                "magick",
                "-size",
                "325x204",
                f"xc:{color}",
                "-pointsize",
                "40",
                "-fill",
                "white",
                "-gravity",
                "center",
                "-annotate",
                "0",
                label,
                path,
            ],
            check=True,
            timeout=15,
            capture_output=True,
        )
        return
    except (OSError, subprocess.CalledProcessError):
        pass
    rgb = (45, 106, 79) if label == "FRONT" else (29, 53, 87)
    _write_solid_png_rgb(path, 325, 204, rgb)


async def scan_id_side(
    side_name: str,
    *,
    device: str | None = None,
    timeout_sec: int = 180,
) -> ScanFileResult:
    """Scan one side of an ID-1 card region (86×54 mm) to a PNG file."""
    from .hardware import get_scanner

    result = await get_scanner().scan_id_side(
        side_name, device=device, timeout_sec=timeout_sec
    )
    log.info(
        "scan_id_side_facade side=%s ok=%s user_message=%r",
        side_name,
        result.ok,
        result.user_message,
    )
    return result
