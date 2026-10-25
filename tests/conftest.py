"""Shared pytest fixtures for Kopi test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from kopi.auth.rate_limit import reset_auth_rate_limiter
from kopi.config import reset_legacy_default_warnings


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Ensure rate-limiter and warning deduplication state are clean before each test."""
    reset_auth_rate_limiter()
    reset_legacy_default_warnings()


@pytest.fixture
def temp_settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated temporary settings.json path and set SETTINGS_PATH."""
    cfg_path = tmp_path / "config" / "settings.json"
    monkeypatch.setenv("SETTINGS_PATH", str(cfg_path))
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "0")
    for var in (
        "KOPI_ADMIN_PASSWORD",
        "KOPI_ADMIN_PASSWORD_FILE",
        "KOPI_PAIRING_PIN",
        "KOPI_PAIRING_PIN_FILE",
        "KOPI_PUBLIC_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    return cfg_path
