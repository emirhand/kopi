"""Pluggable client pairing and exclusive access control for Kopi."""

from __future__ import annotations

from kopi.auth.dependencies import extract_device_token, require_paired_client
from kopi.auth.models import PairingClaimResult, PairingStatus
from kopi.auth.pairing import (
    PairingProvider,
    StaticPinPairingProvider,
    get_pairing_provider,
)

__all__ = [
    "PairingClaimResult",
    "PairingProvider",
    "PairingStatus",
    "StaticPinPairingProvider",
    "extract_device_token",
    "get_pairing_provider",
    "require_paired_client",
]
