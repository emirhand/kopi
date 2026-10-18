"""Pluggable PairingProvider interface and StaticPinPairingProvider implementation."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime

from fastapi import HTTPException

from kopi.auth.models import PairingClaimResult, PairingStatus
from kopi.config import (
    KopiSettings,
    load_settings,
    save_settings,
    verify_admin_password,
    verify_pairing_pin,
)


def _hash_token(raw_token: str) -> str:
    """Compute SHA-256 hex digest of a raw device token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def is_pairing_required() -> bool:
    """Return True if unpaired stations require pairing before operational endpoints run."""
    val = os.environ.get("KOPI_REQUIRE_PAIRING", "1").strip().lower()
    return val not in {"0", "false", "no"}


class PairingProvider(ABC):
    """Abstract interface for tablet pairing and exclusive access verification."""

    @abstractmethod
    def get_status(self, caller_token: str | None = None) -> PairingStatus:
        """Return current pairing state and whether caller_token matches the paired device."""

    @abstractmethod
    def verify_token(self, caller_token: str | None) -> bool:
        """Return True if caller_token matches the currently paired device."""

    @abstractmethod
    def claim(self, pin: str, device_label: str | None = None) -> PairingClaimResult:
        """Pair a new device when the station is currently unpaired."""

    @abstractmethod
    def replace_with_admin(
        self,
        admin_password: str,
        device_label: str | None = None,
    ) -> PairingClaimResult:
        """Atomically revoke any existing tablet and pair the calling tablet using Admin PIN."""

    @abstractmethod
    def unpair(self) -> None:
        """Clear the active device pairing."""


class StaticPinPairingProvider(PairingProvider):
    """Pairing provider backed by static PIN in settings.json and SHA-256 token hash."""

    def _issue_pairing(
        self,
        settings: KopiSettings,
        device_label: str | None,
    ) -> PairingClaimResult:
        raw_token = secrets.token_urlsafe(32)
        device_id = f"tab-{uuid.uuid4().hex[:12]}"
        clean_label = (device_label or "").strip()[:64] or "Paired Tablet"
        paired_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        settings.paired_device_id = device_id
        settings.paired_device_label = clean_label
        settings.paired_at = paired_at
        settings.paired_device_token_hash = _hash_token(raw_token)
        save_settings(settings)

        return PairingClaimResult(
            ok=True,
            token=raw_token,
            device_id=device_id,
            device_label=clean_label,
            paired_at=paired_at,
        )

    def verify_token(self, caller_token: str | None) -> bool:
        settings = load_settings()
        expected_hash = (settings.paired_device_token_hash or "").strip()
        if not expected_hash or not caller_token:
            return False
        provided_hash = _hash_token(caller_token.strip())
        return hmac.compare_digest(expected_hash, provided_hash)

    def get_status(self, caller_token: str | None = None) -> PairingStatus:
        settings = load_settings()
        is_paired = bool((settings.paired_device_token_hash or "").strip())
        caller_matches = self.verify_token(caller_token) if is_paired else False
        return PairingStatus(
            paired=is_paired,
            require_pairing=is_pairing_required(),
            caller_is_paired=caller_matches,
            device_id=settings.paired_device_id if is_paired else None,
            device_label=settings.paired_device_label if is_paired else None,
            paired_at=settings.paired_at if is_paired else None,
        )

    def claim(self, pin: str, device_label: str | None = None) -> PairingClaimResult:
        settings = load_settings()
        if (settings.paired_device_token_hash or "").strip():
            raise HTTPException(
                status_code=409,
                detail=(
                    "Station is already paired to a tablet. "
                    "Use Admin PIN replacement to pair this device instead."
                ),
            )
        if not verify_pairing_pin(settings, pin):
            raise HTTPException(status_code=403, detail="Invalid pairing PIN")
        return self._issue_pairing(settings, device_label)

    def replace_with_admin(
        self,
        admin_password: str,
        device_label: str | None = None,
    ) -> PairingClaimResult:
        settings = load_settings()
        if not verify_admin_password(settings, admin_password):
            raise HTTPException(status_code=403, detail="Invalid Admin PIN")
        return self._issue_pairing(settings, device_label)

    def unpair(self) -> None:
        settings = load_settings()
        settings.paired_device_id = None
        settings.paired_device_label = None
        settings.paired_at = None
        settings.paired_device_token_hash = None
        save_settings(settings)


def get_pairing_provider() -> PairingProvider:
    """Return the active PairingProvider instance."""
    return StaticPinPairingProvider()
