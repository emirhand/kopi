"""Pluggable client pairing and exclusive access control for Kopi."""

from __future__ import annotations

from kopi.auth.dependencies import extract_device_token, require_paired_client
from kopi.auth.models import PairingClaimResult, PairingStatus
from kopi.auth.pairing import (
    PairingProvider,
    StaticPinPairingProvider,
    get_pairing_provider,
)
from kopi.auth.rate_limit import (
    AuthRateLimiter,
    get_auth_rate_limiter,
    reset_auth_rate_limiter,
)

__all__ = [
    "AuthRateLimiter",
    "PairingClaimResult",
    "PairingProvider",
    "PairingStatus",
    "StaticPinPairingProvider",
    "extract_device_token",
    "get_auth_rate_limiter",
    "get_pairing_provider",
    "require_paired_client",
    "reset_auth_rate_limiter",
]
