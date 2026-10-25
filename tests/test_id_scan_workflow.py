"""TDD tests for ID Card Copy / Scan workflow (/api/id-scan/* and /api/settings/public)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

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
async def test_id_scan_full_wizard_flow(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import kopi.processing.mailer as mailer_mod

    monkeypatch.setattr(
        mailer_mod,
        "send_pdf_email",
        lambda *_a, **_kw: (True, None),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Public settings endpoint
        pub_res = await client.get("/api/settings/public")
        assert pub_res.status_code == 200
        assert "id_scan_ocr" in pub_res.json()

        # 2. Scan front
        front_res = await client.post("/api/id-scan/front")
        assert front_res.status_code == 200
        front_data = front_res.json()
        assert front_data["ok"] is True
        session_id = front_data["session_id"]

        # 3. Scan back
        back_res = await client.post("/api/id-scan/back", json={"session_id": session_id})
        assert back_res.status_code == 200
        assert back_res.json()["ok"] is True

        # 4. Compose onto A4 PDF and get base64 preview
        comp_res = await client.post("/api/id-scan/compose", json={"session_id": session_id})
        assert comp_res.status_code == 200
        comp_data = comp_res.json()
        assert comp_data["ok"] is True
        assert isinstance(comp_data["preview_base64"], str)
        assert len(comp_data["preview_base64"]) > 100

        # 5. Print composed ID card page
        print_res = await client.post("/api/id-scan/print", json={"session_id": session_id})
        assert print_res.status_code == 200
        assert print_res.json()["ok"] is True

        # 6. Email composed ID card PDF
        email_res = await client.post(
            "/api/id-scan/email",
            json={"session_id": session_id, "recipient": "id@example.com"},
        )
        assert email_res.status_code == 200
        assert email_res.json()["ok"] is True

        # 7. Discard session
        disc_res = await client.post("/api/id-scan/discard", json={"session_id": session_id})
        assert disc_res.status_code == 200
        assert disc_res.json()["ok"] is True


@pytest.mark.asyncio
async def test_id_scan_compose_cleans_up_temp_pdfs_on_ocr_exception(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    import kopi.api.id_scan as id_scan_mod
    from kopi.config import load_settings, save_settings

    settings = load_settings()
    settings.id_scan_ocr = True
    save_settings(settings)

    created_temp_files: list[Path] = []
    real_mkstemp = tempfile.mkstemp

    def tracking_mkstemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | None = None,
        text: bool = False,
    ) -> tuple[int, str]:
        fd, name = real_mkstemp(suffix=suffix, prefix=prefix, dir=dir, text=text)
        if "kopi-id-composed-" in name or "kopi-id-ocr-" in name:
            created_temp_files.append(Path(name))
        return fd, name

    def exploding_ocr(_in_pdf: Path, _out_pdf: Path) -> tuple[bool, str | None]:
        raise RuntimeError("Simulated unexpected OCR crash")

    monkeypatch.setattr(tempfile, "mkstemp", tracking_mkstemp)
    monkeypatch.setattr(id_scan_mod, "apply_ocrmypdf", exploding_ocr)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        front_res = await client.post("/api/id-scan/front")
        sid = front_res.json()["session_id"]
        await client.post("/api/id-scan/back", json={"session_id": sid})

        with pytest.raises(RuntimeError, match="Simulated unexpected OCR crash"):
            await client.post("/api/id-scan/compose", json={"session_id": sid})

        assert len(created_temp_files) == 2
        for p in created_temp_files:
            assert not p.exists(), f"Leaked temp file: {p}"

        await client.post("/api/id-scan/discard", json={"session_id": sid})
