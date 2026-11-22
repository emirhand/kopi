"""Admin authentication and settings management endpoints."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from kopi.audit import record_audit_event
from kopi.auth.pairing import get_pairing_provider
from kopi.auth.rate_limit import get_auth_rate_limiter
from kopi.config import (
    OktaConfig,
    SmtpConfig,
    is_admin_password_managed,
    is_okta_token_managed,
    is_pairing_pin_managed,
    is_smtp_password_managed,
    load_settings,
    normalize_allowed_domains,
    save_settings,
    verify_admin_password,
    verify_pairing_pin,
)
from kopi.processing.okta import normalize_okta_domain
from kopi.hardware import (
    get_hardware_lock,
    list_printer_queues_async,
    list_scan_devices_async,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN_AUTH_SCOPE = "admin_password"


class AdminVerifyBody(BaseModel):
    password: str


class AdminSettingsUpdate(BaseModel):
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    okta: OktaConfig = Field(default_factory=OktaConfig)
    scanner_device: str = ""
    printer_device: str = ""
    enable_usb_scan: bool = True
    enable_email_scan: bool = True
    enable_archive_scan: bool = True
    pairing_pin: str | None = None
    new_admin_password: str | None = None


def _require_admin(x_admin_password: str | None, client_ip: str | None = None) -> None:
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    limiter = get_auth_rate_limiter()
    limiter.check(ADMIN_AUTH_SCOPE, client_ip)
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        limiter.record_failure(ADMIN_AUTH_SCOPE, client_ip)
        record_audit_event("admin_auth", outcome="denied", client_ip=client_ip)
        raise HTTPException(status_code=403, detail="Invalid admin password")
    limiter.record_success(ADMIN_AUTH_SCOPE, client_ip)


@router.post("/verify")
async def api_admin_verify(body: AdminVerifyBody, request: Request) -> dict[str, bool]:
    client_ip = request.client.host if request.client else None
    limiter = get_auth_rate_limiter()
    limiter.check(ADMIN_AUTH_SCOPE, client_ip)
    settings = load_settings()
    valid = verify_admin_password(settings, body.password)
    if valid:
        limiter.record_success(ADMIN_AUTH_SCOPE, client_ip)
        record_audit_event("admin_login", outcome="success", client_ip=client_ip)
    else:
        limiter.record_failure(ADMIN_AUTH_SCOPE, client_ip)
        record_audit_event("admin_login", outcome="denied", client_ip=client_ip)
    return {"valid": valid}


@router.get("/settings")
async def api_admin_settings(
    request: Request,
    refresh: bool = Query(default=False),
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else None
    _require_admin(x_admin_password, client_ip)
    settings = load_settings()
    smtp_data = settings.smtp.model_dump(exclude={"password"})
    smtp_data["password_set"] = bool(settings.smtp.password)
    smtp_data["password_managed"] = is_smtp_password_managed()
    okta_data = settings.okta.model_dump(exclude={"api_token"})
    okta_data["api_token_set"] = bool(settings.okta.api_token)
    okta_data["api_token_managed"] = is_okta_token_managed()
    lock = get_hardware_lock()
    scanners, printers = await asyncio.gather(
        list_scan_devices_async(is_busy=lock.is_busy, force_refresh=refresh),
        list_printer_queues_async(force_refresh=refresh),
    )
    return {
        "smtp": smtp_data,
        "okta": okta_data,
        "scanner_device": settings.scanner_device,
        "printer_device": settings.printer_device,
        "enable_usb_scan": settings.enable_usb_scan,
        "enable_email_scan": settings.enable_email_scan,
        "enable_archive_scan": settings.enable_archive_scan,
        "pairing_pin_set": bool(settings.pairing_pin),
        "pairing_pin_managed": is_pairing_pin_managed(),
        "admin_password_managed": is_admin_password_managed(),
        "paired_device_id": settings.paired_device_id,
        "paired_device_label": settings.paired_device_label,
        "paired_at": settings.paired_at,
        "hardware_options": {
            "scanners": scanners,
            "printers": printers,
        },
    }


@router.put("/settings")
async def api_admin_settings_put(
    body: AdminSettingsUpdate,
    request: Request,
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else None
    _require_admin(x_admin_password, client_ip)
    settings = load_settings()
    existing_smtp_password = settings.smtp.password
    existing_okta_token = settings.okta.api_token

    body.smtp.allowed_domains = normalize_allowed_domains(body.smtp.allowed_domains)
    settings.smtp = body.smtp
    if not body.smtp.password:
        settings.smtp.password = existing_smtp_password

    try:
        normalized_okta_domain = normalize_okta_domain(body.okta.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.okta.enabled and not normalized_okta_domain:
        raise HTTPException(
            status_code=400,
            detail="Okta domain is required when Okta verification is enabled.",
        )
    settings.okta = OktaConfig(
        enabled=bool(body.okta.enabled),
        domain=normalized_okta_domain,
        api_token=body.okta.api_token.strip() or existing_okta_token,
    )
    if settings.okta.enabled and not settings.okta.api_token:
        raise HTTPException(
            status_code=400,
            detail="Okta API token is required when Okta verification is enabled.",
        )

    settings.scanner_device = body.scanner_device.strip()
    settings.printer_device = body.printer_device.strip()
    settings.enable_usb_scan = bool(body.enable_usb_scan)
    settings.enable_email_scan = bool(body.enable_email_scan)
    settings.enable_archive_scan = bool(body.enable_archive_scan)
    if body.pairing_pin is not None and body.pairing_pin.strip():
        candidate_pin = body.pairing_pin.strip()
        if is_pairing_pin_managed():
            if not verify_pairing_pin(settings, candidate_pin):
                raise HTTPException(
                    status_code=400,
                    detail="Pairing PIN is managed externally and cannot be changed.",
                )
        else:
            settings.pairing_pin = candidate_pin
    if body.new_admin_password is not None and body.new_admin_password.strip():
        candidate_pw = body.new_admin_password.strip()
        if is_admin_password_managed():
            if not verify_admin_password(settings, candidate_pw):
                raise HTTPException(
                    status_code=400,
                    detail="Admin password is managed externally and cannot be changed.",
                )
        else:
            settings.admin_password = candidate_pw
    save_settings(settings)
    record_audit_event("admin_settings_update", outcome="success", client_ip=client_ip)
    return {"ok": True, "message": "Settings saved"}


@router.post("/unpair")
async def api_admin_unpair(
    request: Request,
    x_admin_password: str | None = Header(default=None, alias="X-Admin-Password"),
) -> dict[str, Any]:
    client_ip = request.client.host if request.client else None
    _require_admin(x_admin_password, client_ip)
    get_pairing_provider().unpair()
    record_audit_event("admin_unpair", outcome="success", client_ip=client_ip)
    return {"ok": True, "message": "Paired tablet disconnected"}

