"""Typed configuration management and atomic JSON persistence for Kopi."""

from __future__ import annotations

import contextlib
import hmac
import json
import logging
import os
import secrets
import sys
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger("kopi.config")

DEFAULT_SETTINGS_REL_PATH = Path("config") / "settings.json"
LEGACY_DEFAULT_ADMIN_PASSWORD = "1234"
LEGACY_DEFAULT_PAIRING_PIN = "0000"
ADMIN_PASSWORD_DIGITS = 8
PAIRING_PIN_DIGITS = 6

_SETTINGS_THREAD_LOCK = threading.Lock()
_warned_legacy_defaults: set[str] = set()


class SettingsError(RuntimeError):
    """Raised when settings.json or an external secret file is corrupt or unreadable."""


def reset_legacy_default_warnings() -> None:
    """Clear the per-process legacy-default warning deduplication state (for tests)."""
    _warned_legacy_defaults.clear()


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
    """Resolve an external secret from `<NAME>_FILE` or `<NAME>`, or None if unset.

    If `<NAME>_FILE` is set to a non-empty path, fails closed with `SettingsError`
    when the target file is missing, unreadable, or empty/whitespace-only.
    """
    file_path_raw = os.environ.get(file_env, "").strip()
    if file_path_raw:
        secret_path = Path(file_path_raw)
        try:
            raw_content = secret_path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise SettingsError(
                f"Secret file configured in {file_env} is missing ({secret_path})."
            ) from exc
        except OSError as exc:
            raise SettingsError(
                f"Secret file configured in {file_env} is unreadable ({exc.__class__.__name__})."
            ) from exc
        content = raw_content.strip()
        if not content:
            raise SettingsError(
                f"Secret file configured in {file_env} is empty."
            )
        return content

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


@contextlib.contextmanager
def _settings_lock(target: Path) -> Iterator[None]:
    """Serialize settings generation and read-merge-write across threads and processes."""
    with _SETTINGS_THREAD_LOCK:
        if fcntl is None:  # pragma: no cover
            yield
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            lock_path = target.with_name(f"{target.name}.lock")
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        except OSError as exc:
            raise SettingsError(
                f"Could not acquire lock for settings file {target} ({exc.__class__.__name__})."
            ) from exc
        try:
            with contextlib.suppress(OSError):
                os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                with contextlib.suppress(OSError):
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _settings_file_error(target: Path, reason: str) -> SettingsError:
    return SettingsError(
        f"Settings file {target} is invalid or unreadable ({reason}). "
        "The file was NOT modified; restore it from backup or remove it deliberately to start fresh."
    )


def _read_and_validate_settings(target: Path) -> tuple[dict[str, Any], KopiSettings]:
    """Read and validate `target`, returning `({}, KopiSettings())` only when the file does not exist."""
    try:
        raw_text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, KopiSettings()
    except OSError as exc:
        raise _settings_file_error(target, f"unreadable: {exc.__class__.__name__}") from exc

    try:
        raw_data = json.loads(raw_text)
    except ValueError as exc:
        raise _settings_file_error(target, "invalid JSON") from exc

    if not isinstance(raw_data, dict):
        raise _settings_file_error(
            target, f"expected a JSON object, got {type(raw_data).__name__}"
        )

    try:
        stored = KopiSettings.model_validate(raw_data)
    except ValidationError as exc:
        raise _settings_file_error(target, "schema validation failed") from exc

    return raw_data, stored


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


def _warn_if_legacy_default(field_name: str, value: str, expected_legacy: str, target: Path) -> None:
    if value == expected_legacy and field_name not in _warned_legacy_defaults:
        _warned_legacy_defaults.add(field_name)
        log.warning(
            "Stored %s in %s matches the legacy default (%r); please rotate it.",
            field_name,
            target,
            expected_legacy,
        )


def load_settings(path: Path | None = None) -> KopiSettings:
    """Load settings from disk, applying external overrides or generating first-run secrets."""
    target = path if path is not None else get_settings_path()
    ext_admin_pw = _read_secret_from_env("KOPI_ADMIN_PASSWORD", "KOPI_ADMIN_PASSWORD_FILE")
    ext_pairing_pin = _read_secret_from_env("KOPI_PAIRING_PIN", "KOPI_PAIRING_PIN_FILE")

    _, stored = _read_and_validate_settings(target)
    need_admin = ext_admin_pw is None and not stored.admin_password.strip()
    need_pin = ext_pairing_pin is None and not stored.pairing_pin.strip()

    if need_admin or need_pin:
        with _settings_lock(target):
            _, stored = _read_and_validate_settings(target)
            generated: list[tuple[str, str]] = []

            if ext_admin_pw is None and not stored.admin_password.strip():
                stored.admin_password = _generate_digits(ADMIN_PASSWORD_DIGITS)
                generated.append(("Admin PIN", stored.admin_password))

            if ext_pairing_pin is None and not stored.pairing_pin.strip():
                stored.pairing_pin = _generate_digits(PAIRING_PIN_DIGITS)
                generated.append(("Pairing PIN", stored.pairing_pin))

            if generated:
                _write_settings_dict_atomic(stored.model_dump(mode="json"), target)
                log.info(
                    "Generated initial station credentials in %s (run 'kopi status --show-secrets' on the station).",
                    target,
                )
                if sys.stdout.isatty():
                    print(f"Kopi first-run credentials generated (saved to {target}):")
                    for label, secret_val in generated:
                        print(f"  {label}: {secret_val}")

    stored_admin_pw = stored.admin_password.strip()
    stored_pairing_pin = stored.pairing_pin.strip()

    if ext_admin_pw is not None:
        effective_admin_pw = ext_admin_pw
    else:
        effective_admin_pw = stored_admin_pw
        _warn_if_legacy_default(
            "admin_password", effective_admin_pw, LEGACY_DEFAULT_ADMIN_PASSWORD, target
        )

    if ext_pairing_pin is not None:
        effective_pairing_pin = ext_pairing_pin
    else:
        effective_pairing_pin = stored_pairing_pin
        _warn_if_legacy_default(
            "pairing_pin", effective_pairing_pin, LEGACY_DEFAULT_PAIRING_PIN, target
        )

    return stored.model_copy(
        update={
            "admin_password": effective_admin_pw,
            "pairing_pin": effective_pairing_pin,
        }
    )


def save_settings(settings: KopiSettings, path: Path | None = None) -> None:
    """Atomically persist settings to disk (mode 0600), never writing external secret overrides."""
    target = path if path is not None else get_settings_path()
    admin_managed = is_admin_password_managed()
    pin_managed = is_pairing_pin_managed()

    with _settings_lock(target):
        existing_raw, _ = _read_and_validate_settings(target)
        data = settings.model_dump(mode="json")

        if admin_managed:
            disk_pw = existing_raw.get("admin_password", "")
            data["admin_password"] = disk_pw if isinstance(disk_pw, str) else ""
        if pin_managed:
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

