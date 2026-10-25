"""Unit tests for kopi.config (written first per TDD rules)."""

from __future__ import annotations

import json
import logging
import stat
from pathlib import Path

import pytest

from kopi.config import (
    ADMIN_PASSWORD_DIGITS,
    PAIRING_PIN_DIGITS,
    KopiSettings,
    SmtpConfig,
    get_settings_path,
    is_admin_password_managed,
    is_pairing_pin_managed,
    load_settings,
    save_settings,
    verify_admin_password,
    verify_pairing_pin,
)


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

    # Persisted to disk with mode 0600 and without secrets leaked in logs
    assert temp_settings_path.is_file()
    assert stat.S_IMODE(temp_settings_path.stat().st_mode) == 0o600
    assert any("Generated initial station credentials" in rec.message for rec in caplog.records)
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


def test_load_settings_migrates_legacy_partial_json(temp_settings_path: Path) -> None:
    """Legacy settings.json without pairing fields should generate a PIN and preserve existing fields."""
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
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


def test_legacy_default_credentials_log_warning_without_rotating(
    temp_settings_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    temp_settings_path.parent.mkdir(parents=True, exist_ok=True)
    temp_settings_path.write_text(
        json.dumps({"admin_password": "1234", "pairing_pin": "0000"}),
        encoding="utf-8",
    )
    with caplog.at_level(logging.WARNING, logger="kopi.config"):
        settings = load_settings()

    assert settings.admin_password == "1234"
    assert settings.pairing_pin == "0000"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("admin_password" in w and "legacy default" in w for w in warnings)
    assert any("pairing_pin" in w and "legacy default" in w for w in warnings)


def test_env_and_file_override_precedence_and_non_persistence(
    temp_settings_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
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

    # Missing or empty *_FILE logs a warning (without file contents) and falls through to env
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD_FILE", str(tmp_path / "missing.secret"))
    empty_file = tmp_path / "empty.secret"
    empty_file.write_text("   \n", encoding="utf-8")
    monkeypatch.setenv("KOPI_PAIRING_PIN_FILE", str(empty_file))

    with caplog.at_level(logging.WARNING, logger="kopi.config"):
        s_fallthrough = load_settings()
    assert s_fallthrough.admin_password == "env-admin-9999"
    assert s_fallthrough.pairing_pin == "222222"
    assert any("KOPI_ADMIN_PASSWORD_FILE" in r.getMessage() for r in caplog.records)
    assert any("KOPI_PAIRING_PIN_FILE" in r.getMessage() for r in caplog.records)

    # Whitespace-only env vars are ignored and fall back to stored settings.json
    monkeypatch.delenv("KOPI_ADMIN_PASSWORD_FILE")
    monkeypatch.delenv("KOPI_PAIRING_PIN_FILE")
    monkeypatch.setenv("KOPI_ADMIN_PASSWORD", "   ")
    monkeypatch.setenv("KOPI_PAIRING_PIN", "")
    assert is_admin_password_managed() is False
    assert is_pairing_pin_managed() is False

    s_stored = load_settings()
    assert s_stored.admin_password == "stored-admin-8888"
    assert s_stored.pairing_pin == "111111"


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
