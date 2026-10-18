"""Shared pytest fixtures for Kopi test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_settings_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide an isolated temporary settings.json path and set SETTINGS_PATH."""
    cfg_path = tmp_path / "config" / "settings.json"
    monkeypatch.setenv("SETTINGS_PATH", str(cfg_path))
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "0")
    return cfg_path
