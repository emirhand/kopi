"""Client pairing and tablet replacement endpoints (/api/pair/*)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Cookie, Header, Request, Response
from pydantic import BaseModel, Field

from kopi.auth.dependencies import (
    DEVICE_TOKEN_COOKIE_NAME,
    DEVICE_TOKEN_HEADER_NAME,
    extract_device_token,
)
from kopi.auth.pairing import get_pairing_provider

router = APIRouter(prefix="/api/pair", tags=["pairing"])

TEN_YEARS_SECONDS = 10 * 365 * 24 * 60 * 60


def _is_cookie_secure(request: Request) -> bool:
    raw = os.environ.get("KOPI_COOKIE_SECURE", "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    return request.url.scheme == "https"


def _set_device_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=DEVICE_TOKEN_COOKIE_NAME,
        value=token,
        max_age=TEN_YEARS_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_is_cookie_secure(request),
        path="/",
    )


class PairClaimBody(BaseModel):
    pin: str = Field(..., min_length=1)
    device_label: str | None = "Paired Tablet"


class PairReplaceBody(BaseModel):
    admin_password: str = Field(..., min_length=1)
    device_label: str | None = "Replacement Tablet"


@router.get("/status")
async def api_pair_status(
    request: Request,
    response: Response,
    header_token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER_NAME),
    cookie_token: str | None = Cookie(default=None, alias=DEVICE_TOKEN_COOKIE_NAME),
) -> dict[str, Any]:
    token = extract_device_token(header_token=header_token, cookie_token=cookie_token)
    provider = get_pairing_provider()
    status = provider.get_status(token)
    # If the tablet authenticated via localStorage header, refresh its HttpOnly cookie too
    if status.caller_is_paired and token:
        _set_device_cookie(response, request, token)
    return status.model_dump()


@router.post("/claim")
async def api_pair_claim(
    body: PairClaimBody,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    provider = get_pairing_provider()
    client_ip = request.client.host if request.client else None
    result = provider.claim(pin=body.pin, device_label=body.device_label, client_ip=client_ip)
    _set_device_cookie(response, request, result.token)
    return result.model_dump()


@router.post("/replace")
async def api_pair_replace(
    body: PairReplaceBody,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    provider = get_pairing_provider()
    client_ip = request.client.host if request.client else None
    result = provider.replace_with_admin(
        admin_password=body.admin_password,
        device_label=body.device_label,
        client_ip=client_ip,
    )
    _set_device_cookie(response, request, result.token)
    return result.model_dump()
