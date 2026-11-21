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


def test_build_scanimage_cmds_apply_original_size_geometry() -> None:
    from kopi.hardware.scanner import build_scanimage_batch_cmd

    cmd_doc = build_scanimage_document_cmd(
        duplex_scan=False,
        source=ScanSource.FLATBED,
        output_format="png",
        resolution_dpi=300,
        color=True,
        original_size="A5",
    )
    assert ["-l", "0", "-t", "0", "-x", "148", "-y", "210"] == cmd_doc[
        cmd_doc.index("-l") : cmd_doc.index("-l") + 8
    ]

    cmd_batch = build_scanimage_batch_cmd(
        batch_pattern="/tmp/batch/page-%04d.png",
        duplex_scan=False,
        source=ScanSource.ADF,
        resolution_dpi=300,
        color=True,
        original_size="Letter",
    )
    assert ["-l", "0", "-t", "0", "-x", "215.9", "-y", "279.4"] == cmd_batch[
        cmd_batch.index("-l") : cmd_batch.index("-l") + 8
    ]


def test_build_scanimage_cmds_parse_quoted_extra_args_with_shlex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kopi.hardware.scanner import build_scanimage_batch_cmd

    monkeypatch.setenv("SCANIMAGE_EXTRA_ARGS", '--page-format "ISO A4" --brightness=10')

    cmd_doc = build_scanimage_document_cmd(duplex_scan=False, color=True)
    idx_doc = cmd_doc.index("--page-format")
    assert cmd_doc[idx_doc : idx_doc + 3] == ["--page-format", "ISO A4", "--brightness=10"]

    cmd_batch = build_scanimage_batch_cmd(batch_pattern="/tmp/batch/page-%04d.png")
    idx_batch = cmd_batch.index("--page-format")
    assert cmd_batch[idx_batch : idx_batch + 3] == ["--page-format", "ISO A4", "--brightness=10"]


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

    file_4x6 = await scanner.scan_copy_file(
        duplex=False, resolution_dpi=300, color=True, original_size="4x6"
    )
    assert file_4x6.ok is True
    p_4x6 = Path(file_4x6.path)
    from PIL import Image

    with Image.open(p) as im_a4, Image.open(p_4x6) as im_4x6:
        assert im_4x6.size[0] < im_a4.size[0]
        assert im_4x6.size[1] < im_a4.size[1]
    p_4x6.unlink(missing_ok=True)

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
async def test_cancel_scan_between_jobs_does_not_affect_next_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kopi.hardware.scanner import MockScannerBridge, RealScannerBridge

    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    mock_bridge = MockScannerBridge()
    assert await mock_bridge.cancel_scan() is False
    mock_res = await mock_bridge.scan_pdf(duplex=False, resolution_dpi=150, color=True)
    assert mock_res.ok is True

    real_bridge = RealScannerBridge()
    assert await real_bridge.cancel_scan() is False

    class FakeJpegProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"\xff\xd8\xff\xe0\x00\x10JFIF\xff\xd9", b""

        async def wait(self) -> int:
            return 0

    async def fake_subprocess_exec(*_args: str, **_kwargs: object) -> FakeJpegProc:
        return FakeJpegProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess_exec)
    real_res = await real_bridge.scan_pdf(
        duplex=False, resolution_dpi=150, color=True, output_format="jpeg"
    )
    assert real_res.ok is True



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


@pytest.mark.asyncio
async def test_list_scan_devices_async_coalesces_caches_and_skips_when_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kopi.hardware.scanner as scanner_mod
    from kopi.hardware import list_scan_devices_async, reset_bridges

    reset_bridges()
    calls = 0

    def fake_list_scan_devices(_timeout_sec: int = 8) -> list[str]:
        nonlocal calls
        calls += 1
        return ["hpaio:/usb/HP_OfficeJet_Pro_9010"]

    monkeypatch.setattr(scanner_mod, "list_scan_devices", fake_list_scan_devices)

    # When busy before any cache exists, returns [] without invoking scanimage -L
    assert await list_scan_devices_async(is_busy=True) == []
    assert calls == 0

    # Concurrent callers coalesce into a single thread invocation and populate cache
    r1, r2 = await asyncio.gather(
        list_scan_devices_async(is_busy=False),
        list_scan_devices_async(is_busy=False),
    )
    assert r1 == ["hpaio:/usb/HP_OfficeJet_Pro_9010"]
    assert r2 == ["hpaio:/usb/HP_OfficeJet_Pro_9010"]
    assert calls == 1

    # When busy after cache is populated, returns cached list without calling scanimage -L
    assert await list_scan_devices_async(is_busy=True, force_refresh=True) == [
        "hpaio:/usb/HP_OfficeJet_Pro_9010"
    ]
    assert calls == 1



