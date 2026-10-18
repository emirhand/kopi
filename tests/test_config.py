"""Unit tests for kopi.config (written first per TDD rules)."""

from __future__ import annotations

import json
from pathlib import Path

from kopi.config import (
    KopiSettings,
    SmtpConfig,
    get_settings_path,
    load_settings,
    save_settings,
    verify_admin_password,
)


def test_get_settings_path_uses_env_override(temp_settings_path: Path) -> None:
    assert get_settings_path() == temp_settings_path


def test_load_settings_returns_defaults_when_file_missing(temp_settings_path: Path) -> None:
    assert not temp_settings_path.exists()
    settings = load_settings()
    assert isinstance(settings, KopiSettings)
    assert settings.admin_password == "1234"
    assert settings.pairing_pin == "0000"
    assert settings.paired_device_id is None
    assert settings.paired_device_token_hash is None
    assert settings.scanner_device == ""
    assert settings.printer_device == ""
    assert settings.id_scan_ocr is False
    assert settings.smtp == SmtpConfig()


def test_save_and_load_settings_roundtrip(temp_settings_path: Path) -> None:
    custom = KopiSettings(
        admin_password="secret-admin",
        pairing_pin="9876",
        paired_device_id="tablet-living-room",
        paired_device_token_hash="abc123hash",
        scanner_device="pixma:04A9176D",
        printer_device="Canon_LBP",
        usb_roots=["/media/usb0"],
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

    reloaded = load_settings()
    assert reloaded == custom


def test_load_settings_migrates_legacy_partial_json(temp_settings_path: Path) -> None:
    """Legacy settings.json without pairing fields should load cleanly with defaults."""
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
    assert settings.pairing_pin == "0000"
    assert settings.paired_device_token_hash is None
    assert settings.smtp.host == "mail.local"
    assert settings.smtp.tls is False


def test_verify_admin_password() -> None:
    settings = KopiSettings(admin_password="correct-pin")
    assert verify_admin_password(settings, "correct-pin") is True
    assert verify_admin_password(settings, "wrong-pin") is False
    assert verify_admin_password(settings, "") is False
