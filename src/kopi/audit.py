"""Append-only structured JSONL audit logging for Kopi operations."""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kopi.config import get_settings_path

log = logging.getLogger("kopi.audit")
_AUDIT_LOCK = threading.Lock()


def get_audit_log_path() -> Path:
    """Resolve the audit log path from KOPI_AUDIT_LOG_PATH or alongside settings.json."""
    env_path = os.environ.get("KOPI_AUDIT_LOG_PATH", "").strip()
    if env_path:
        return Path(env_path)
    return get_settings_path().parent / "audit.jsonl"


def record_audit_event(
    action: str,
    *,
    outcome: str,
    client_ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append a single structured JSONL audit record without raising on I/O errors."""
    import json

    entry: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(),
        "action": action,
        "outcome": outcome,
    }
    if client_ip:
        entry["client_ip"] = client_ip
    if detail:
        entry["detail"] = detail

    line = json.dumps(entry, separators=(",", ":")) + "\n"
    path = get_audit_log_path()
    try:
        with _AUDIT_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
    except OSError as exc:
        log.warning("audit_log_write_failed path=%s err=%s", path, exc)
