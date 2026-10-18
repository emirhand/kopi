"""FastAPI dependencies for enforcing exclusive paired tablet access."""

from __future__ import annotations

from fastapi import Cookie, Header, HTTPException

from kopi.auth.pairing import get_pairing_provider, is_pairing_required

DEVICE_TOKEN_COOKIE_NAME = "kopi_device_token"
DEVICE_TOKEN_HEADER_NAME = "X-Kopi-Device-Token"


def extract_device_token(
    header_token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER_NAME),
    cookie_token: str | None = Cookie(default=None, alias=DEVICE_TOKEN_COOKIE_NAME),
) -> str | None:
    """Extract the client's pairing token from header (preferred) or HttpOnly cookie."""
    if header_token and header_token.strip():
        return header_token.strip()
    if cookie_token and cookie_token.strip():
        return cookie_token.strip()
    return None


async def require_paired_client(
    header_token: str | None = Header(default=None, alias=DEVICE_TOKEN_HEADER_NAME),
    cookie_token: str | None = Cookie(default=None, alias=DEVICE_TOKEN_COOKIE_NAME),
) -> None:
    """Verify the request comes from the exclusively paired tablet.

    - If the station is paired, only the matching token is allowed (otherwise 403).
    - If the station is unpaired and KOPI_REQUIRE_PAIRING is enabled (default),
      operational endpoints are blocked with 403 Pairing Required.
    """
    token = extract_device_token(header_token=header_token, cookie_token=cookie_token)
    provider = get_pairing_provider()
    status = provider.get_status(token)

    if status.paired:
        if not status.caller_is_paired:
            raise HTTPException(
                status_code=403,
                detail="Station is paired to another tablet. Access denied.",
            )
        return

    if is_pairing_required():
        raise HTTPException(
            status_code=403,
            detail="Pairing required. Please pair this tablet to use the station.",
        )
