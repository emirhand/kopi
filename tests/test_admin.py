"""Unit and integration tests for Admin settings endpoints (TDD)."""

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
    reset_bridges()
    return create_app()


@pytest.mark.asyncio
async def test_admin_verify_and_settings_crud(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Verify default password ("1234")
        res_ok = await client.post("/api/admin/verify", json={"password": "1234"})
        assert res_ok.status_code == 200
        assert res_ok.json() == {"valid": True}

        res_bad = await client.post("/api/admin/verify", json={"password": "wrong"})
        assert res_bad.status_code == 200
        assert res_bad.json() == {"valid": False}

        # Missing header -> 401
        res_unauth = await client.get("/api/admin/settings")
        assert res_unauth.status_code == 401

        # Wrong header -> 403
        res_forbidden = await client.get(
            "/api/admin/settings", headers={"X-Admin-Password": "wrong"}
        )
        assert res_forbidden.status_code == 403

        # Valid header -> 200 with settings + hardware_options
        res_get = await client.get(
            "/api/admin/settings", headers={"X-Admin-Password": "1234"}
        )
        assert res_get.status_code == 200
        data = res_get.json()
        assert "hardware_options" in data
        assert "scanners" in data["hardware_options"]
        assert "printers" in data["hardware_options"]

        # Update scanner and printer device
        update_payload = {
            "smtp": {
                "host": "smtp.office.local",
                "port": 587,
                "user": "kopi",
                "password": "secret",
                "from_email": "kopi@office.local",
                "tls": True,
            },
            "scanner_device": "hpaio:/usb/HP_OfficeJet_Pro_9010_series?serial=TH0B2762P5",
            "printer_device": "HP_OfficeJet_Pro_9010",
            "usb_roots": ["/run/media"],
            "id_scan_ocr": True,
        }
        res_put = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "1234"},
            json=update_payload,
        )
        assert res_put.status_code == 200
        assert res_put.json()["ok"] is True

        # Confirm persisted values
        res_get2 = await client.get(
            "/api/admin/settings", headers={"X-Admin-Password": "1234"}
        )
        updated = res_get2.json()
        assert (
            updated["scanner_device"]
            == "hpaio:/usb/HP_OfficeJet_Pro_9010_series?serial=TH0B2762P5"
        )
        assert updated["printer_device"] == "HP_OfficeJet_Pro_9010"
        assert updated["id_scan_ocr"] is True
