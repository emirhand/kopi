"""Integration tests for the Copy workflow and hardware/health endpoints (TDD)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kopi.hardware import (
    DuplexMode,
    PrintResult,
    ScanFileResult,
    ScanSource,
    get_hardware_lock,
    reset_bridges,
)
from kopi.main import create_app


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    reset_bridges()
    return create_app()


@pytest.mark.asyncio
async def test_health_and_hardware_endpoints(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_health = await client.get("/api/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

        res_hw = await client.get("/api/hardware")
        assert res_hw.status_code == 200
        body = res_hw.json()
        assert "scanners" in body
        assert "printers" in body
        assert "usb_volumes" in body
        assert body["busy"] is False


@pytest.mark.asyncio
async def test_two_step_scan_and_print_copy_flow(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scan_res = await client.post(
            "/api/scan",
            json={
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "source": "flatbed",
            },
        )
        assert scan_res.status_code == 200
        scan_data = scan_res.json()
        assert "scan_id" in scan_data
        assert scan_data["bytes"] > 0

        print_res = await client.post(
            "/api/print",
            json={
                "scan_id": scan_data["scan_id"],
                "copies": 3,
                "duplex": False,
                "color": True,
                "paper_size": "A4",
            },
        )
        assert print_res.status_code == 200
        print_data = print_res.json()
        assert print_data["ok"] is True
        assert print_data["copies"] == 3


@pytest.mark.asyncio
async def test_print_failure_restores_scan_for_retry(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kopi.hardware import get_printer

    printer = get_printer()
    calls = 0

    async def flaky_print_file(
        file_path: str,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
        **_kwargs: object,
    ) -> PrintResult:
        nonlocal calls
        _ = file_path, copies, duplex, color, paper_size, job_name, device, timeout_sec
        calls += 1
        if calls == 1:
            return PrintResult(ok=False, stderr="lp: media empty", user_message="No Paper")
        return PrintResult(ok=True, stderr="", user_message=None, job_id="retry-ok-1")

    monkeypatch.setattr(printer, "print_file", flaky_print_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scan_res = await client.post("/api/scan", json={"duplex": False, "color": True})
        scan_id = scan_res.json()["scan_id"]

        # First print fails with No Paper
        fail_res = await client.post("/api/print", json={"scan_id": scan_id, "copies": 2})
        assert fail_res.status_code == 400
        assert "No Paper" in fail_res.json()["detail"]

        # Second print with the SAME scan_id succeeds without re-scanning
        retry_res = await client.post("/api/print", json={"scan_id": scan_id, "copies": 2})
        assert retry_res.status_code == 200
        assert retry_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_direct_one_tap_copy_endpoint(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kopi.hardware import get_printer, get_scanner

    scanner = get_scanner()
    printer = get_printer()
    recorded: dict[str, object] = {}

    orig_scan = scanner.scan_copy_file

    async def spy_scan(
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        resolution_dpi: int = 300,
        color: bool = True,
        timeout_sec: int = 300,
        **_kwargs: object,
    ) -> ScanFileResult:
        recorded["scan_source"] = source
        recorded["scan_dpi"] = resolution_dpi
        recorded["scan_color"] = color
        return await orig_scan(
            duplex=duplex,
            source=source,
            device=device,
            resolution_dpi=resolution_dpi,
            color=color,
            timeout_sec=timeout_sec,
        )

    orig_print = printer.print_file

    async def spy_print(
        file_path: str,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
        **_kwargs: object,
    ) -> PrintResult:
        recorded["print_copies"] = copies
        recorded["print_duplex"] = duplex
        recorded["print_color"] = color
        recorded["print_paper_size"] = paper_size
        return await orig_print(
            file_path,
            copies=copies,
            duplex=duplex,
            color=color,
            paper_size=paper_size,
            job_name=job_name,
            device=device,
            timeout_sec=timeout_sec,
        )

    monkeypatch.setattr(scanner, "scan_copy_file", spy_scan)
    monkeypatch.setattr(printer, "print_file", spy_print)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/copy",
            json={
                "copies": 4,
                "duplex": True,
                "color": False,
                "resolution_dpi": 600,
                "source": "adf_duplex",
                "paper_size": "A4",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["copies"] == 4
        assert recorded["scan_source"] is ScanSource.ADF_DUPLEX
        assert recorded["scan_dpi"] == 600
        assert recorded["scan_color"] is False
        assert recorded["print_copies"] == 4
        assert recorded["print_color"] is False
        assert recorded["print_paper_size"] == "A4"


@pytest.mark.asyncio
async def test_copy_returns_409_when_hardware_busy(app: FastAPI) -> None:
    lock = get_hardware_lock()
    async with lock.acquire("existing-scan"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/scan", json={"duplex": False, "color": True})
            assert res.status_code == 409
            assert "existing-scan" in res.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_copy_endpoint(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/copy/cancel")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "scan_cancelled" in data
        assert "print_cancelled" in data


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scan_duplex", "print_duplex", "expected_source"),
    [
        (False, False, ScanSource.ADF),         # 1 -> 1
        (False, True, ScanSource.ADF),          # 1 -> 2 (Single scan -> Duplex print)
        (True, True, ScanSource.ADF_DUPLEX),    # 2 -> 2 (Duplex scan -> Duplex print)
        (True, False, ScanSource.ADF_DUPLEX),   # 2 -> 1 (Duplex scan -> Single print)
    ],
)
async def test_all_four_scan_to_print_sided_modes(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    scan_duplex: bool,
    print_duplex: bool,
    expected_source: ScanSource,
) -> None:
    from kopi.hardware import get_printer, get_scanner

    scanner = get_scanner()
    printer = get_printer()
    recorded: dict[str, object] = {}

    orig_scan = scanner.scan_copy_file

    async def spy_scan(
        *,
        duplex: bool = False,
        source: ScanSource | None = None,
        device: str | None = None,
        resolution_dpi: int = 300,
        color: bool = True,
        timeout_sec: int = 300,
        **_kwargs: object,
    ) -> ScanFileResult:
        recorded["scan_duplex"] = duplex
        recorded["scan_source"] = source
        return await orig_scan(
            duplex=duplex,
            source=source,
            device=device,
            resolution_dpi=resolution_dpi,
            color=color,
            timeout_sec=timeout_sec,
        )

    orig_print = printer.print_file

    async def spy_print(
        file_path: str,
        *,
        copies: int = 1,
        duplex: bool | DuplexMode = False,
        color: bool = True,
        paper_size: str | None = None,
        job_name: str = "kopi-job",
        device: str | None = None,
        timeout_sec: int = 120,
        **_kwargs: object,
    ) -> PrintResult:
        recorded["print_duplex"] = duplex
        return await orig_print(
            file_path,
            copies=copies,
            duplex=duplex,
            color=color,
            paper_size=paper_size,
            job_name=job_name,
            device=device,
            timeout_sec=timeout_sec,
        )

    monkeypatch.setattr(scanner, "scan_copy_file", spy_scan)
    monkeypatch.setattr(printer, "print_file", spy_print)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test via two-step /api/scan -> /api/print (used by CopyMenu UI)
        scan_res = await client.post(
            "/api/scan",
            json={
                "duplex": scan_duplex,
                "color": True,
                "resolution_dpi": 300,
                "source": expected_source.value,
            },
        )
        assert scan_res.status_code == 200
        scan_id = scan_res.json()["scan_id"]
        assert recorded["scan_duplex"] is scan_duplex
        assert recorded["scan_source"] is expected_source

        print_res = await client.post(
            "/api/print",
            json={
                "scan_id": scan_id,
                "copies": 1,
                "duplex": print_duplex,
                "color": True,
            },
        )
        assert print_res.status_code == 200
        assert recorded["print_duplex"] is print_duplex

        # Test via one-step /api/copy with explicit scan_duplex and print_duplex
        copy_res = await client.post(
            "/api/copy",
            json={
                "copies": 1,
                "scan_duplex": scan_duplex,
                "print_duplex": print_duplex,
                "source": expected_source.value,
            },
        )
        assert copy_res.status_code == 200
        assert recorded["scan_duplex"] is scan_duplex
        assert recorded["print_duplex"] is print_duplex


