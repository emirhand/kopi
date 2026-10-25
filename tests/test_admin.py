"""Unit and integration tests for Admin settings endpoints (TDD)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kopi.config import KopiSettings, load_settings, save_settings
from kopi.hardware import reset_bridges
from kopi.main import _cli_setup_sheet, _cli_status, create_app


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    save_settings(KopiSettings(admin_password="1234", pairing_pin="0000"), temp_settings_path)
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
        assert "password" not in data["smtp"]
        assert data["smtp"]["password_set"] is False
        assert "pairing_pin" not in data
        assert data["pairing_pin_set"] is True

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
            "id_scan_ocr": True,
        }
        res_put = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "1234"},
            json=update_payload,
        )
        assert res_put.status_code == 200
        assert res_put.json()["ok"] is True

        # Confirm persisted values and masked secrets
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
        assert "password" not in updated["smtp"]
        assert updated["smtp"]["password_set"] is True
        assert "pairing_pin" not in updated
        assert updated["pairing_pin_set"] is True

        # Confirm subsequent PUT with empty smtp.password preserves existing password
        update_without_pw: dict[str, object] = {
            **update_payload,
            "smtp": {
                "host": "smtp.office.local",
                "port": 587,
                "user": "kopi",
                "password": "",
                "from_email": "kopi@office.local",
                "tls": True,
            },
        }
        res_put2 = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "1234"},
            json=update_without_pw,
        )
        assert res_put2.status_code == 200
        from kopi.config import load_settings

        assert load_settings().smtp.password == "secret"


@pytest.mark.asyncio
async def test_admin_verify_rate_limit_and_lockout(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kopi.auth.rate_limit import get_auth_rate_limiter

    monkeypatch.setenv("KOPI_AUTH_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("KOPI_AUTH_LOCKOUT_SECONDS", "30")

    fake_now = [1000.0]
    limiter = get_auth_rate_limiter()
    monkeypatch.setattr(limiter, "clock", lambda: fake_now[0])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 3 failed attempts are allowed before lockout kicks in
        for _ in range(3):
            res = await client.post("/api/admin/verify", json={"password": "wrong"})
            assert res.status_code == 200
            assert res.json() == {"valid": False}

        # 4th attempt (even with valid password) is blocked with 429 during the 30s delay
        blocked = await client.post("/api/admin/verify", json={"password": "1234"})
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After") == "30"

        # /api/admin/settings and /api/pair/replace share the admin_password scope and are also locked
        blocked_settings = await client.get(
            "/api/admin/settings", headers={"X-Admin-Password": "1234"}
        )
        assert blocked_settings.status_code == 429

        blocked_replace = await client.post(
            "/api/pair/replace", json={"admin_password": "1234"}
        )
        assert blocked_replace.status_code == 429

        # Advance clock past the 30s delay; wrong attempt triggers doubled delay (60s)
        fake_now[0] += 31.0
        bad_again = await client.post("/api/admin/verify", json={"password": "wrong"})
        assert bad_again.status_code == 200
        assert bad_again.json() == {"valid": False}

        blocked_60 = await client.post("/api/admin/verify", json={"password": "1234"})
        assert blocked_60.status_code == 429
        assert blocked_60.headers.get("Retry-After") == "60"

        # Advance past 60s; valid password succeeds and resets the counter
        fake_now[0] += 61.0
        ok = await client.post("/api/admin/verify", json={"password": "1234"})
        assert ok.status_code == 200
        assert ok.json() == {"valid": True}

        # A subsequent wrong attempt does not immediately lock out (counter was reset)
        single_fail = await client.post("/api/admin/verify", json={"password": "wrong"})
        assert single_fail.status_code == 200
        assert single_fail.json() == {"valid": False}
        still_ok = await client.post("/api/admin/verify", json={"password": "1234"})
        assert still_ok.status_code == 200
        assert still_ok.json() == {"valid": True}


@pytest.mark.asyncio
async def test_cors_defaults_to_station_origin_not_wildcard(
    temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    fresh_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=fresh_app), base_url="http://test") as client:
        # Arbitrary external origin is not echoed back in Access-Control-Allow-Origin
        evil = await client.get(
            "/api/health", headers={"Origin": "https://evil.example.com"}
        )
        assert evil.status_code == 200
        assert "access-control-allow-origin" not in evil.headers

        # Station's own origin is allowed
        own = await client.get(
            "/api/health", headers={"Origin": "http://localhost:8000"}
        )
        assert own.status_code == 200
        assert own.headers.get("access-control-allow-origin") == "http://localhost:8000"


@pytest.mark.asyncio
async def test_admin_settings_managed_credentials_rejected_on_put(
    temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    save_settings(KopiSettings(admin_password="stored-admin", pairing_pin="stored-pin"), temp_settings_path)
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD", "managed-admin-12345678")
    monkeypatch.setenv("KOPI_PAIRING_PIN", "654321")
    reset_bridges()
    managed_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=managed_app), base_url="http://test") as client:
        res_get = await client.get(
            "/api/admin/settings",
            headers={"X-Admin-Password": "managed-admin-12345678"},
        )
        assert res_get.status_code == 200
        body = res_get.json()
        assert body["admin_password_managed"] is True
        assert body["pairing_pin_managed"] is True
        assert "admin_password" not in body
        assert "pairing_pin" not in body

        # Attempting to change a managed pairing PIN -> 400
        res_pin_change = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "managed-admin-12345678"},
            json={"pairing_pin": "999999"},
        )
        assert res_pin_change.status_code == 400

        # Attempting to change a managed admin password -> 400
        res_pw_change = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "managed-admin-12345678"},
            json={"new_admin_password": "different-admin-pw"},
        )
        assert res_pw_change.status_code == 400

        # Passing the same value or omitting managed fields succeeds without writing overrides to disk
        res_same = await client.put(
            "/api/admin/settings",
            headers={"X-Admin-Password": "managed-admin-12345678"},
            json={
                "pairing_pin": "654321",
                "new_admin_password": "managed-admin-12345678",
                "scanner_device": "mock:scanner",
            },
        )
        assert res_same.status_code == 200

    # Verify stored file still has original secrets when overrides are removed
    monkeypatch.delenv("KOPI_ADMIN_PASSWORD")
    monkeypatch.delenv("KOPI_PAIRING_PIN")
    reloaded = load_settings(temp_settings_path)
    assert reloaded.admin_password == "stored-admin"
    assert reloaded.pairing_pin == "stored-pin"


def test_cli_status_hides_secrets_by_default_and_shows_with_flag(
    temp_settings_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_settings(KopiSettings(admin_password="87654321", pairing_pin="135790"), temp_settings_path)
    _cli_status()
    out_default = capsys.readouterr().out
    assert "135790" not in out_default
    assert "87654321" not in out_default
    assert "--show-secrets" in out_default

    monkeypatch.setenv("KOPI_PAIRING_PIN", "246810")
    _cli_status(show_secrets=True)
    out_secrets = capsys.readouterr().out
    assert "246810 (managed externally)" in out_secrets
    assert "87654321" in out_secrets


@pytest.mark.asyncio
async def test_public_url_in_setup_sheet_and_cors(
    temp_settings_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    save_settings(KopiSettings(admin_password="87654321", pairing_pin="135790"), temp_settings_path)
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_PUBLIC_URL", "https://copier.example.org:8443/")

    _cli_setup_sheet()
    sheet_out = capsys.readouterr().out
    assert "Station URL : https://copier.example.org:8443" in sheet_out
    assert "Pairing PIN : 135790" in sheet_out

    public_app = create_app()
    async with AsyncClient(transport=ASGITransport(app=public_app), base_url="http://test") as client:
        res = await client.get(
            "/api/health", headers={"Origin": "https://copier.example.org:8443"}
        )
        assert res.status_code == 200
        assert (
            res.headers.get("access-control-allow-origin")
            == "https://copier.example.org:8443"
        )
