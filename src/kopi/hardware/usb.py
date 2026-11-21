"""Removable USB storage discovery and mounting via lsblk + udisksctl."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("kopi.usb")

_EXCLUDED_FSTYPES: frozenset[str] = frozenset(
    {
        "swap",
        "squashfs",
        "iso9660",
        "udf",
        "crypto_luks",
        "lvm2_member",
        "linux_raid_member",
        "zfs_member",
    }
)

_SYSTEM_MOUNT_PREFIXES: tuple[str, ...] = (
    "/boot",
    "/etc",
    "/usr",
    "/var",
    "/proc",
    "/sys",
    "/dev",
)

_SYSTEM_EXACT_MOUNTS: frozenset[str] = frozenset(
    {
        "/",
        "/home",
        "/root",
        "/opt",
        "/srv",
        "/tmp",
        "[swap]",
    }
)

_PRINTER_MODEL_KEYWORDS: tuple[str, ...] = (
    "officejet",
    "laserjet",
    "deskjet",
    "photosmart",
    "envy",
    "pagewide",
    "scanjet",
)


@dataclass(frozen=True)
class UsbVolume:
    """One partition or whole-disk removable USB mass-storage volume."""

    device: str
    mountpoint: str | None
    label: str
    model: str
    mounted: bool
    fstype: str = ""
    size: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device": self.device,
            "mountpoint": self.mountpoint,
            "label": self.label,
            "model": self.model,
            "mounted": self.mounted,
            "fstype": self.fstype,
            "size": self.size,
        }


def _format_size(raw_size: Any) -> str:
    if raw_size is None or raw_size == "":
        return ""
    if isinstance(raw_size, (int, float)):
        num = float(raw_size)
    else:
        s = str(raw_size).strip()
        if not s or s in ("0", "0B"):
            return ""
        if not s.isdigit():
            return s
        num = float(int(s))
    if num <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0 or unit == "TB":
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return ""


def _is_zero_size(raw_size: Any) -> bool:
    if raw_size is None:
        return False
    if isinstance(raw_size, (int, float)):
        return raw_size <= 0
    s = str(raw_size).strip().upper()
    return s in ("0", "0B", "0.0B")


def _is_truthy_flag(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes")
    return False


def _is_system_mountpoint(mp: str | None) -> bool:
    if not mp:
        return False
    norm = mp.strip().lower()
    if norm in _SYSTEM_EXACT_MOUNTS:
        return True
    return any(norm == p or norm.startswith(p + "/") for p in _SYSTEM_MOUNT_PREFIXES)


def _lsblk_tree(timeout_sec: float = 12.0) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            [
                "lsblk",
                "-J",
                "-b",
                "-o",
                "PATH,NAME,TYPE,MOUNTPOINT,RM,RO,TRAN,FSTYPE,LABEL,MODEL,SIZE,SUBSYSTEMS",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("lsblk failed: %s", e)
        return []
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return []
    raw_devices = data.get("blockdevices")
    if not isinstance(raw_devices, list):
        return []
    return [d for d in raw_devices if isinstance(d, dict)]


def _device_path(node: dict[str, Any]) -> str:
    p = str(node.get("path") or "").strip()
    if p.startswith("/dev/"):
        return p
    name = str(node.get("name") or "").strip()
    return f"/dev/{name}" if name else ""


def _collect_usb_volumes(
    node: dict[str, Any],
    *,
    under_usb: bool,
    parent_model: str = "",
) -> list[UsbVolume]:
    out: list[UsbVolume] = []
    typ = str(node.get("type") or "").strip().lower()
    tran = str(node.get("tran") or "").strip().lower()
    subsystems = str(node.get("subsystems") or "").strip().lower()
    path = _device_path(node)

    is_usb_disk = typ == "disk" and (tran == "usb" or "usb" in subsystems)
    in_usb_tree = under_usb or is_usb_disk

    model = str(node.get("model") or "").strip() or parent_model
    ro = _is_truthy_flag(node.get("ro"))
    raw_size = node.get("size")

    # Exclude optical/ROM drives, loop devices, read-only devices, and 0-byte stub LUNs
    if typ in ("rom", "loop", "lvm", "crypt", "ram", "zram"):
        return []
    if ro or _is_zero_size(raw_size):
        return []

    raw_mp = node.get("mountpoint")
    mp = str(raw_mp).strip() if raw_mp not in ("", None) else None
    if not mp:
        mp = None

    if _is_system_mountpoint(mp):
        return []

    has_fstype_key = "fstype" in node
    fstype = str(node.get("fstype") or "").strip().lower()
    if fstype in _EXCLUDED_FSTYPES:
        return []

    # Exclude printer stub LUNs unless there is an actual formatted filesystem
    if any(kw in model.lower() for kw in _PRINTER_MODEL_KEYWORDS) and not fstype:
        return []

    label = str(node.get("label") or "").strip()
    display_label = (
        label
        or (Path(mp).name if mp else "")
        or model
        or (Path(path).name if path else "USB Drive")
    )
    size_str = _format_size(raw_size)

    children = node.get("children")
    has_children = isinstance(children, list) and len(children) > 0

    if in_usb_tree and typ == "part" and path:
        # If lsblk provided fstype metadata, require a valid filesystem on the partition
        if not has_fstype_key or fstype or mp:
            out.append(
                UsbVolume(
                    device=path,
                    mountpoint=mp,
                    label=display_label,
                    model=model,
                    mounted=mp is not None,
                    fstype=fstype,
                    size=size_str,
                )
            )

    if in_usb_tree and typ == "disk" and path and is_usb_disk and not has_children:
        # Whole-disk filesystem (superfloppy USB stick) — must either be mounted or have a filesystem
        if mp or fstype:
            out.append(
                UsbVolume(
                    device=path,
                    mountpoint=mp,
                    label=display_label,
                    model=model,
                    mounted=mp is not None,
                    fstype=fstype,
                    size=size_str,
                )
            )

    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                out.extend(
                    _collect_usb_volumes(
                        child,
                        under_usb=in_usb_tree,
                        parent_model=model,
                    )
                )
    return out


def parse_usb_volumes_from_lsblk(raw_devices: list[dict[str, Any]]) -> list[UsbVolume]:
    """Parse and filter lsblk JSON tree into genuine removable USB storage volumes."""
    volumes: list[UsbVolume] = []
    for root in raw_devices:
        if isinstance(root, dict):
            volumes.extend(_collect_usb_volumes(root, under_usb=False))
    seen: set[tuple[str, str | None]] = set()
    unique: list[UsbVolume] = []
    for v in volumes:
        key = (v.device, v.mountpoint)
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)
    return sorted(unique, key=lambda x: (not x.mounted, x.mountpoint or "", x.device))


def list_usb_volumes() -> list[UsbVolume]:
    """Return volumes on removable USB mass-storage block devices."""
    mock_dir = os.environ.get("KOPI_MOCK_USB_DIR", "").strip()
    if mock_dir:
        return [
            UsbVolume(
                device="/dev/mock-usb1",
                mountpoint=mock_dir,
                label=Path(mock_dir).name or "MOCK_USB",
                model="Mock USB Flash Drive",
                mounted=True,
                fstype="vfat",
                size="16.0 GB",
            )
        ]

    return parse_usb_volumes_from_lsblk(_lsblk_tree())


def mount_usb_partition(device: str, timeout_sec: float = 45.0) -> tuple[str | None, str]:
    """Mount a USB partition using udisksctl."""
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
        return m.group(1).strip().rstrip("."), ""

    return None, combined or "Mounted but could not parse mount path"


def _real(path: str) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return os.path.realpath(path)


def resolve_writable_usb_mount(
    mount_path: str | None,
    *,
    device: str | None = None,
    volumes: list[UsbVolume] | None = None,
) -> Path:
    """Validate and resolve a mounted, writable USB volume by device or mount_path."""
    vols = volumes if volumes is not None else list_usb_volumes()

    if device and device.strip():
        want_dev = device.strip()
        vol = next((v for v in vols if v.device == want_dev), None)
        if vol is None:
            raise FileNotFoundError(f"Selected USB drive {want_dev} not found")
        mp = vol.mountpoint
        if not vol.mounted or not mp:
            mounted_mp, err = mount_usb_partition(vol.device)
            if err or not mounted_mp:
                raise PermissionError(err or f"Could not mount USB drive {vol.device}")
            mp = mounted_mp
        if os.path.isdir(mp) and os.access(mp, os.W_OK):
            return Path(mp)
        raise PermissionError(f"USB mount not writable: {mp}")

    if not mount_path or not str(mount_path).strip():
        for v in vols:
            if v.mounted and v.mountpoint and os.access(v.mountpoint, os.W_OK):
                return Path(v.mountpoint)
        raise FileNotFoundError("No USB storage drive selected or available")

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
