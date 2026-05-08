"""Removable USB storage via lsblk + optional udisksctl mount."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("kopi.usb")


@dataclass(frozen=True)
class UsbVolume:
    """One partition or whole-disk USB volume."""

    device: str
    mountpoint: str | None
    label: str
    model: str
    mounted: bool

    def to_dict(self) -> dict:
        return {
            "device": self.device,
            "mountpoint": self.mountpoint,
            "label": self.label,
            "model": self.model,
            "mounted": self.mounted,
        }


def _lsblk_tree(timeout_sec: float = 12.0) -> list[dict]:
    try:
        proc = subprocess.run(
            [
                "lsblk",
                "-J",
                "-o",
                "PATH,NAME,TYPE,MOUNTPOINT,RM,TRAN,LABEL,MODEL",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("lsblk failed: %s", e)
        return []
    if proc.returncode != 0:
        log.warning("lsblk rc=%s stderr=%s", proc.returncode, (proc.stderr or "").strip())
        return []
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        log.warning("lsblk JSON parse error: %s", e)
        return []
    return list(data.get("blockdevices") or [])


def _device_path(node: dict) -> str:
    p = (node.get("path") or "").strip()
    if p.startswith("/dev/"):
        return p
    name = (node.get("name") or "").strip()
    return f"/dev/{name}" if name else ""


def _collect_usb_volumes(node: dict, under_usb: bool) -> list[UsbVolume]:
    out: list[UsbVolume] = []
    typ = (node.get("type") or "").lower()
    tran = (node.get("tran") or "").lower()
    path = _device_path(node)
    is_usb_disk = typ == "disk" and tran == "usb"
    in_usb_tree = under_usb or is_usb_disk

    mp = node.get("mountpoint")
    if mp in ("", None):
        mp = None
    else:
        mp = str(mp).strip() or None

    label = (node.get("label") or "").strip()
    model = (node.get("model") or "").strip()
    display_label = label or (Path(mp).name if mp else "") or (Path(path).name if path else "USB")

    if in_usb_tree and typ == "part" and path:
        out.append(
            UsbVolume(
                device=path,
                mountpoint=mp,
                label=display_label,
                model=model,
                mounted=mp is not None,
            )
        )

    if in_usb_tree and typ == "disk" and mp and path and is_usb_disk and not node.get("children"):
        out.append(
            UsbVolume(
                device=path,
                mountpoint=mp,
                label=display_label or model or path,
                model=model,
                mounted=True,
            )
        )

    for child in node.get("children") or []:
        if isinstance(child, dict):
            out.extend(_collect_usb_volumes(child, in_usb_tree))
    return out


def list_usb_volumes() -> list[UsbVolume]:
    """Volumes on USB-attached block devices (lsblk), not arbitrary /media folders."""
    volumes: list[UsbVolume] = []
    for root in _lsblk_tree():
        volumes.extend(_collect_usb_volumes(root, under_usb=False))
    seen: set[tuple[str, str | None]] = set()
    unique: list[UsbVolume] = []
    for v in volumes:
        key = (v.device, v.mountpoint)
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return sorted(unique, key=lambda x: (x.mounted, x.mountpoint or "", x.device))


def mount_usb_partition(device: str, timeout_sec: float = 45.0) -> tuple[str | None, str]:
    """
    Mount a USB partition using udisksctl (typical desktop Linux).
    Returns (mountpoint or None, error_message).
    """
    dev = device.strip()
    if not dev.startswith("/dev/") or ".." in dev:
        return None, "Invalid device path"

    try:
        proc = subprocess.run(
            ["udisksctl", "mount", "-b", dev, "--no-user-interaction"],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError:
        return None, "udisksctl not found; install udisks2 or mount the drive manually"
    except subprocess.SubprocessError as e:
        return None, str(e)

    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0:
        return None, combined or f"mount failed (exit {proc.returncode})"

    m = re.search(r"\bat\s+(\S+)", combined)
    if m:
        return m.group(1).strip(), ""

    return None, combined or "Mounted but could not parse mount path"


def _real(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return os.path.realpath(path)


def resolve_writable_usb_mount(
    mount_path: str | None,
    *,
    volumes: list[UsbVolume] | None = None,
) -> Path:
    """
    Validate ``mount_path`` is the realpath of a currently mounted USB volume
    from list_usb_volumes(), and is writable.
    """
    vols = volumes if volumes is not None else list_usb_volumes()
    if not mount_path or not str(mount_path).strip():
        for v in vols:
            if v.mounted and v.mountpoint and os.access(v.mountpoint, os.W_OK):
                return Path(v.mountpoint)
        raise FileNotFoundError("No USB volume selected or available")

    want = _real(str(mount_path).strip())
    for v in vols:
        if not v.mounted or not v.mountpoint:
            continue
        if _real(v.mountpoint) != want:
            continue
        if os.path.isdir(v.mountpoint) and os.access(v.mountpoint, os.W_OK):
            return Path(v.mountpoint)
        raise PermissionError(f"USB mount not writable: {v.mountpoint}")

    raise FileNotFoundError("USB mount path is not a detected removable USB volume")


def first_usb_mount(roots: list[str] | None = None) -> Path | None:
    """First writable mounted USB volume (ignores legacy ``roots``)."""
    _ = roots
    try:
        return resolve_writable_usb_mount(None)
    except (FileNotFoundError, PermissionError):
        return None


def require_usb_path(roots: list[str] | None = None) -> Path:
    p = first_usb_mount(roots)
    if p is None:
        raise FileNotFoundError("USB Not Found")
    return p


def list_usb_mounts(roots: list[str] | None = None, writable_only: bool = False) -> list[str]:
    """
    Back-compat: mountpoint paths only (real USB). ``roots`` ignored.
    """
    _ = roots
    paths: list[str] = []
    for v in list_usb_volumes():
        if not v.mounted or not v.mountpoint:
            continue
        if writable_only and not os.access(v.mountpoint, os.W_OK):
            continue
        paths.append(v.mountpoint)
    return sorted(dict.fromkeys(paths))
