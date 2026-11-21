"""Typed models for client pairing status and claim results."""

from __future__ import annotations

from pydantic import BaseModel


class PairingStatus(BaseModel):
    """Public status of the station's exclusive tablet pairing."""

    paired: bool
    require_pairing: bool
    caller_is_paired: bool
    device_id: str | None = None
    device_label: str | None = None
    paired_at: str | None = None


class PairingClaimResult(BaseModel):
    """Result returned when a client claims or replaces pairing."""

    ok: bool = True
    token: str
    device_id: str
    device_label: str
    paired_at: str
