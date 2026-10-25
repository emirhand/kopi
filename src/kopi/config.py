"""Typed configuration management and atomic JSON persistence for Kopi."""

from __future__ import annotations

import hmac
import json
import logging
import os
import secrets
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger("kopi.config")

DEFAULT_SETTINGS_REL_PATH = Path("config") / "settings.json"
LEGACY_DEFAULT_ADMIN_PASSWORD = "1234"
LEGACY_DEFAULT_PAIRING_PIN = "0000"
ADMIN_PASSWORD_DIGITS = 8
PAIRING_PIN_DIGITS = 6


class SmtpConfig(BaseModel):
    """Outbound SMTP configuration for scan-to-email workflows."""

    host: str = ""
    port: int = Field(default=587, ge=1, le=65535)
    user: str = ""
    password: str = ""
    from_email: str = ""
    tls: bool = True


class CopyDefaultsConfig(BaseModel):
    """Persistent default settings for the Copy workflow (HP OfficeJet Pro 9010 style)."""

    sided_mode: str = "1_to_1"
    color: bool = True
    source: str = "flatbed"
    quality: str = "normal"
    lighter_darker: int = Field(default=0, ge=-4, le=4)
    resize_mode: str = "actual"
    resize_percent: int = Field(default=100, ge=25, le=400)
    original_size: str = "A4"
    paper_size: str = "A4"
    page_flip: str = "long_edge"
    collate: bool = True
    content_type: str = "mixed"


class KopiSettings(BaseModel):
    """Persistent appliance settings."""

    admin_password: str = ""
    pairing_pin: str = ""
    paired_device_id: str | None = None
    paired_device_label: str | None = None
    paired_at: str | None = None
    paired_device_token_hash: str | None = None
    scanner_device: str = ""
    printer_device: str = ""
    id_scan_ocr: bool = False
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    copy_defaults: CopyDefaultsConfig = Field(default_factory=CopyDefaultsConfig)


def _generate_digits(length: int) -> str:
    """Generate a random numeric string suitable for the kiosk keypad."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def _read_secret_from_env(val_env: str, file_env: str) -> str | None:
    """Resolve an external secret from `<NAME>_FILE` or `<NAME>`, or None if unset."""
    file_path_raw = os.environ.get(file_env, "").strip()
    if file_path_raw:
        try:
            content = Path(file_path_raw).read_text(encoding="utf-8").strip()
            if content:
                return content
            log.warning("%s points to an empty file; falling through.", file_env)
        except OSError as exc:
            log.warning(
                "Failed to read secret file specified by %s (%s); falling through.",
                file_env,
                exc.__class__.__name__,
            )

    direct_val = os.environ.get(val_env, "").strip()
    if direct_val:
        return direct_val
    return None


def is_admin_password_managed() -> bool:
    """Return True if the admin password is supplied via environment or secret file."""
    return _read_secret_from_env("KOPI_ADMIN_PASSWORD", "KOPI_ADMIN_PASSWORD_FILE") is not None


def is_pairing_pin_managed() -> bool:
    """Return True if the pairing PIN is supplied via environment or secret file."""
    return _read_secret_from_env("KOPI_PAIRING_PIN", "KOPI_PAIRING_PIN_FILE") is not None


def get_settings_path() -> Path:
    """Resolve the active settings.json path from SETTINGS_PATH or default."""
    env_override = os.environ.get("SETTINGS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / DEFAULT_SETTINGS_REL_PATH


def _read_raw_settings_dict(target: Path) -> dict[str, Any]:
    if not target.is_file():
        return {}
    try:
        with target.open("r", encoding="utf-8") as f:
            raw_data = json.load(f)
        return raw_data if isinstance(raw_data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_settings_dict_atomic(data: dict[str, Any], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)

    fd, tmp_name = tempfile.mkstemp(
        prefix=".settings-",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def load_settings(path: Path | None = None) -> KopiSettings:
    """Load settings from disk, applying external overrides or generating first-run secrets."""
    target = path if path is not None else get_settings_path()
    raw_data = _read_raw_settings_dict(target)
    stored = KopiSettings.model_validate(raw_data) if raw_data else KopiSettings()

    stored_admin_pw = stored.admin_password.strip()
    stored_pairing_pin = stored.pairing_pin.strip()

    ext_admin_pw = _read_secret_from_env("KOPI_ADMIN_PASSWORD", "KOPI_ADMIN_PASSWORD_FILE")
    ext_pairing_pin = _read_secret_from_env("KOPI_PAIRING_PIN", "KOPI_PAIRING_PIN_FILE")

    generated: list[tuple[str, str]] = []

    if ext_admin_pw is not None:
        effective_admin_pw = ext_admin_pw
    elif stored_admin_pw:
        effective_admin_pw = stored_admin_pw
        if stored_admin_pw == LEGACY_DEFAULT_ADMIN_PASSWORD:
            log.warning(
                "Stored admin_password in %s matches the legacy default ('1234'); please rotate it.",
                target,
            )
    else:
        effective_admin_pw = _generate_digits(ADMIN_PASSWORD_DIGITS)
        stored.admin_password = effective_admin_pw
        generated.append(("Admin PIN", effective_admin_pw))

    if ext_pairing_pin is not None:
        effective_pairing_pin = ext_pairing_pin
    elif stored_pairing_pin:
        effective_pairing_pin = stored_pairing_pin
        if stored_pairing_pin == LEGACY_DEFAULT_PAIRING_PIN:
            log.warning(
                "Stored pairing_pin in %s matches the legacy default ('0000'); please rotate it.",
                target,
            )
    else:
        effective_pairing_pin = _generate_digits(PAIRING_PIN_DIGITS)
        stored.pairing_pin = effective_pairing_pin
        generated.append(("Pairing PIN", effective_pairing_pin))

    if generated:
        _write_settings_dict_atomic(stored.model_dump(mode="json"), target)
        log.info(
            "Generated initial station credentials in %s (run 'uv run kopi status --show-secrets' to view).",
            target,
        )
        if sys.stdout.isatty():
            print(f"Kopi first-run credentials generated (saved to {target}):")
            for label, secret_val in generated:
                print(f"  {label}: {secret_val}")

    return stored.model_copy(
        update={
            "admin_password": effective_admin_pw,
            "pairing_pin": effective_pairing_pin,
        }
    )


def save_settings(settings: KopiSettings, path: Path | None = None) -> None:
    """Atomically persist settings to disk (mode 0600), never writing external secret overrides."""
    target = path if path is not None else get_settings_path()
    existing_raw = _read_raw_settings_dict(target)
    data = settings.model_dump(mode="json")

    if is_admin_password_managed():
        disk_pw = existing_raw.get("admin_password", "")
        data["admin_password"] = disk_pw if isinstance(disk_pw, str) else ""
    if is_pairing_pin_managed():
        disk_pin = existing_raw.get("pairing_pin", "")
        data["pairing_pin"] = disk_pin if isinstance(disk_pin, str) else ""

    _write_settings_dict_atomic(data, target)


def verify_admin_password(settings: KopiSettings, password: str) -> bool:
    """Constant-time verification of the administrator password/PIN."""
    expected = settings.admin_password.encode("utf-8")
    provided = (password or "").encode("utf-8")
    if not provided or not expected:
        return False
    return hmac.compare_digest(expected, provided)


def verify_pairing_pin(settings: KopiSettings, pin: str) -> bool:
    """Constant-time verification of the client pairing PIN."""
    expected = settings.pairing_pin.encode("utf-8")
    provided = (pin or "").encode("utf-8")
    if not provided or not expected:
        return False
    return hmac.compare_digest(expected, provided)

