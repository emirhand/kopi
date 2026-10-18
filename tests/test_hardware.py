"""Unit tests for kopi.hardware (written first per TDD rules)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kopi.hardware import (
    DuplexMode,
    HardwareBusyError,
    HardwareLock,
    HardwareMode,
    ScanSource,
    build_lp_cmd,
    build_scanimage_document_cmd,
    classify_print_error,
    classify_scan_error,
    detect_mode,
    get_printer,
    get_scanner,
    reset_bridges,
)


def test_detect_mode_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    assert detect_mode() is HardwareMode.MOCK

    monkeypatch.setenv("KOPI_HARDWARE_MODE", "real")
    assert detect_mode() is HardwareMode.REAL


@pytest.mark.asyncio
async def test_hardware_lock_tracks_operation_and_prevents_collision() -> None:
    lock = HardwareLock()
    assert lock.is_busy is False
    assert lock.current_operation is None

    async with lock.acquire("copy"):
        assert lock.is_busy is True
        assert lock.current_operation == "copy"
        with pytest.raises(HardwareBusyError, match="copy"):
            async with lock.acquire("scan", wait=False):
                pass

    assert lock.is_busy is False
    assert lock.current_operation is None


@pytest.mark.asyncio
async def test_hardware_lock_serializes_when_wait_true() -> None:
    lock = HardwareLock()
    order: list[str] = []

    async def worker(name: str, delay: float) -> None:
        async with lock.acquire(name, wait=True):
            order.append(f"{name}:start")
            await asyncio.sleep(delay)
            order.append(f"{name}:end")

    await asyncio.gather(worker("first", 0.03), worker("second", 0.01))
    assert order == ["first:start", "first:end", "second:start", "second:end"]


def test_build_scanimage_document_cmd_options() -> None:
    cmd = build_scanimage_document_cmd(
        duplex_scan=True,
        device="pixma:04A9",
        output_format="pdf",
        resolution_dpi=300,
        color=False,
    )
    assert cmd[:2] == ["scanimage", "--format=pdf"]
    assert ["--mode", "Gray"] == cmd[cmd.index("--mode") : cmd.index("--mode") + 2]
    assert ["--resolution", "300"] == cmd[cmd.index("--resolution") : cmd.index("--resolution") + 2]
    assert ["-d", "pixma:04A9"] == cmd[cmd.index("-d") : cmd.index("-d") + 2]
    assert ["--source", "ADF Duplex"] == cmd[cmd.index("--source") : cmd.index("--source") + 2]
    assert cmd[-2:] == ["-o", "-"]


def test_build_scanimage_document_cmd_explicit_source() -> None:
    cmd = build_scanimage_document_cmd(
        duplex_scan=False,
        source=ScanSource.ADF,
        output_format="jpeg",
        resolution_dpi=150,
        color=True,
    )
    assert "--format=jpeg" in cmd
    assert ["--source", "ADF"] == cmd[cmd.index("--source") : cmd.index("--source") + 2]


def test_build_lp_cmd_full_copier_options() -> None:
    cmd = build_lp_cmd(
        "/tmp/doc.pdf",
        job_name="kopi-copy",
        device="Office_Printer",
        copies=3,
        duplex=DuplexMode.SHORT_EDGE,
        color=False,
        paper_size="A4",
    )
    assert cmd[0] == "lp"
    assert "-t" in cmd and cmd[cmd.index("-t") + 1] == "kopi-copy"
    assert "-d" in cmd and cmd[cmd.index("-d") + 1] == "Office_Printer"
    assert "-n" in cmd and cmd[cmd.index("-n") + 1] == "3"
    assert "sides=two-sided-short-edge" in cmd
    assert "ColorModel=Gray" in cmd
    assert "media=A4" in cmd
    assert cmd[-1] == "/tmp/doc.pdf"


def test_classify_scan_and_print_errors() -> None:
    assert classify_scan_error("scanimage: sane_start: Document feeder out of documents") == "No Paper"
    assert classify_scan_error("scanimage: open of device pixma failed: Device busy") == "Scanner Busy"
    assert classify_scan_error("unknown glitch") is None

    assert classify_print_error("lp: Media empty on tray 1") == "No Paper"
    assert classify_print_error("lp: printer is busy") == "Printer Busy"
    assert classify_print_error("everything fine") is None


@pytest.mark.asyncio
async def test_mock_scanner_and_printer_bridges_work_without_external_binaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    reset_bridges()

    scanner = get_scanner()
    printer = get_printer()

    pdf_res = await scanner.scan_pdf(duplex=True, resolution_dpi=300, color=True, output_format="pdf")
    assert pdf_res.ok is True
    assert pdf_res.stdout.startswith(b"%PDF-")

    jpg_res = await scanner.scan_pdf(duplex=False, resolution_dpi=150, color=False, output_format="jpeg")
    assert jpg_res.ok is True
    assert jpg_res.stdout.startswith(b"\xff\xd8")

    file_res = await scanner.scan_copy_file(duplex=False, resolution_dpi=300, color=True)
    assert file_res.ok is True
    p = Path(file_res.path)
    assert p.is_file() and p.stat().st_size > 0

    print_res = await printer.print_file(
        str(p),
        copies=2,
        duplex=True,
        color=True,
        paper_size="A4",
    )
    assert print_res.ok is True
    p.unlink(missing_ok=True)


def test_build_scanimage_batch_cmd_for_adf() -> None:
    from kopi.hardware.scanner import build_scanimage_batch_cmd

    cmd = build_scanimage_batch_cmd(
        batch_pattern="/tmp/batch/page-%04d.png",
        duplex_scan=False,
        source=ScanSource.ADF,
        device="hpaio:/usb/HP_OfficeJet_Pro_9010_series",
        resolution_dpi=300,
        color=True,
    )
    assert cmd[0] == "scanimage"
    assert "--format=png" in cmd
    assert ["--source", "ADF"] == cmd[cmd.index("--source") : cmd.index("--source") + 2]
    assert "--batch=/tmp/batch/page-%04d.png" in cmd
    assert "-o" not in cmd


@pytest.mark.asyncio
async def test_real_scanner_adf_combines_multiple_pages_into_single_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import Image
    from pypdf import PdfReader

    from kopi.hardware.scanner import RealScannerBridge

    bridge = RealScannerBridge()

    class FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b"Scanning page 1\nScanning page 2\nDocument feeder out of documents\n"

        async def wait(self) -> int:
            return 0

    async def fake_subprocess_exec(*args: str, **_kwargs: object) -> FakeProc:
        batch_arg = next((a for a in args if a.startswith("--batch=")), "")
        assert batch_arg, f"Expected --batch= in {args}"
        pattern = batch_arg.split("=", 1)[1]
        batch_dir = Path(pattern).parent
        # Simulate scanimage writing 2 pages to the batch directory
        for idx in (1, 2):
            img = Image.new("RGB", (200, 300), color=(255, 255, 255))
            img.save(batch_dir / f"page-000{idx}.png", format="PNG")
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess_exec)

    res = await bridge.scan_copy_file(
        duplex=False,
        source=ScanSource.ADF,
        device="hpaio:/usb/HP_OfficeJet_Pro_9010_series",
        resolution_dpi=300,
        color=True,
    )
    assert res.ok is True
    pdf_path = Path(res.path)
    assert pdf_path.is_file()
    assert pdf_path.suffix == ".pdf"

    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) == 2
    pdf_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_scanner_cancel_terminates_active_scanimage_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kopi.hardware.scanner import RealScannerBridge

    bridge = RealScannerBridge()
    terminated = False
    started_event = asyncio.Event()
    finish_event = asyncio.Event()

    class SlowFakeProc:
        returncode: int | None = None

        async def communicate(self) -> tuple[bytes, bytes]:
            started_event.set()
            await finish_event.wait()
            return b"", b"scanimage: received signal 15\n"

        def terminate(self) -> None:
            nonlocal terminated
            terminated = True
            self.returncode = -15
            finish_event.set()

        def kill(self) -> None:
            self.returncode = -9
            finish_event.set()

        async def wait(self) -> int:
            return self.returncode or 0

    async def fake_subprocess_exec(*_args: str, **_kwargs: object) -> SlowFakeProc:
        return SlowFakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess_exec)

    scan_task = asyncio.create_task(
        bridge.scan_copy_file(duplex=False, source=ScanSource.ADF, color=True)
    )
    await started_event.wait()
    cancelled = await bridge.cancel_scan()
    assert cancelled is True
    assert terminated is True

    res = await scan_task
    assert res.ok is False
    assert res.user_message == "Cancelled"


@pytest.mark.asyncio
async def test_printer_cancel_invokes_cups_cancel_on_last_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kopi.hardware.printer import RealPrinterBridge

    bridge = RealPrinterBridge()
    commands_run: list[list[str]] = []

    class FakeProc:
        def __init__(self, stdout: bytes = b"") -> None:
            self.returncode = 0
            self._stdout = stdout

        async def communicate(self) -> tuple[bytes, bytes]:
            return self._stdout, b""

        async def wait(self) -> int:
            return 0

    async def fake_subprocess_exec(*args: str, **_kwargs: object) -> FakeProc:
        cmd_list = list(args)
        commands_run.append(cmd_list)
        if cmd_list[0] == "lp":
            return FakeProc(b"request id is HP_OfficeJet_Pro_9010-42 (1 file(s))\n")
        return FakeProc(b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess_exec)

    res = await bridge.print_file("/tmp/dummy.pdf", device="HP_OfficeJet_Pro_9010")
    assert res.ok is True
    assert res.job_id == "HP_OfficeJet_Pro_9010-42"

    cancel_ok = await bridge.cancel_print()
    assert cancel_ok is True
    assert ["cancel", "HP_OfficeJet_Pro_9010-42"] in commands_run


