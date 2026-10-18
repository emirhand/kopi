"""Abstract hardware bridge definitions and domain enums."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class HardwareMode(str, Enum):
    REAL = "real"
    MOCK = "mock"


class ScanSource(str, Enum):
    AUTO = "auto"
    FLATBED = "flatbed"
    ADF = "adf"
    ADF_DUPLEX = "adf_duplex"


class DuplexMode(str, Enum):
    NONE = "none"
    LONG_EDGE = "two-sided-long-edge"
    SHORT_EDGE = "two-sided-short-edge"


_MODE_ENV = "KOPI_HARDWARE_MODE"


def detect_mode() -> HardwareMode:
    """Determine whether to use real Linux SANE/CUPS CLI tools or mock bridges."""
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


@dataclass(frozen=True)
class PrintResult:
    ok: bool
    stderr: str
    user_message: str | None
    stdout: str = ""
    job_id: str = ""
    destination: str = ""


class ScannerBridge(ABC):
    @abstractmethod
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
    ) -> ScanResult: ...

    @abstractmethod
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
    ) -> ScanFileResult: ...

    @abstractmethod
    async def scan_id_side(
        self,
        side_name: str,
        *,
        device: str | None = None,
        timeout_sec: int = 180,
    ) -> ScanFileResult: ...

    @abstractmethod
    async def cancel_scan(self) -> bool: ...


class PrinterBridge(ABC):
    @abstractmethod
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
    ) -> PrintResult: ...

    @abstractmethod
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
    ) -> PrintResult: ...

    @abstractmethod
    async def cancel_print(self, job_id: str | None = None) -> bool: ...

