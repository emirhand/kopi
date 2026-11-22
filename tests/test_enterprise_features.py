"""Tests for enterprise features: Okta verification, domain allowlist, audit log, secret files, archive toggle, attachment cap, and per-IP rate limiting."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from kopi.auth.rate_limit import AuthRateLimiter
from kopi.config import OktaConfig, SettingsError, SmtpConfig, load_settings, save_settings
from kopi.hardware import reset_bridges
from kopi.main import create_app
from kopi.processing import mailer, okta


@pytest.fixture
def app(
    temp_settings_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "0")
    monkeypatch.setenv("KOPI_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    reset_bridges()
    return create_app()


def test_email_domain_allowlist_and_max_attachment_size() -> None:
    assert mailer.is_email_domain_allowed("user@example.com", []) is True
    assert mailer.is_email_domain_allowed("User@UDEMY.COM", ["udemy.com", "@coursera.org"]) is True
    assert mailer.is_email_domain_allowed("user@gmail.com", ["udemy.com"]) is False

    ok, err = mailer.send_attachment_email(
        b"x" * (2 * 1024 * 1024),
        filename="big.pdf",
        to_addr="user@udemy.com",
        subject="Test",
        smtp=SmtpConfig(
            host="smtp.example.com",
            port=587,
            allowed_domains=["udemy.com"],
            max_attachment_mb=1,
        ),
    )
    assert ok is False
    assert err == "Total attachment size exceeds 1 MB limit"


def test_normalize_okta_domain_rejects_insecure_or_paths() -> None:
    assert okta.normalize_okta_domain("company.okta.com") == "https://company.okta.com"
    assert okta.normalize_okta_domain("https://company.okta.com/") == "https://company.okta.com"
    with pytest.raises(ValueError):
        okta.normalize_okta_domain("http://company.okta.com")
    with pytest.raises(ValueError):
        okta.normalize_okta_domain("https://company.okta.com/admin")


@pytest.mark.asyncio
async def test_okta_and_domain_allowlist_enforced_in_scan_email_and_audited(
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kopi.api.scan as scan_mod

    settings = load_settings()
    settings.smtp = SmtpConfig(
        host="smtp.example.com",
        port=587,
        allowed_domains=["udemy.com", "coursera.org"],
    )
    settings.okta = OktaConfig(
        enabled=True,
        domain="https://company.okta.com",
        api_token="secret-ssws-token",
    )
    save_settings(settings)

    async def fake_okta_check(
        email: str, *, domain: str, api_token: str, timeout_sec: float = 5.0
    ) -> tuple[bool, str | None]:
        _ = domain, api_token, timeout_sec
        if email.lower() == "active@udemy.com":
            return True, None
        return False, "Recipient is not an active Okta user"

    monkeypatch.setattr(scan_mod, "verify_okta_active_user", fake_okta_check)
    monkeypatch.setattr(scan_mod.mailer, "send_attachments_email", lambda *a, **kw: (True, None))
    monkeypatch.setattr(scan_mod.mailer, "send_attachment_email", lambda *a, **kw: (True, None))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Disallowed domain rejected before Okta/scan
        bad_dom = await client.post("/api/scan/email", json={"recipient": "person@gmail.com"})
        assert bad_dom.status_code == 400
        assert bad_dom.json()["detail"] == "Email address invalid (not an allowed domain)"

        # 2. Allowed domain but inactive/missing in Okta -> 403
        bad_okta = await client.post("/api/scan/email", json={"recipient": "former@udemy.com"})
        assert bad_okta.status_code == 403
        assert "Okta" in bad_okta.json()["detail"]

        # 3. Allowed domain AND active Okta user -> 200
        ok_res = await client.post("/api/scan/email", json={"recipient": "active@udemy.com"})
        assert ok_res.status_code == 200

    audit_path = tmp_path / "audit.jsonl"
    assert audit_path.is_file()
    assert stat.S_IMODE(audit_path.stat().st_mode) == 0o600
    events = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [e["outcome"] for e in events] == ["denied", "denied", "success"]
    assert events[-1]["action"] == "scan_email"
    assert events[-1]["detail"]["recipient_domain"] == "udemy.com"


@pytest.mark.asyncio
async def test_archive_scan_toggle_disables_archive_endpoint(app: FastAPI) -> None:
    settings = load_settings()
    settings.enable_archive_scan = False
    save_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pub = await client.get("/api/settings/public")
        assert pub.status_code == 200
        assert pub.json()["enable_archive_scan"] is False

        res = await client.post("/api/scan/archive", json={})
        assert res.status_code == 403


def test_smtp_and_okta_secret_files_not_written_to_disk(
    temp_settings_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    smtp_file = tmp_path / "smtp_pw.secret"
    smtp_file.write_text("file-smtp-pw\n", encoding="utf-8")
    okta_file = tmp_path / "okta_tok.secret"
    okta_file.write_text("file-okta-tok\n", encoding="utf-8")

    monkeypatch.setenv("KOPI_SMTP_PASSWORD_FILE", str(smtp_file))
    monkeypatch.setenv("KOPI_OKTA_API_TOKEN_FILE", str(okta_file))

    loaded = load_settings()
    assert loaded.smtp.password == "file-smtp-pw"
    assert loaded.okta.api_token == "file-okta-tok"

    save_settings(loaded)
    raw = json.loads(temp_settings_path.read_text(encoding="utf-8"))
    assert raw["smtp"]["password"] == ""
    assert raw["okta"]["api_token"] == ""

    # Missing file fails closed
    monkeypatch.setenv("KOPI_OKTA_API_TOKEN_FILE", str(tmp_path / "missing.secret"))
    with pytest.raises(SettingsError, match="missing"):
        load_settings()


def test_per_ip_rate_limiting_isolates_noisy_client() -> None:
    limiter = AuthRateLimiter(clock=lambda: 100.0)
    for _ in range(5):
        limiter.record_failure("admin_password", "192.168.1.99")

    with pytest.raises(HTTPException) as exc_info:
        limiter.check("admin_password", "192.168.1.99")
    assert exc_info.value.status_code == 429

    # Different client IP is not locked out by the noisy client
    limiter.check("admin_password", "192.168.1.10")
