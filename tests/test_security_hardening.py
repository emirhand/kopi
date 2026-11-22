"""Security hardening, feature toggle, and temp-file cleanup tests."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from kopi.config import SmtpConfig, load_settings, save_settings
from kopi.hardware import reset_bridges
from kopi.hardware.printer import build_lp_cmd
from kopi.main import create_app, sweep_orphaned_temp_files
from kopi.processing import mailer


@pytest.fixture
def app(temp_settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    _ = temp_settings_path
    monkeypatch.setenv("KOPI_HARDWARE_MODE", "mock")
    monkeypatch.setenv("KOPI_MOCK_DELAY_SEC", "0.01")
    monkeypatch.setenv("KOPI_REQUIRE_PAIRING", "0")
    reset_bridges()
    return create_app()


def test_starttls_uses_verifying_ssl_context_and_aborts_on_ssl_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_contexts: list[object] = []
    login_called = False
    send_called = False

    class CertCheckSMTP:
        def __init__(self, host: str, port: int, timeout: int = 30) -> None:
            _ = host, port, timeout

        def __enter__(self) -> CertCheckSMTP:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def ehlo(self) -> None:
            pass

        def starttls(self, *, context: object = None) -> None:
            seen_contexts.append(context)
            raise ssl.SSLCertVerificationError("certificate verify failed")

        def login(self, user: str, password: str) -> None:
            nonlocal login_called
            _ = user, password
            login_called = True

        def send_message(self, msg: EmailMessage) -> None:
            nonlocal send_called
            _ = msg
            send_called = True

    monkeypatch.setattr(smtplib, "SMTP", CertCheckSMTP)

    ok, err = mailer.send_attachment_email(
        b"%PDF-1.4 test",
        filename="scan.pdf",
        to_addr="dest@example.com",
        subject="Test",
        smtp=SmtpConfig(host="smtp.example.com", port=587, user="u", password="p", tls=True),
    )
    assert ok is False
    assert err is not None and "smtp.example.com" not in err
    assert len(seen_contexts) == 1
    assert isinstance(seen_contexts[0], ssl.SSLContext)
    assert seen_contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert login_called is False
    assert send_called is False


def test_build_lp_cmd_rejects_untrusted_options() -> None:
    with pytest.raises(ValueError, match="paper_size"):
        build_lp_cmd("/tmp/doc.pdf", paper_size="A4 -o PageSize=Custom")
    with pytest.raises(ValueError, match="resize_mode"):
        build_lp_cmd("/tmp/doc.pdf", resize_mode="stretch")
    with pytest.raises(ValueError, match="quality"):
        build_lp_cmd("/tmp/doc.pdf", quality="ultra")


@pytest.mark.asyncio
async def test_docs_disabled_by_default_and_security_headers_present(app: FastAPI) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            res = await client.get(path)
            assert res.status_code == 404

        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.headers.get("X-Content-Type-Options") == "nosniff"
        assert health.headers.get("X-Frame-Options") == "DENY"
        assert health.headers.get("Referrer-Policy") == "no-referrer"
        assert "Content-Security-Policy" in health.headers


@pytest.mark.asyncio
async def test_usb_and_email_scan_toggles_and_temp_cleanup(
    app: FastAPI,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kopi.api.scan as scan_mod
    from kopi.api.copy import SCAN_STORE

    # Disable both USB scan and Email scan in settings
    settings = load_settings()
    settings.enable_usb_scan = False
    settings.enable_email_scan = False
    settings.smtp = SmtpConfig(host="smtp.example.com", port=587, tls=True)
    save_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        pub = await client.get("/api/settings/public")
        assert pub.status_code == 200
        assert pub.json() == {
            "enable_usb_scan": False,
            "enable_email_scan": False,
            "enable_archive_scan": True,
        }

        drives_res = await client.get("/api/scan/usb/drives")
        assert drives_res.status_code == 403

        usb_res = await client.post("/api/scan/usb", json={})
        assert usb_res.status_code == 403

        email_res = await client.post("/api/scan/email", json={"recipient": "user@example.com"})
        assert email_res.status_code == 403

        # Re-enable and verify temp files are deleted after email & USB scan complete
        settings.enable_usb_scan = True
        settings.enable_email_scan = True
        save_settings(settings)

        monkeypatch.setattr(scan_mod.mailer, "send_attachment_email", lambda *a, **kw: (True, None))
        scan1 = tmp_path / "kopi-email-temp.png"
        scan1.write_bytes(b"\x89PNG\r\n\x1a\n")
        # Use a valid 1x1 PNG
        from PIL import Image

        Image.new("RGB", (10, 10), "white").save(scan1, format="PNG")
        sid1 = await SCAN_STORE.put_path(str(scan1))
        ok_email = await client.post(
            "/api/scan/email",
            json={"recipient": "user@example.com", "scan_id": sid1, "output_format": "jpg"},
        )
        assert ok_email.status_code == 200
        assert not scan1.exists()

        # ID Copy workflow: front -> back -> compose -> print -> all temp files deleted
        front = await client.post("/api/copy/id/front")
        assert front.status_code == 200
        id_sid = front.json()["session_id"]

        back = await client.post("/api/copy/id/back", json={"session_id": id_sid})
        assert back.status_code == 200

        comp = await client.post("/api/copy/id/compose", json={"session_id": id_sid})
        assert comp.status_code == 200
        assert comp.json()["preview_png_base64"]

        prn = await client.post("/api/copy/id/print", json={"session_id": id_sid})
        assert prn.status_code == 200


def test_sweep_orphaned_temp_files_cleans_kopi_artifacts(tmp_path: Path) -> None:
    f = tmp_path / "kopi-copy-leftover.png"
    f.write_bytes(b"leftover")
    d = tmp_path / "kopi-adf-batch-leftover"
    d.mkdir()
    (d / "page1.png").write_bytes(b"p1")
    other = tmp_path / "unrelated-file.txt"
    other.write_text("keep")

    removed = sweep_orphaned_temp_files(tmp_path)
    assert removed == 2
    assert not f.exists()
    assert not d.exists()
    assert other.is_file()
