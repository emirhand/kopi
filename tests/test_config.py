"""Unit tests for kopi.config (written first per TDD rules)."""

from __future__ import annotations

import json
import logging
import multiprocessing
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from kopi.config import (
    ADMIN_PASSWORD_DIGITS,
    PAIRING_PIN_DIGITS,
    KopiSettings,
    SettingsError,
    SmtpConfig,
    get_settings_path,
    is_admin_password_managed,
    is_pairing_pin_managed,
    load_settings,
    reset_legacy_default_warnings,
    save_settings,
    verify_admin_password,
    verify_pairing_pin,
)
from kopi.main import _app_lifespan, _cli_status, create_app


def _mp_load_worker(settings_path_str: str) -> tuple[str, str]:
    """Top-level worker for multiprocessing first-run generation test."""
    s = load_settings(Path(settings_path_str))
    return (s.admin_password, s.pairing_pin)


def test_get_settings_path_uses_env_override(temp_settings_path: Path) -> None:
    assert get_settings_path() == temp_settings_path


def test_load_settings_generates_and_persists_credentials_on_first_run(
    temp_settings_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert not temp_settings_path.exists()
    with caplog.at_level(logging.INFO, logger="kopi.config"):
        settings = load_settings()

    assert isinstance(settings, KopiSettings)
    assert len(settings.admin_password) == ADMIN_PASSWORD_DIGITS
    assert settings.admin_password.isdigit()
    assert settings.admin_password != "1234"
    assert len(settings.pairing_pin) == PAIRING_PIN_DIGITS
    assert settings.pairing_pin.isdigit()
    assert settings.pairing_pin != "0000"
    assert settings.paired_device_id is None
    assert settings.paired_device_token_hash is None
    assert settings.scanner_device == ""
    assert settings.printer_device == ""
    assert settings.id_scan_ocr is False
    assert settings.smtp == SmtpConfig()

    # Persisted to disk with mode 0600 (plus lock file mode 0600) and without secrets in logs
    assert temp_settings_path.is_file()
    assert stat.S_IMODE(temp_settings_path.stat().st_mode) == 0o600
    lock_file = temp_settings_path.with_name(f"{temp_settings_path.name}.lock")
    if lock_file.exists():
        assert stat.S_IMODE(lock_file.stat().st_mode) == 0o600
    assert any(
        "run 'kopi status --show-secrets' on the station" in rec.getMessage()
        for rec in caplog.records
    )
    for rec in caplog.records:
        assert settings.admin_password not in rec.getMessage()
        assert settings.pairing_pin not in rec.getMessage()

    # Idempotent across subsequent loads (does not rotate)
    second = load_settings()
    assert second.admin_password == settings.admin_password
    assert second.pairing_pin == settings.pairing_pin


def test_save_and_load_settings_roundtrip(temp_settings_path: Path) -> None:
    custom = KopiSettings(
        admin_password="secret-admin",
        pairing_pin="9876",
        paired_device_id="tablet-living-room",
        paired_device_token_hash="abc123hash",
        scanner_device="pixma:04A9176D",
        printer_device="Canon_LBP",
        id_scan_ocr=True,
        smtp=SmtpConfig(
            host="smtp.example.com",
            port=465,
            user="scanner@example.com",
            password="pw",
            from_email="scanner@example.com",
            tls=True,
        ),
    )
    save_settings(custom)
    assert temp_settings_path.is_file()
    assert stat.S_IMODE(temp_settings_path.stat().st_mode) == 0o600

    reloaded = load_settings()
    assert reloaded == custom


def test_load_settings_migrates_legacy_partial_json_and_empty_object(
    temp_settings_path: Path,
) -> None:
    """Empty `{}` or legacy settings.json without credentials generates missing ones and keeps other fields."""
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_settings_path.write_text("{}", encoding="utf-8")
    empty_obj_settings = load_settings()
    assert len(empty_obj_settings.admin_password) == ADMIN_PASSWORD_DIGITS
    assert len(empty_obj_settings.pairing_pin) == PAIRING_PIN_DIGITS

    legacy_payload = {
        "admin_password": "4321",
        "smtp": {
            "host": "mail.local",
            "port": 587,
            "user": "",
            "password": "",
            "from_email": "kopi@local",
            "tls": False,
        },
        "scanner_device": "airscan:e0:Canon",
    }
    temp_settings_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    settings = load_settings()
    assert settings.admin_password == "4321"
    assert settings.scanner_device == "airscan:e0:Canon"
    assert len(settings.pairing_pin) == PAIRING_PIN_DIGITS
    assert settings.pairing_pin.isdigit()
    assert settings.paired_device_token_hash is None
    assert settings.smtp.host == "mail.local"
    assert settings.smtp.tls is False


def test_legacy_default_credentials_log_warning_once_per_process(
    temp_settings_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_settings_path.write_text(
        json.dumps({"admin_password": "1234", "pairing_pin": "0000"}),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="kopi.config"):
        for _ in range(5):
            settings = load_settings()

    assert settings.admin_password == "1234"
    assert settings.pairing_pin == "0000"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    admin_warnings = [w for w in warnings if "admin_password" in w and "legacy default" in w]
    pin_warnings = [w for w in warnings if "pairing_pin" in w and "legacy default" in w]
    assert len(admin_warnings) == 1
    assert len(pin_warnings) == 1

    # Reset helper re-enables the warning for subsequent tests
    caplog.clear()
    reset_legacy_default_warnings()
    with caplog.at_level(logging.WARNING, logger="kopi.config"):
        load_settings()
    warnings_after_reset = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings_after_reset) == 2


def test_corrupt_or_invalid_settings_file_raises_and_is_never_overwritten(
    temp_settings_path: Path,
) -> None:
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Truncated JSON containing a paired device
    truncated_bytes = b'{"paired_device_id": "tablet-1", "smtp": {"host": "mail.internal"'
    temp_settings_path.write_bytes(truncated_bytes)
    with pytest.raises(SettingsError) as exc_info:
        load_settings()
    msg = str(exc_info.value)
    assert str(temp_settings_path) in msg
    assert "NOT modified" in msg
    assert "tablet-1" not in msg
    assert temp_settings_path.read_bytes() == truncated_bytes

    # save_settings also refuses to overwrite a corrupt file
    with pytest.raises(SettingsError):
        save_settings(KopiSettings(admin_password="87654321", pairing_pin="123456"))
    assert temp_settings_path.read_bytes() == truncated_bytes

    # 2. JSON array instead of object
    list_bytes = b'["not", "an", "object"]'
    temp_settings_path.write_bytes(list_bytes)
    with pytest.raises(SettingsError) as exc_info2:
        load_settings()
    assert "NOT modified" in str(exc_info2.value)
    assert temp_settings_path.read_bytes() == list_bytes

    # 3. JSON object with invalid schema field type
    bad_schema_bytes = b'{"smtp": {"port": "not-a-port-number"}}'
    temp_settings_path.write_bytes(bad_schema_bytes)
    with pytest.raises(SettingsError) as exc_info3:
        load_settings()
    assert "NOT modified" in str(exc_info3.value)
    assert "not-a-port-number" not in str(exc_info3.value)
    assert temp_settings_path.read_bytes() == bad_schema_bytes


@pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root bypasses 0000 file permissions",
)
def test_unreadable_settings_file_raises_and_is_unchanged(
    temp_settings_path: Path,
) -> None:
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    original_bytes = b'{"admin_password": "87654321", "pairing_pin": "123456"}'
    temp_settings_path.write_bytes(original_bytes)
    os.chmod(temp_settings_path, 0o000)
    try:
        with pytest.raises(SettingsError) as exc_info:
            load_settings()
        assert str(temp_settings_path) in str(exc_info.value)
        assert "NOT modified" in str(exc_info.value)
    finally:
        os.chmod(temp_settings_path, 0o600)
    assert temp_settings_path.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_corrupt_settings_http_503_and_cli_exit_1(
    temp_settings_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    corrupt_bytes = b'{"paired_device_id": "kiosk-tablet", broken'
    temp_settings_path.write_bytes(corrupt_bytes)

    app = create_app()

    # Startup lifespan fails fast with SettingsError
    with pytest.raises(SettingsError):
        async with _app_lifespan(app):
            pass

    # Runtime endpoint returns 503 without leaking path and without modifying file
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/admin/verify", json={"password": "12345678"})
        assert res.status_code == 503
        assert res.json() == {"detail": "Station settings are unavailable. Check the server logs."}
        assert str(temp_settings_path) not in res.text

    assert temp_settings_path.read_bytes() == corrupt_bytes

    # CLI status exits 1 and prints error to stderr
    with pytest.raises(SystemExit) as exit_info:
        _cli_status()
    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(temp_settings_path) in captured.err
    assert "NOT modified" in captured.err
    assert temp_settings_path.read_bytes() == corrupt_bytes


def test_env_and_file_override_precedence_and_fail_closed_file_errors(
    temp_settings_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed stored credentials on disk
    save_settings(KopiSettings(admin_password="stored-admin-8888", pairing_pin="111111"))

    # Env override takes precedence over stored settings.json
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD", "env-admin-9999")
    monkeypatch.setenv("KOPI_PAIRING_PIN", "222222")
    assert is_admin_password_managed() is True
    assert is_pairing_pin_managed() is True

    s_env = load_settings()
    assert s_env.admin_password == "env-admin-9999"
    assert s_env.pairing_pin == "222222"

    # *_FILE takes precedence over direct env var (and strips trailing newline/whitespace)
    pw_file = tmp_path / "admin_pw.secret"
    pin_file = tmp_path / "pairing_pin.secret"
    pw_file.write_text("file-admin-7777\n", encoding="utf-8")
    pin_file.write_text("  333333 \r\n", encoding="utf-8")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", str(pw_file))
    monkeypatch.setenv("KOPI_PAIRING_PIN_FILE", str(pin_file))

    s_file = load_settings()
    assert s_file.admin_password == "file-admin-7777"
    assert s_file.pairing_pin == "333333"

    # Saving settings while overrides are active must NOT write overridden secrets to disk
    s_file.scanner_device = "test:scanner"
    save_settings(s_file)
    raw_on_disk = json.loads(temp_settings_path.read_text(encoding="utf-8"))
    assert raw_on_disk["admin_password"] == "stored-admin-8888"
    assert raw_on_disk["pairing_pin"] == "111111"
    assert raw_on_disk["scanner_device"] == "test:scanner"

    # Broken *_FILE must fail closed (raise SettingsError, never fall through to env/stored)
    # 1. Missing file
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", str(tmp_path / "missing.secret"))
    with pytest.raises(SettingsError, match=r"KOPI_ADMIN_PASSWORD_FILE.*missing"):
        load_settings()
    with pytest.raises(SettingsError, match=r"KOPI_ADMIN_PASSWORD_FILE.*missing"):
        is_admin_password_managed()

    # 2. Directory instead of file
    dir_path = tmp_path / "secret_dir"
    dir_path.mkdir()
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", str(dir_path))
    with pytest.raises(SettingsError, match=r"KOPI_ADMIN_PASSWORD_FILE.*unreadable"):
        load_settings()

    # 3. Empty file
    empty_file = tmp_path / "empty.secret"
    empty_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", str(empty_file))
    with pytest.raises(SettingsError, match=r"KOPI_ADMIN_PASSWORD_FILE.*empty"):
        load_settings()

    # 4. Whitespace-only file
    ws_file = tmp_path / "whitespace.secret"
    ws_file.write_text("   \t\r\n", encoding="utf-8")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", "  ")
    monkeypatch.setenv("KOPI_PAIRING_PIN_FILE", str(ws_file))
    with pytest.raises(SettingsError, match=r"KOPI_PAIRING_PIN_FILE.*empty"):
        load_settings()
    with pytest.raises(SettingsError, match=r"KOPI_PAIRING_PIN_FILE.*empty"):
        is_pairing_pin_managed()

    # Unset/blank *_FILE and whitespace-only env vars fall back to stored settings.json
    monkeypatch.setenv("KOPI_PAIRING_PIN_FILE", "   ")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD", "   ")
    monkeypatch.setenv("KOPI_PAIRING_PIN", "")
    assert is_admin_password_managed() is False
    assert is_pairing_pin_managed() is False

    s_stored = load_settings()
    assert s_stored.admin_password == "stored-admin-8888"
    assert s_stored.pairing_pin == "111111"


def test_first_run_generation_is_race_free_across_threads(
    temp_settings_path: Path,
) -> None:
    assert not temp_settings_path.exists()
    barrier = threading.Barrier(8)

    def worker() -> tuple[str, str]:
        barrier.wait()
        s = load_settings(temp_settings_path)
        return (s.admin_password, s.pairing_pin)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: worker(), range(8)))

    on_disk = load_settings(temp_settings_path)
    expected = (on_disk.admin_password, on_disk.pairing_pin)
    assert len(set(results)) == 1
    assert results[0] == expected


def test_first_run_generation_is_race_free_across_processes(
    temp_settings_path: Path,
) -> None:
    assert not temp_settings_path.exists()
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(processes=4) as pool:
        results = pool.map(_mp_load_worker, [str(temp_settings_path)] * 4)

    on_disk = load_settings(temp_settings_path)
    expected = (on_disk.admin_password, on_disk.pairing_pin)
    assert len(set(results)) == 1
    assert results[0] == expected


def test_create_app_has_no_settings_dir_or_path_log_side_effects_until_lifespan(
    temp_settings_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert not temp_settings_path.parent.exists()
    with caplog.at_level(logging.INFO, logger="kopi.main"):
        _ = create_app()
    assert not temp_settings_path.parent.exists()
    assert not any("kopi_paths" in r.getMessage() for r in caplog.records)


def test_verify_admin_password_and_pairing_pin() -> None:
    settings = KopiSettings(admin_password="correct-pin", pairing_pin="654321")
    assert verify_admin_password(settings, "correct-pin") is True
    assert verify_admin_password(settings, "wrong-pin") is False
    assert verify_admin_password(settings, "") is False
    assert verify_pairing_pin(settings, "654321") is True
    assert verify_pairing_pin(settings, "000000") is False
    assert verify_pairing_pin(settings, "") is False

    empty_settings = KopiSettings()
    assert verify_admin_password(empty_settings, "") is False
    assert verify_pairing_pin(empty_settings, "") is False
