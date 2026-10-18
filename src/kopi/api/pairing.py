"""Client pairing and tablet replacement endpoints (/api/pair/*)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Cookie, Header, Response
from pydantic import BaseModel, Field

from kopi.auth.dependencies import (
    DEVICE_TOKEN_COOKIE_NAME,
    DEVICE_TOKEN_HEADER_NAME,
    extract_device_token,
)
from kopi.auth.pairing import get_pairing_provider

router = APIRouter(prefix="/api/pair", tags=["pairing"])

TEN_YEARS_SECONDS = 10 * 365 * 24 * 60 * 60


def _set_device_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=DEVICE_TOKEN_COOKIE_NAME,
        value=token,
        max_age=TEN_YEARS_SECONDS,
        httponly=True,
        samesite="lax",
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
    response: Response,
    header_token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER_NAME),
    cookie_token: str | None = Cookie(default=None, alias=DEVICE_TOKEN_COOKIE_NAME),
) -> dict[str, Any]:
    token = extract_device_token(header_token=header_token, cookie_token=cookie_token)
    provider = get_pairing_provider()
    status = provider.get_status(token)
    # If the tablet authenticated via localStorage header, refresh its HttpOnly cookie too
    if status.caller_is_paired and token:
        _set_device_cookie(response, token)
    return status.model_dump()


@router.post("/claim")
async def api_pair_claim(body: PairClaimBody, response: Response) -> dict[str, Any]:
    provider = get_pairing_provider()
    result = provider.claim(pin=body.pin, device_label=body.device_label)
    _set_device_cookie(response, result.token)
    return result.model_dump()


@router.post("/replace")
async def api_pair_replace(body: PairReplaceBody, response: Response) -> dict[str, Any]:
    provider = get_pairing_provider()
    result = provider.replace_with_admin(
        admin_password=body.admin_password,
        device_label=body.device_label,
    )
    _set_device_cookie(response, result.token)
    return result.model_dump()
