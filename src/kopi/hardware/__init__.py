"""Hardware abstraction layer singletons and public exports."""

from __future__ import annotations

import logging

from .base import (
    DuplexMode,
    HardwareMode,
    PrinterBridge,
    PrintResult,
    ScanFileResult,
    ScannerBridge,
    ScanResult,
    ScanSource,
    detect_mode,
)
from .lock import HardwareBusyError, HardwareLock
from .printer import (
    MockPrinterBridge,
    RealPrinterBridge,
    build_lp_cmd,
    classify_print_error,
    list_printer_queues,
)
from .scanner import (
    SCANNER_BUSY_RECOVERY_HINT,
    MockScannerBridge,
    RealScannerBridge,
    build_scanimage_document_cmd,
    classify_scan_error,
    is_scanner_busy_error,
    list_scan_devices,
)
from .usb import (
    UsbVolume,
    list_usb_volumes,
    mount_usb_partition,
    resolve_writable_usb_mount,
)

log = logging.getLogger("kopi.hardware")

_scanner: ScannerBridge | None = None
_printer: PrinterBridge | None = None
_hardware_lock: HardwareLock | None = None


def get_scanner() -> ScannerBridge:
    """Return the active ScannerBridge singleton (Real or Mock)."""
    global _scanner
    if _scanner is None:
        mode = detect_mode()
        log.info("scanner_bridge_init mode=%s", mode.value)
        _scanner = RealScannerBridge() if mode is HardwareMode.REAL else MockScannerBridge()
    return _scanner


def get_printer() -> PrinterBridge:
    """Return the active PrinterBridge singleton (Real or Mock)."""
    global _printer
    if _printer is None:
        mode = detect_mode()
        log.info("printer_bridge_init mode=%s", mode.value)
        _printer = RealPrinterBridge() if mode is HardwareMode.REAL else MockPrinterBridge()
    return _printer


def get_hardware_lock() -> HardwareLock:
    """Return the global HardwareLock singleton."""
    global _hardware_lock
    if _hardware_lock is None:
        _hardware_lock = HardwareLock()
    return _hardware_lock


def reset_bridges() -> None:
    """Reset hardware singletons (primarily for testing)."""
    global _scanner, _printer, _hardware_lock
    _scanner = None
    _printer = None
    _hardware_lock = None


__all__ = [
    "DuplexMode",
    "HardwareBusyError",
    "HardwareLock",
    "HardwareMode",
    "MockPrinterBridge",
    "MockScannerBridge",
    "PrintResult",
    "PrinterBridge",
    "RealPrinterBridge",
    "RealScannerBridge",
    "SCANNER_BUSY_RECOVERY_HINT",
    "ScanFileResult",
    "ScanResult",
    "ScanSource",
    "ScannerBridge",
    "UsbVolume",
    "build_lp_cmd",
    "build_scanimage_document_cmd",
    "classify_print_error",
    "classify_scan_error",
    "detect_mode",
    "get_hardware_lock",
    "get_printer",
    "get_scanner",
    "is_scanner_busy_error",
    "list_printer_queues",
    "list_scan_devices",
    "list_usb_volumes",
    "mount_usb_partition",
    "reset_bridges",
    "resolve_writable_usb_mount",
]
