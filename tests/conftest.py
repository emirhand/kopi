"""Shared pytest fixtures for Kopi test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from kopi.auth.rate_limit import reset_auth_rate_limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    """Ensure rate-limiter state is clean before each test."""
    reset_auth_rate_limiter()


@pytest.fixture
def temp_settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated temporary settings.json path and set SETTINGS_PATH."""
    cfg_path = tmp_path / "config" / "settings.json"
    monkeypatch.setenv("SETTINGS_PATH", str(cfg_path))
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "0")
    return cfg_path
