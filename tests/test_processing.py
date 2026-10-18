"""TDD tests for pure-Python PDF blank page removal, ID card A4 composition, and SMTP mailer."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import img2pdf
import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader

from kopi.config import SmtpConfig
from kopi.processing.id_card import (
    compose_id_scans_to_a4_pdf,
    pdf_to_preview_png_base64,
)
from kopi.processing.mailer import send_attachment_email, send_pdf_email
from kopi.processing.pdf import is_image_blank, remove_blank_pages_from_pdf


def _make_png(path: Path, *, blank: bool, size: tuple[int, int] = (400, 560)) -> None:
    img = Image.new("RGB", size, color=(255, 255, 255))
    if not blank:
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 40, 360, 260), fill=(15, 20, 30))
        draw.rectangle((40, 300, 360, 500), fill=(30, 60, 120))
    img.save(path, format="PNG")


def test_is_image_blank_detection() -> None:
    white_img = Image.new("RGB", (300, 400), color=(254, 254, 254))
    assert is_image_blank(white_img) is True

    content_img = Image.new("RGB", (300, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(content_img)
    draw.rectangle((30, 30, 270, 200), fill=(10, 10, 10))
    assert is_image_blank(content_img) is False


def test_remove_blank_pages_from_pdf_pure_python(tmp_path: Path) -> None:
    p1 = tmp_path / "p1.png"
    p2_blank = tmp_path / "p2.png"
    p3 = tmp_path / "p3.png"
    _make_png(p1, blank=False)
    _make_png(p2_blank, blank=True)
    _make_png(p3, blank=False)

    in_pdf = tmp_path / "in.pdf"
    out_pdf = tmp_path / "out.pdf"
    pdf_bytes = img2pdf.convert([str(p1), str(p2_blank), str(p3)])
    assert pdf_bytes is not None
    in_pdf.write_bytes(pdf_bytes)

    ok, err = remove_blank_pages_from_pdf(in_pdf, out_pdf)
    assert ok is True
    assert err is None
    reader = PdfReader(str(out_pdf))
    assert len(reader.pages) == 2


def test_compose_id_scans_to_a4_pdf_and_preview(tmp_path: Path) -> None:
    front = tmp_path / "front.png"
    back = tmp_path / "back.png"
    _make_png(front, blank=False, size=(325, 204))
    _make_png(back, blank=False, size=(325, 204))

    out_pdf = tmp_path / "id_a4.pdf"
    ok, err = compose_id_scans_to_a4_pdf(front, back, out_pdf)
    assert ok is True
    assert err is None
    assert out_pdf.is_file()
    reader = PdfReader(str(out_pdf))
    assert len(reader.pages) == 1

    b64, prev_err = pdf_to_preview_png_base64(out_pdf)
    assert prev_err is None
    assert b64 is not None
    raw_png = base64.b64decode(b64)
    img = Image.open(io.BytesIO(raw_png))
    assert img.width > 0 and img.height > 0


def test_mailer_validation_and_mock_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    # Missing host should return a clean error
    empty_smtp = SmtpConfig(host="", port=587)
    ok, err = send_pdf_email(
        b"%PDF-1.4 mock",
        to_addr="user@example.com",
        subject="Test Scan",
        smtp=empty_smtp,
    )
    assert ok is False
    assert err is not None and "SMTP" in err

    sent_messages: list[object] = []

    class DummySMTP:
        def __init__(self, host: str, port: int, timeout: int = 30) -> None:
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self) -> DummySMTP:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def ehlo(self) -> None:
            pass

        def starttls(self) -> None:
            pass

        def login(self, user: str, password: str) -> None:
            _ = user, password

        def send_message(self, msg: object) -> None:
            sent_messages.append(msg)

    import smtplib

    monkeypatch.setattr(smtplib, "SMTP", DummySMTP)

    valid_smtp = SmtpConfig(
        host="smtp.example.com",
        port=587,
        user="kopi@example.com",
        password="secret",
        from_email="kopi@example.com",
        tls=True,
    )
    ok2, err2 = send_attachment_email(
        b"%PDF-1.4 mock",
        filename="scan.pdf",
        to_addr="dest@example.com",
        subject="Scan Ready",
        smtp=valid_smtp,
    )
    assert ok2 is True
    assert err2 is None
    assert len(sent_messages) == 1
