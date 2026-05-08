"""Detect removable USB mounts under /media (typical desktop Linux)."""

from __future__ import annotations

import os
from pathlib import Path


def _default_roots() -> list[str]:
    raw = os.environ.get("KOPI_USB_ROOTS", "/media,/run/media,/Volumes")
    return [x.strip() for x in raw.split(",") if x.strip()]


def list_usb_mounts(roots: list[str] | None = None, writable_only: bool = False) -> list[str]:
    """List plausible mounted USB volume paths under configured roots."""
    candidates: list[Path] = []
    for root_str in (roots or _default_roots()):
        root = Path(root_str)
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir():
                candidates.append(child)
                try:
                    for sub in sorted(child.iterdir()):
                        if sub.is_dir():
                            candidates.append(sub)
                except OSError:
                    continue

    paths: list[str] = []
    for path in candidates:
        try:
            if not path.is_dir():
                continue
            if writable_only and not os.access(path, os.W_OK):
                continue
            paths.append(str(path))
        except OSError:
            continue
    return sorted(dict.fromkeys(paths))


def first_usb_mount(roots: list[str] | None = None) -> Path | None:
    """
    Return the first plausible writable mount under configured roots.
    Order is filesystem-dependent; first match is used.
    """
    writable = list_usb_mounts(roots=roots, writable_only=True)
    return Path(writable[0]) if writable else None


def require_usb_path(roots: list[str] | None = None) -> Path:
    p = first_usb_mount(roots)
    if p is None:
        raise FileNotFoundError("USB Not Found")
    return p
