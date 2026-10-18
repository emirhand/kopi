"""TDD tests for Scan workflows (/api/scan/email, /api/scan/usb, /api/scan/archive)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kopi.config import SmtpConfig, load_settings, save_settings
from kopi.hardware import reset_bridges
from kopi.main import create_app


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    reset_bridges()
    return create_app()


@pytest.mark.asyncio
async def test_scan_to_archive_pdf_and_jpg(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_dir = tmp_path / "archive"
    monkeypatch.setenv("KOPI_ARCHIVE_DIR", str(archive_dir))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_pdf = await client.post(
            "/api/scan/archive",
            json={
                "duplex": False,
                "color": True,
                "resolution": "standard",
                "output_format": "pdf",
                "remove_blank_pages": True,
            },
        )
        assert res_pdf.status_code == 200
        assert res_pdf.json()["ok"] is True
        saved_pdfs = list(archive_dir.glob("*.pdf"))
        assert len(saved_pdfs) == 1

        res_jpg = await client.post(
            "/api/scan/archive",
            json={
                "duplex": False,
                "color": False,
                "resolution": "high",
                "output_format": "jpg",
                "remove_blank_pages": False,
            },
        )
        assert res_jpg.status_code == 200
        assert res_jpg.json()["ok"] is True
        saved_jpgs = list(archive_dir.glob("*.jpg"))
        assert len(saved_jpgs) == 1


@pytest.mark.asyncio
async def test_scan_to_usb(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    usb_dir = tmp_path / "usb_drive"
    usb_dir.mkdir(parents=True)
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/scan/usb",
            json={
                "mount_path": str(usb_dir),
                "duplex": True,
                "color": True,
                "resolution": "high",
                "output_format": "pdf",
                "remove_blank_pages": False,
            },
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True
        files = list(usb_dir.glob("scan-*.pdf"))
        assert len(files) == 1


@pytest.mark.asyncio
async def test_scan_to_email(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = load_settings()
    settings.smtp = SmtpConfig(
        host="smtp.example.com",
        port=587,
        user="kopi@example.com",
        password="pw",
        from_email="kopi@example.com",
        tls=True,
    )
    save_settings(settings)

    import kopi.processing.mailer as mailer_mod

    monkeypatch.setattr(
        mailer_mod,
        "send_attachment_email",
        lambda *_a, **_kw: (True, None),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/api/scan/email",
            json={
                "recipient": "person@example.com",
                "duplex": False,
                "color": True,
                "resolution": "standard",
                "output_format": "pdf",
                "remove_blank_pages": False,
            },
        )
        assert res.status_code == 200
        assert res.json()["ok"] is True


def test_usb_storage_filtering_excludes_non_storage_and_system_devices() -> None:
    """Ensure only genuine removable USB mass-storage volumes are returned."""
    from kopi.hardware.usb import parse_usb_volumes_from_lsblk

    sample_lsblk = [
        # 1. Internal NVMe OS drive -> must be excluded
        {
            "path": "/dev/nvme0n1",
            "name": "nvme0n1",
            "type": "disk",
            "tran": "nvme",
            "rm": False,
            "ro": False,
            "size": 512110190592,
            "children": [
                {
                    "path": "/dev/nvme0n1p1",
                    "name": "nvme0n1p1",
                    "type": "part",
                    "mountpoint": "/",
                    "fstype": "ext4",
                    "size": 512000000000,
                }
            ],
        },
        # 2. HP OfficeJet 9010 unpopulated USB card-reader / stub LUN (0 bytes) -> must be excluded
        {
            "path": "/dev/sda",
            "name": "sda",
            "type": "disk",
            "tran": "usb",
            "rm": True,
            "ro": False,
            "size": 0,
            "model": "HP OfficeJet Pro 9010",
            "fstype": None,
        },
        # 3. USB virtual CD-ROM / read-only iso9660 -> must be excluded
        {
            "path": "/dev/sr0",
            "name": "sr0",
            "type": "rom",
            "tran": "usb",
            "rm": True,
            "ro": True,
            "size": 104857600,
            "fstype": "iso9660",
            "label": "HP Smart Install",
        },
        # 4. USB disk containing root/boot OS partition -> system partitions must be excluded
        {
            "path": "/dev/sdb",
            "name": "sdb",
            "type": "disk",
            "tran": "usb",
            "rm": False,
            "ro": False,
            "size": 64000000000,
            "model": "USB SSD OS",
            "children": [
                {
                    "path": "/dev/sdb1",
                    "name": "sdb1",
                    "type": "part",
                    "mountpoint": "/boot/efi",
                    "fstype": "vfat",
                    "size": 536870912,
                },
                {
                    "path": "/dev/sdb2",
                    "name": "sdb2",
                    "type": "part",
                    "mountpoint": "[SWAP]",
                    "fstype": "swap",
                    "size": 4294967296,
                },
            ],
        },
        # 5. Genuine SanDisk USB Flash Drive with FAT32 partition -> MUST BE INCLUDED
        {
            "path": "/dev/sdc",
            "name": "sdc",
            "type": "disk",
            "tran": "usb",
            "rm": True,
            "ro": False,
            "size": 15931539456,
            "model": "Ultra Fit",
            "children": [
                {
                    "path": "/dev/sdc1",
                    "name": "sdc1",
                    "type": "part",
                    "mountpoint": "/run/media/kopi/SANDISK",
                    "fstype": "vfat",
                    "label": "SANDISK",
                    "size": 15930000000,
                    "rm": True,
                    "ro": False,
                }
            ],
        },
        # 6. Genuine Kingston USB Flash Drive (unmounted exFAT partition) -> MUST BE INCLUDED
        {
            "path": "/dev/sdd",
            "name": "sdd",
            "type": "disk",
            "tran": "usb",
            "rm": True,
            "ro": False,
            "size": 31914983424,
            "model": "DataTraveler",
            "children": [
                {
                    "path": "/dev/sdd1",
                    "name": "sdd1",
                    "type": "part",
                    "mountpoint": None,
                    "fstype": "exfat",
                    "label": "KINGSTON",
                    "size": 31900000000,
                    "rm": True,
                    "ro": False,
                }
            ],
        },
    ]

    vols = parse_usb_volumes_from_lsblk(sample_lsblk)
    devices = [v.device for v in vols]
    assert devices == ["/dev/sdd1", "/dev/sdc1"] or set(devices) == {"/dev/sdc1", "/dev/sdd1"}
    by_dev = {v.device: v for v in vols}
    assert by_dev["/dev/sdc1"].label == "SANDISK"
    assert by_dev["/dev/sdc1"].fstype == "vfat"
    assert by_dev["/dev/sdc1"].mounted is True
    assert by_dev["/dev/sdd1"].label == "KINGSTON"
    assert by_dev["/dev/sdd1"].fstype == "exfat"
    assert by_dev["/dev/sdd1"].mounted is False


@pytest.mark.asyncio
async def test_multi_step_flatbed_scan_to_email_usb_and_archive(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-page flatbed scans (/api/scan + append_to_scan_id) can be delivered to Email, USB, or Archive."""
    from pypdf import PdfReader

    usb_dir = tmp_path / "usb_flash"
    usb_dir.mkdir(parents=True)
    archive_dir = tmp_path / "archive_multi"
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))
    monkeypatch.setenv("KOPI_ARCHIVE_DIR", str(archive_dir))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. List USB storage drives endpoint
        drives_res = await client.get("/api/scan/usb/drives")
        assert drives_res.status_code == 200
        drives = drives_res.json()["drives"]
        assert len(drives) == 1
        assert drives[0]["mountpoint"] == str(usb_dir)

        # 2. Scan 2 pages step-by-step on Flatbed and save to selected USB drive
        p1 = await client.post(
            "/api/scan",
            json={"source": "flatbed", "duplex": False, "color": True, "resolution_dpi": 300},
        )
        assert p1.status_code == 200
        scan_id_usb = p1.json()["scan_id"]
        assert p1.json()["pages"] == 1

        p2 = await client.post(
            "/api/scan",
            json={
                "source": "flatbed",
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "append_to_scan_id": scan_id_usb,
            },
        )
        assert p2.status_code == 200
        assert p2.json()["pages"] == 2

        usb_res = await client.post(
            "/api/scan/usb",
            json={
                "scan_id": scan_id_usb,
                "device": drives[0]["device"],
                "mount_path": drives[0]["mountpoint"],
                "output_format": "pdf",
                "remove_blank_pages": False,
            },
        )
        assert usb_res.status_code == 200
        usb_pdfs = list(usb_dir.glob("scan-*.pdf"))
        assert len(usb_pdfs) == 1
        assert len(PdfReader(str(usb_pdfs[0])).pages) == 2

        # 3. Scan 2 pages on Flatbed and save to Archive
        a1 = await client.post(
            "/api/scan",
            json={"source": "flatbed", "duplex": False, "color": True, "resolution_dpi": 300},
        )
        scan_id_arch = a1.json()["scan_id"]
        await client.post(
            "/api/scan",
            json={
                "source": "flatbed",
                "duplex": False,
                "color": True,
                "resolution_dpi": 300,
                "append_to_scan_id": scan_id_arch,
            },
        )
        arch_res = await client.post(
            "/api/scan/archive",
            json={
                "scan_id": scan_id_arch,
                "output_format": "pdf",
                "remove_blank_pages": False,
            },
        )
        assert arch_res.status_code == 200
        arch_pdfs = list(archive_dir.glob("scan-*.pdf"))
        assert len(arch_pdfs) == 1
        assert len(PdfReader(str(arch_pdfs[0])).pages) == 2


@pytest.mark.asyncio
async def test_scan_custom_filename_email_usb_and_archive(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Custom filenames are sanitized, given the proper extension, and avoid overwriting existing files."""
    usb_dir = tmp_path / "usb_custom"
    usb_dir.mkdir(parents=True)
    archive_dir = tmp_path / "archive_custom"
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))
    monkeypatch.setenv("KOPI_ARCHIVE_DIR", str(archive_dir))

    captured_filenames: list[str] = []
    import kopi.processing.mailer as mailer_mod

    def fake_send_attachment_email(
        _data: bytes,
        *,
        filename: str,
        to_addr: str,
        subject: str,
        smtp: object,
    ) -> tuple[bool, str | None]:
        _ = (to_addr, subject, smtp)
        captured_filenames.append(filename)
        return True, None

    monkeypatch.setattr(mailer_mod, "send_attachment_email", fake_send_attachment_email)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Custom filename in Scan to Email (even if user typed .pdf or path chars)
        email_res = await client.post(
            "/api/scan/email",
            json={
                "recipient": "user@example.com",
                "filename": "../Tax_Return_2026.pdf",
                "output_format": "pdf",
            },
        )
        assert email_res.status_code == 200
        assert captured_filenames == ["Tax_Return_2026.pdf"]

        # 2. Custom filename in Scan to USB + duplicate collision prevention
        usb_res1 = await client.post(
            "/api/scan/usb",
            json={
                "mount_path": str(usb_dir),
                "filename": "receipt_october",
                "output_format": "pdf",
            },
        )
        assert usb_res1.status_code == 200
        assert (usb_dir / "receipt_october.pdf").is_file()

        usb_res2 = await client.post(
            "/api/scan/usb",
            json={
                "mount_path": str(usb_dir),
                "filename": "receipt_october",
                "output_format": "pdf",
            },
        )
        assert usb_res2.status_code == 200
        assert (usb_dir / "receipt_october-1.pdf").is_file()

        # 3. Custom filename in Scan to Archive (JPG)
        arch_res = await client.post(
            "/api/scan/archive",
            json={
                "filename": "family photo",
                "output_format": "jpg",
            },
        )
        assert arch_res.status_code == 200
        assert (archive_dir / "family_photo.jpg").is_file()


@pytest.mark.asyncio
async def test_multipage_jpg_png_numbered_files_and_tiff_support(
    app: FastAPI, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multi-page JPG/PNG scans save one sequentially numbered file per page; TIFF saves multi-page TIFF."""
    from PIL import Image

    usb_dir = tmp_path / "usb_formats"
    usb_dir.mkdir(parents=True)
    archive_dir = tmp_path / "archive_formats"
    monkeypatch.setenv("KOPI_MOCK_USB_DIR", str(usb_dir))
    monkeypatch.setenv("KOPI_ARCHIVE_DIR", str(archive_dir))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Scan 3 pages on Flatbed and save as PNG to USB -> must create page-1.png, page-2.png, page-3.png
        r1 = await client.post(
            "/api/scan",
            json={"source": "flatbed", "duplex": False, "color": True, "resolution_dpi": 300},
        )
        sid_png = r1.json()["scan_id"]
        await client.post(
            "/api/scan",
            json={"source": "flatbed", "append_to_scan_id": sid_png},
        )
        await client.post(
            "/api/scan",
            json={"source": "flatbed", "append_to_scan_id": sid_png},
        )

        usb_png_res = await client.post(
            "/api/scan/usb",
            json={
                "scan_id": sid_png,
                "mount_path": str(usb_dir),
                "filename": "contract",
                "output_format": "png",
            },
        )
        assert usb_png_res.status_code == 200
        body_png = usb_png_res.json()
        assert body_png["ok"] is True
        assert body_png["filenames"] == ["contract-1.png", "contract-2.png", "contract-3.png"]
        for fname in body_png["filenames"]:
            p = usb_dir / fname
            assert p.is_file()
            with Image.open(p) as im:
                assert im.format == "PNG"

        # 2. Scan 2 pages on Flatbed and save as JPG to Archive -> notes-1.jpg, notes-2.jpg
        j1 = await client.post(
            "/api/scan",
            json={"source": "flatbed", "duplex": False, "color": True, "resolution_dpi": 300},
        )
        sid_jpg = j1.json()["scan_id"]
        await client.post(
            "/api/scan",
            json={"source": "flatbed", "append_to_scan_id": sid_jpg},
        )

        arch_jpg_res = await client.post(
            "/api/scan/archive",
            json={
                "scan_id": sid_jpg,
                "filename": "notes",
                "output_format": "jpg",
            },
        )
        assert arch_jpg_res.status_code == 200
        assert arch_jpg_res.json()["filenames"] == ["notes-1.jpg", "notes-2.jpg"]
        assert (archive_dir / "notes-1.jpg").is_file()
        assert (archive_dir / "notes-2.jpg").is_file()

        # 3. Scan 2 pages on Flatbed and save as multi-page TIFF to Archive -> ledger.tiff
        t1 = await client.post(
            "/api/scan",
            json={"source": "flatbed", "duplex": False, "color": True, "resolution_dpi": 300},
        )
        sid_tiff = t1.json()["scan_id"]
        await client.post(
            "/api/scan",
            json={"source": "flatbed", "append_to_scan_id": sid_tiff},
        )

        arch_tiff_res = await client.post(
            "/api/scan/archive",
            json={
                "scan_id": sid_tiff,
                "filename": "ledger",
                "output_format": "tiff",
            },
        )
        assert arch_tiff_res.status_code == 200
        assert (archive_dir / "ledger.tiff").is_file()
        with Image.open(archive_dir / "ledger.tiff") as tif_img:
            assert tif_img.format == "TIFF"
            assert getattr(tif_img, "n_frames", 1) == 2



