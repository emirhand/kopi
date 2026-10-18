"""Health, hardware discovery, and USB storage endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from kopi.auth.dependencies import require_paired_client
from kopi.config import load_settings
from kopi.hardware import (
    get_hardware_lock,
    list_printer_queues,
    list_scan_devices,
    list_usb_volumes,
    mount_usb_partition,
)

router = APIRouter(prefix="/api", tags=["hardware"])


class UsbMountBody(BaseModel):
    device: str = Field(..., min_length=4, description="Block device e.g. /dev/sdb1")


@router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/hardware", dependencies=[Depends(require_paired_client)])
async def api_hardware() -> dict[str, Any]:
    lock = get_hardware_lock()
    return {
        "scanners": list_scan_devices(),
        "printers": list_printer_queues(),
        "usb_volumes": [v.to_dict() for v in list_usb_volumes()],
        "busy": lock.is_busy,
        "current_operation": lock.current_operation,
    }


@router.get("/settings/public")
async def api_settings_public() -> dict[str, bool]:
    settings = load_settings()
    return {"id_scan_ocr": bool(settings.id_scan_ocr)}


@router.post("/usb/mount", dependencies=[Depends(require_paired_client)])
async def api_usb_mount(body: UsbMountBody) -> dict[str, Any]:
    vols = list_usb_volumes()
    vol = next((v for v in vols if v.device == body.device.strip()), None)
    if vol is None:
        raise HTTPException(
            status_code=400,
            detail="Device not found. Plug in the USB drive, then open USB storage again.",
        )
    if vol.mounted and vol.mountpoint:
        return {
            "ok": True,
            "mountpoint": vol.mountpoint,
            "message": f"Already mounted at {vol.mountpoint}",
        }
    mp, err = mount_usb_partition(vol.device)
    if err or not mp:
        raise HTTPException(status_code=400, detail=err or "Mount failed")
    return {"ok": True, "mountpoint": mp, "message": f"Mounted at {mp}"}

