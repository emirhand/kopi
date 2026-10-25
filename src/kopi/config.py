"""Typed configuration management and atomic JSON persistence for Kopi."""

from __future__ import annotations

import hmac
import json
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_SETTINGS_REL_PATH = Path("config") / "settings.json"


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

    admin_password: str = "1234"
    pairing_pin: str = "0000"
    paired_device_id: str | None = None
    paired_device_label: str | None = None
    paired_at: str | None = None
    paired_device_token_hash: str | None = None
    scanner_device: str = ""
    printer_device: str = ""
    id_scan_ocr: bool = False
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    copy_defaults: CopyDefaultsConfig = Field(default_factory=CopyDefaultsConfig)


def get_settings_path() -> Path:
    """Resolve the active settings.json path from SETTINGS_PATH or default."""
    env_override = os.environ.get("SETTINGS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / DEFAULT_SETTINGS_REL_PATH


def load_settings(path: Path | None = None) -> KopiSettings:
    """Load settings from disk, falling back to safe defaults if not yet created."""
    target = path if path is not None else get_settings_path()
    if not target.is_file():
        return KopiSettings()
    with target.open("r", encoding="utf-8") as f:
        raw_data = json.load(f)
    if not isinstance(raw_data, dict):
        return KopiSettings()
    return KopiSettings.model_validate(raw_data)


def save_settings(settings: KopiSettings, path: Path | None = None) -> None:
    """Atomically persist settings to disk."""
    target = path if path is not None else get_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings.model_dump(mode="json"), indent=2)

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
        tmp_path.replace(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


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

