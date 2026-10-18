"""TDD tests for Print from USB workflow (/api/usb/files, /api/usb/preview, /api/usb/print)."""

from __future__ import annotations

import io
from pathlib import Path

import img2pdf
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

from kopi.hardware import reset_bridges
from kopi.main import create_app


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    reset_bridges()
    return create_app()


def _create_sample_two_page_pdf(dest: Path) -> None:
    pages: list[bytes] = []
    for color in ((220, 40, 40), (40, 120, 220)):
        img = Image.new("RGB", (300, 400), color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        pages.append(buf.getvalue())
    pdf_bytes = img2pdf.convert(pages)
    assert pdf_bytes is not None
    dest.write_bytes(bytes(pdf_bytes))


@pytest.mark.asyncio
async def test_usb_browse_files_and_path_traversal_protection(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usb_dir = tmp_path / "usb_print_drive"
    usb_dir.mkdir(parents=True)
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))

    # Create subfolders, printable files, hidden files, and unsupported files
    _create_sample_two_page_pdf(usb_dir / "report.pdf")
    img = Image.new("RGB", (200, 150), color=(30, 180, 90))
    img.save(usb_dir / "photo.png", format="PNG")
    (usb_dir / "notes.txt").write_text("Hello Kopi USB Print\nLine 2", encoding="utf-8")
    (usb_dir / ".hidden.pdf").write_bytes(b"hidden")
    (usb_dir / "archive.zip").write_bytes(b"zipdata")

    sub = usb_dir / "Invoices"
    sub.mkdir()
    _create_sample_two_page_pdf(sub / "inv_01.pdf")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/usb/files", params={"mount_path": str(usb_dir)})
        assert res.status_code == 200
        data = res.json()
        entries = data["entries"]
        names = [e["name"] for e in entries]
        assert "Invoices" in names
        assert "report.pdf" in names
        assert "photo.png" in names
        assert "notes.txt" in names
        assert ".hidden.pdf" not in names
        assert "archive.zip" not in names

        by_name = {e["name"]: e for e in entries}
        assert by_name["Invoices"]["is_dir"] is True
        assert by_name["report.pdf"]["pages"] == 2

        # Browse into subfolder
        sub_res = await client.get(
            "/api/usb/files",
            params={"mount_path": str(usb_dir), "subpath": "Invoices"},
        )
        assert sub_res.status_code == 200
        sub_entries = sub_res.json()["entries"]
        assert [e["name"] for e in sub_entries] == ["inv_01.pdf"]

        # Reject path traversal outside USB mount
        trav_res = await client.get(
            "/api/usb/files",
            params={"mount_path": str(usb_dir), "subpath": "../../etc"},
        )
        assert trav_res.status_code == 400


@pytest.mark.asyncio
async def test_usb_preview_and_print_workflow(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usb_dir = tmp_path / "usb_print_exec"
    usb_dir.mkdir(parents=True)
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))

    _create_sample_two_page_pdf(usb_dir / "brochure.pdf")
    img = Image.new("RGB", (240, 180), color=(100, 50, 200))
    img.save(usb_dir / "badge.jpg", format="JPEG")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Preview page 0 and page 1 of brochure.pdf
        prev0 = await client.get(
            "/api/usb/preview",
            params={"mount_path": str(usb_dir), "path": "brochure.pdf", "page": 0},
        )
        assert prev0.status_code == 200
        assert prev0.headers["content-type"] == "image/png"

        prev1 = await client.get(
            "/api/usb/preview",
            params={"mount_path": str(usb_dir), "path": "brochure.pdf", "page": 1},
        )
        assert prev1.status_code == 200

        # 2. Preview JPEG image on USB
        prev_jpg = await client.get(
            "/api/usb/preview",
            params={"mount_path": str(usb_dir), "path": "badge.jpg", "page": 0},
        )
        assert prev_jpg.status_code == 200
        assert prev_jpg.headers["content-type"] == "image/png"

        # 3. Print brochure.pdf with 2 copies, duplex short_edge
        pr_pdf = await client.post(
            "/api/usb/print",
            json={
                "mount_path": str(usb_dir),
                "path": "brochure.pdf",
                "copies": 2,
                "duplex": True,
                "page_flip": "short_edge",
                "color": True,
                "paper_size": "A4",
                "collate": True,
                "resize_mode": "fit_to_page",
                "quality": "normal",
            },
        )
        assert pr_pdf.status_code == 200
        assert pr_pdf.json()["ok"] is True
        assert pr_pdf.json()["copies"] == 2

        # 4. Print badge.jpg from USB
        pr_jpg = await client.post(
            "/api/usb/print",
            json={
                "mount_path": str(usb_dir),
                "path": "badge.jpg",
                "copies": 1,
                "duplex": False,
                "color": False,
                "paper_size": "A4",
                "quality": "best",
            },
        )
        assert pr_jpg.status_code == 200
        assert pr_jpg.json()["ok"] is True
