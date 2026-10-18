"""TDD tests for Phase 5: Client Pairing, Exclusive Access Control, and Tablet Failure Recovery."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kopi.config import load_settings, save_settings
from kopi.hardware import reset_bridges
from kopi.main import create_app


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "1")
    reset_bridges()
    return create_app()


@pytest.mark.asyncio
async def test_unpaired_station_rejects_operational_endpoints_until_paired(
    app: FastAPI,
) -> None:
    """When unpaired, operational endpoints return 403 Pairing Required."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Check initial pairing status
        st = await client.get("/api/pair/status")
        assert st.status_code == 200
        st_data = st.json()
        assert st_data["paired"] is False
        assert st_data["require_pairing"] is True
        assert st_data["caller_is_paired"] is False

        # 2. Operational endpoints must be blocked (403) when unpaired
        copy_res = await client.post("/api/copy", json={"copies": 1})
        assert copy_res.status_code == 403

        scan_res = await client.post("/api/scan", json={"source": "flatbed"})
        assert scan_res.status_code == 403

        # 3. Health and public settings remain accessible
        health_res = await client.get("/api/health")
        assert health_res.status_code == 200


@pytest.mark.asyncio
async def test_pairing_lifecycle_exclusive_lock_and_tablet_replacement(
    app: FastAPI,
) -> None:
    """Test claiming with PIN, rejecting second tablet (409), exclusive access, and Admin PIN replacement."""
    settings = load_settings()
    settings.pairing_pin = "2468"
    settings.admin_password = "9999"
    save_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Wrong PIN is rejected with 403
        bad_claim = await client.post(
            "/api/pair/claim",
            json={"pin": "0000", "device_label": "Intruder"},
        )
        assert bad_claim.status_code == 403

        # 2. Valid PIN pairs Tablet A and issues token + cookie
        claim_a = await client.post(
            "/api/pair/claim",
            json={"pin": "2468", "device_label": "Front Desk iPad"},
        )
        assert claim_a.status_code == 200
        data_a = claim_a.json()
        assert data_a["ok"] is True
        token_a = data_a["token"]
        assert len(token_a) >= 24
        assert data_a["device_label"] == "Front Desk iPad"

        # 3. Tablet A is recognized as the paired client
        st_a = await client.get(
            "/api/pair/status",
            headers={"X-Kopi-Device-Token": token_a},
        )
        assert st_a.status_code == 200
        assert st_a.json()["paired"] is True
        assert st_a.json()["caller_is_paired"] is True
        assert st_a.json()["device_label"] == "Front Desk iPad"

        # 4. Tablet A can now execute operational endpoints (/api/copy)
        copy_ok = await client.post(
            "/api/copy",
            json={"copies": 1},
            headers={"X-Kopi-Device-Token": token_a},
        )
        assert copy_ok.status_code == 200
        assert copy_ok.json()["ok"] is True

    # Use a fresh client (simulating Tablet B on the network with no cookies)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client_b:
        # 5. Tablet B sees paired=True, caller_is_paired=False
        st_b = await client_b.get("/api/pair/status")
        assert st_b.status_code == 200
        assert st_b.json()["paired"] is True
        assert st_b.json()["caller_is_paired"] is False

        # 6. Tablet B cannot claim while Tablet A is paired (409 Conflict)
        claim_b = await client_b.post(
            "/api/pair/claim",
            json={"pin": "2468", "device_label": "Second Tablet"},
        )
        assert claim_b.status_code == 409

        # 7. Tablet B cannot run operational endpoints (403 Forbidden)
        copy_b = await client_b.post("/api/copy", json={"copies": 1})
        assert copy_b.status_code == 403

        # 8. Suppose Tablet A (iPad) died! Tablet B uses Admin PIN Override (/api/pair/replace)
        bad_replace = await client_b.post(
            "/api/pair/replace",
            json={"admin_password": "wrong", "device_label": "Replacement Galaxy Tab"},
        )
        assert bad_replace.status_code == 403

        replace_b = await client_b.post(
            "/api/pair/replace",
            json={"admin_password": "9999", "device_label": "Replacement Galaxy Tab"},
        )
        assert replace_b.status_code == 200
        token_b = replace_b.json()["token"]
        assert token_b != token_a

        # 9. Old Tablet A token is immediately revoked (403)
        old_copy = await client_b.post(
            "/api/copy",
            json={"copies": 1},
            headers={"X-Kopi-Device-Token": token_a},
        )
        assert old_copy.status_code == 403

        # 10. New Tablet B token works!
        new_copy = await client_b.post(
            "/api/copy",
            json={"copies": 1},
            headers={"X-Kopi-Device-Token": token_b},
        )
        assert new_copy.status_code == 200

        # 11. Admin can also unpair completely via /api/admin/unpair
        unpair_res = await client_b.post(
            "/api/admin/unpair",
            headers={"X-Admin-Password": "9999"},
        )
        assert unpair_res.status_code == 200
        assert unpair_res.json()["ok"] is True

        st_after = await client_b.get("/api/pair/status")
        assert st_after.json()["paired"] is False
