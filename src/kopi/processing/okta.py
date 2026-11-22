"""Okta directory user verification for Scan-to-Email."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger("kopi.processing.okta")


def normalize_okta_domain(raw: str) -> str:
    """Validate and normalize an Okta base URL (https:// only, no path/userinfo)."""
    val = (raw or "").strip().rstrip("/")
    if not val:
        return ""
    if "://" not in val:
        val = f"https://{val}"
    parsed = urlsplit(val)
    if parsed.scheme.lower() != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Okta domain must be a valid https:// hostname (e.g. company.okta.com)")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("Okta domain must not include a path, query, or fragment")
    return f"https://{parsed.netloc}"


def _check_okta_user_sync(
    email: str,
    *,
    base_url: str,
    api_token: str,
    timeout_sec: float,
) -> tuple[bool, str | None]:
    encoded_email = urllib.parse.quote(email.strip(), safe="")
    url = f"{base_url}/api/v1/users/{encoded_email}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"SSWS {api_token}",
            "Accept": "application/json",
            "User-Agent": "kopi-appliance/0.1",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            if resp.status != 200:
                return False, "Could not verify recipient with Okta"
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "Recipient not found in Okta directory"
        log.warning("okta_lookup_http_error status=%s", exc.code)
        return False, "Could not verify recipient with Okta"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        log.warning("okta_lookup_failed err=%s", exc.__class__.__name__)
        return False, "Could not verify recipient with Okta"

    status = str(data.get("status", "")).upper()
    if status != "ACTIVE":
        return False, "Recipient is not an active Okta user"
    return True, None


async def verify_okta_active_user(
    email: str,
    *,
    domain: str,
    api_token: str,
    timeout_sec: float = 5.0,
) -> tuple[bool, str | None]:
    """Verify that `email` corresponds to an ACTIVE user in the configured Okta tenant."""
    try:
        base_url = normalize_okta_domain(domain)
    except ValueError:
        return False, "Okta domain configuration is invalid"
    token = (api_token or "").strip()
    if not base_url or not token:
        return False, "Okta integration is enabled but not fully configured"
    return await asyncio.to_thread(
        _check_okta_user_sync,
        email,
        base_url=base_url,
        api_token=token,
        timeout_sec=timeout_sec,
    )
