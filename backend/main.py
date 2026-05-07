"""
Linux Smart Copier Appliance — FastAPI bridge to SANE, CUPS, USB, and msmtp.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services import mailer, printer, scanner, usb_manager

APP_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = Path(os.environ.get("SETTINGS_PATH", APP_ROOT / "config" / "settings.json"))


def load_settings() -> dict:
    if not SETTINGS_PATH.is_file():
        raise FileNotFoundError(f"Missing settings file: {SETTINGS_PATH}")
    with SETTINGS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SETTINGS_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def verify_admin_password(settings: dict, password: str) -> bool:
    expected = str(settings.get("admin_password", ""))
    return bool(password) and password == expected


app = FastAPI(title="Linux Smart Copier Appliance", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CopyBody(BaseModel):
    duplex: bool = False


class ScanEmailBody(BaseModel):
    recipient: str = Field(..., min_length=3)


class AdminVerifyBody(BaseModel):
    password: str


class SmtpSettings(BaseModel):
    host: str
    port: int = 587
    user: str = ""
    password: str = ""
    from_email: str = ""
    tls: bool = True


class AdminSettingsUpdate(BaseModel):
    smtp: SmtpSettings


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/copy")
def api_copy(body: CopyBody):
    """
    Pipe scan directly to print: scanimage --format=pdf ... | lp
    """
    cmd = scanner.build_scanimage_pdf_cmd(duplex_scan=body.duplex)
    result = printer.print_from_scanimage_pipe(duplex=body.duplex, scan_cmd=cmd)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.user_message or "Copy failed")
    return {"ok": True, "message": "Copy job submitted"}


@app.post("/api/scan/email")
def api_scan_email(body: ScanEmailBody):
    settings = load_settings()
    scan = scanner.scan_pdf_to_stdout(duplex_scan=False)
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    ok, err = mailer.send_pdf_email(
        scan.stdout,
        to_addr=body.recipient.strip(),
        subject=f"Scan {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        smtp=settings.get("smtp", {}),
    )
    if not ok:
        raise HTTPException(status_code=400, detail=err)
    return {"ok": True, "message": "Scan emailed"}


@app.post("/api/scan/usb")
def api_scan_usb():
    try:
        mount = usb_manager.require_usb_path()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="USB Not Found")

    scan = scanner.scan_pdf_to_stdout(duplex_scan=False)
    if not scan.ok:
        raise HTTPException(status_code=400, detail=scan.user_message or "Scan failed")

    name = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.pdf"
    dest = mount / name
    try:
        dest.write_bytes(scan.stdout)
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Could not write to USB: {e}") from e

    return {"ok": True, "message": f"Saved to {dest}"}


@app.post("/api/admin/verify")
def api_admin_verify(body: AdminVerifyBody):
    settings = load_settings()
    valid = verify_admin_password(settings, body.password)
    return {"valid": valid}


@app.get("/api/admin/settings")
def api_admin_settings(x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password")):
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")
    return {"smtp": settings.get("smtp", {})}


@app.put("/api/admin/settings")
def api_admin_settings_put(
    body: AdminSettingsUpdate,
    x_admin_password: Optional[str] = Header(default=None, alias="X-Admin-Password"),
):
    if not x_admin_password:
        raise HTTPException(status_code=401, detail="Admin password required")
    settings = load_settings()
    if not verify_admin_password(settings, x_admin_password):
        raise HTTPException(status_code=403, detail="Invalid admin password")

    settings["smtp"] = body.smtp.model_dump()
    save_settings(settings)
    return {"ok": True, "message": "Settings saved"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
