"""TDD tests for HP OfficeJet Pro 9010 Copy Settings (enhancements, CUPS flags, defaults)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageStat

from kopi.hardware import DuplexMode, build_lp_cmd, reset_bridges
from kopi.main import create_app
from kopi.processing.copy_enhance import apply_copy_enhancements_to_image


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    reset_bridges()
    return create_app()


def test_lighter_darker_and_resize_image_enhancements() -> None:
    # Create a mid-gray 200x300 image
    base = Image.new("RGB", (200, 300), color=(128, 128, 128))
    base_mean = ImageStat.Stat(base).mean[0]

    # Lighter (-3) should increase mean brightness
    lighter = apply_copy_enhancements_to_image(
        base,
        lighter_darker=-3,
        content_type="mixed",
        resize_mode="actual",
        resize_percent=100,
    )
    assert ImageStat.Stat(lighter).mean[0] > base_mean

    # Darker (+3) should decrease mean brightness
    darker = apply_copy_enhancements_to_image(
        base,
        lighter_darker=3,
        content_type="text",
        resize_mode="actual",
        resize_percent=100,
    )
    assert ImageStat.Stat(darker).mean[0] < base_mean

    # Custom resize 50% keeps canvas dimensions (200x300) with white margin padding
    resized_half = apply_copy_enhancements_to_image(
        base,
        lighter_darker=0,
        content_type="mixed",
        resize_mode="custom",
        resize_percent=50,
    )
    assert resized_half.size == (200, 300)
    # Since 50% of the gray box is surrounded by white (255), overall mean brightness increases
    assert ImageStat.Stat(resized_half).mean[0] > base_mean


def test_build_lp_cmd_hp9010_advanced_options() -> None:
    cmd = build_lp_cmd(
        "/tmp/job.pdf",
        job_name="kopi-copy",
        device="HP_OfficeJet_Pro_9010",
        copies=3,
        duplex=DuplexMode.SHORT_EDGE,
        color=True,
        paper_size="Letter",
        collate=True,
        resize_mode="two_on_one",
        quality="best",
    )
    assert "-n" in cmd and cmd[cmd.index("-n") + 1] == "3"
    assert "sides=two-sided-short-edge" in cmd
    assert "media=Letter" in cmd
    assert "collate=true" in cmd
    assert "number-up=2" in cmd
    assert "print-quality=5" in cmd

    cmd_fit = build_lp_cmd(
        "/tmp/job.pdf",
        copies=2,
        collate=False,
        resize_mode="fit_to_page",
        quality="draft",
    )
    assert "collate=false" in cmd_fit
    assert "fit-to-page" in cmd_fit
    assert "print-quality=3" in cmd_fit


@pytest.mark.asyncio
async def test_copy_defaults_get_and_save(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_get = await client.get("/api/copy/defaults")
        assert res_get.status_code == 200
        defaults = res_get.json()
        assert defaults["sided_mode"] == "1_to_1"
        assert defaults["color"] is True
        assert defaults["quality"] == "normal"
        assert defaults["lighter_darker"] == 0
        assert defaults["resize_mode"] == "actual"
        assert defaults["collate"] is True

        new_defaults = {
            "sided_mode": "1_to_2",
            "color": False,
            "source": "adf",
            "quality": "best",
            "lighter_darker": 2,
            "resize_mode": "full_page_91",
            "resize_percent": 91,
            "original_size": "A4",
            "paper_size": "A4",
            "page_flip": "short_edge",
            "collate": False,
            "content_type": "text",
        }
        res_put = await client.put("/api/copy/defaults", json=new_defaults)
        assert res_put.status_code == 200
        assert res_put.json()["ok"] is True

        res_get2 = await client.get("/api/copy/defaults")
        assert res_get2.status_code == 200
        saved = res_get2.json()
        assert saved["sided_mode"] == "1_to_2"
        assert saved["color"] is False
        assert saved["quality"] == "best"
        assert saved["lighter_darker"] == 2
        assert saved["resize_mode"] == "full_page_91"
        assert saved["page_flip"] == "short_edge"
        assert saved["collate"] is False
        assert saved["content_type"] == "text"


@pytest.mark.asyncio
async def test_scan_and_print_with_hp9010_settings(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scan_res = await client.post(
            "/api/scan",
            json={
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "source": "flatbed",
                "original_size": "A4",
                "lighter_darker": 1,
                "content_type": "text",
                "resize_mode": "full_page_91",
                "resize_percent": 91,
            },
        )
        assert scan_res.status_code == 200
        scan_id = scan_res.json()["scan_id"]

        print_res = await client.post(
            "/api/print",
            json={
                "scan_id": scan_id,
                "copies": 2,
                "duplex": True,
                "page_flip": "short_edge",
                "color": True,
                "paper_size": "A4",
                "collate": True,
                "resize_mode": "full_page_91",
                "quality": "normal",
            },
        )
        assert print_res.status_code == 200
        assert print_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_multi_page_flatbed_scan_append_and_print(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pypdf import PdfReader
    from kopi.hardware import PrintResult, get_printer

    printer = get_printer()
    printed_pdf_pages: list[int] = []

    async def spy_print_file(
        file_path: str,
        **_kwargs: object,
    ) -> PrintResult:
        p = Path(file_path)
        assert p.suffix.lower() == ".pdf"
        reader = PdfReader(str(p))
        printed_pdf_pages.append(len(reader.pages))
        return PrintResult(ok=True, stderr="", user_message=None, job_id="flatbed-multi-1")

    monkeypatch.setattr(printer, "print_file", spy_print_file)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Page 1 scan from flatbed
        res1 = await client.post(
            "/api/scan",
            json={
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "source": "flatbed",
            },
        )
        assert res1.status_code == 200
        data1 = res1.json()
        scan_id = data1["scan_id"]
        assert data1["pages"] == 1

        # Page 2 scan from flatbed appended to the same scan_id
        res2 = await client.post(
            "/api/scan",
            json={
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "source": "flatbed",
                "append_to_scan_id": scan_id,
            },
        )
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["scan_id"] == scan_id
        assert data2["pages"] == 2

        # Finish & Print combines the 2 flatbed PNGs into a 2-page PDF
        print_res = await client.post(
            "/api/print",
            json={
                "scan_id": scan_id,
                "copies": 1,
                "duplex": True,
                "color": True,
                "paper_size": "A4",
            },
        )
        assert print_res.status_code == 200
        assert print_res.json()["ok"] is True
        assert printed_pdf_pages == [2]


@pytest.mark.asyncio
async def test_copy_preview_image_and_rotate(app: FastAPI) -> None:
    import io

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
        scan_id = scan_res.json()["scan_id"]

        # Fetch page 0 preview image
        prev_res = await client.get(f"/api/copy/preview/{scan_id}?page=0")
        assert prev_res.status_code == 200
        assert prev_res.headers["content-type"].startswith("image/png")
        img_before = Image.open(io.BytesIO(prev_res.content))
        w_before, h_before = img_before.size

        # Rotate page 0 by 90 degrees clockwise
        rot_res = await client.post(f"/api/copy/preview/{scan_id}/rotate?page=0")
        assert rot_res.status_code == 200
        assert rot_res.json()["ok"] is True

        # Fetch page 0 preview again — dimensions should be swapped (rotated 90 deg)
        prev_after = await client.get(f"/api/copy/preview/{scan_id}?page=0")
        assert prev_after.status_code == 200
        img_after = Image.open(io.BytesIO(prev_after.content))
        assert img_after.size == (h_before, w_before)

