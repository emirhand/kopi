"""Admin authentication and settings management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from kopi.auth.pairing import get_pairing_provider
from kopi.auth.rate_limit import get_auth_rate_limiter
from kopi.config import SmtpConfig, load_settings, save_settings, verify_admin_password
from kopi.hardware import list_printer_queues, list_scan_devices

router = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN_AUTH_SCOPE = "admin_password"


class AdminVerifyBody(BaseModel):
    password: str


class AdminSettingsUpdate(BaseModel):
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    scanner_device: str = ""
    printer_device: str = ""
    usb_roots: list[str] = Field(default_factory=list)
    id_scan_ocr: bool = False
    pairing_pin: str | None = None
    new_admin_password: str | None = None


def _require_admin(x_admin_password: str | None) -> None:
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    limiter = get_auth_rate_limiter()
    limiter.check(ADMIN_AUTH_SCOPE)
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        limiter.record_failure(ADMIN_AUTH_SCOPE)
        raise HTTPException(status_code=403, detail="Invalid admin password")
    limiter.record_success(ADMIN_AUTH_SCOPE)


@router.post("/verify")
async def api_admin_verify(body: AdminVerifyBody) -> dict[str, bool]:
    limiter = get_auth_rate_limiter()
    limiter.check(ADMIN_AUTH_SCOPE)
    settings = load_settings()
    valid = verify_admin_password(settings, body.password)
    if valid:
        limiter.record_success(ADMIN_AUTH_SCOPE)
    else:
        limiter.record_failure(ADMIN_AUTH_SCOPE)
    return {"valid": valid}


@router.get("/settings")
async def api_admin_settings(
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    _require_admin(x_admin_password)
    settings = load_settings()
    smtp_data = settings.smtp.model_dump(exclude={"password"})
    smtp_data["password_set"] = bool(settings.smtp.password)
    return {
        "smtp": smtp_data,
        "scanner_device": settings.scanner_device,
        "printer_device": settings.printer_device,
        "usb_roots": settings.usb_roots,
        "id_scan_ocr": settings.id_scan_ocr,
        "pairing_pin_set": bool(settings.pairing_pin),
        "paired_device_id": settings.paired_device_id,
        "paired_device_label": settings.paired_device_label,
        "paired_at": settings.paired_at,
        "hardware_options": {
            "scanners": list_scan_devices(),
            "printers": list_printer_queues(),
        },
    }


@router.put("/settings")
async def api_admin_settings_put(
    body: AdminSettingsUpdate,
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    _require_admin(x_admin_password)
    settings = load_settings()
    existing_smtp_password = settings.smtp.password
    settings.smtp = body.smtp
    if not body.smtp.password:
        settings.smtp.password = existing_smtp_password
    settings.scanner_device = body.scanner_device.strip()
    settings.printer_device = body.printer_device.strip()
    settings.usb_roots = [x.strip() for x in body.usb_roots if x.strip()]
    settings.id_scan_ocr = bool(body.id_scan_ocr)
    if body.pairing_pin is not None and body.pairing_pin.strip():
        settings.pairing_pin = body.pairing_pin.strip()
    if body.new_admin_password is not None and body.new_admin_password.strip():
        settings.admin_password = body.new_admin_password.strip()
    save_settings(settings)
    return {"ok": True, "message": "Settings saved"}


@router.post("/unpair")
async def api_admin_unpair(
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    _require_admin(x_admin_password)
    get_pairing_provider().unpair()
    return {"ok": True, "message": "Paired tablet disconnected"}

