"""Detect removable USB mounts under /media (typical desktop Linux)."""

from __future__ import annotations

import os
from pathlib import Path


def first_usb_mount(media_root: str = "/media") -> Path | None:
    """
    Return the first plausible user mount under /media or /media/$USER.
    Order is filesystem-dependent; first match is used.
    """
    root = Path(media_root)
    if not root.is_dir():
        return None

    candidates: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            candidates.append(child)
            # e.g. /media/username/DEVICE
            try:
                for sub in sorted(child.iterdir()):
                    if sub.is_dir():
                        candidates.append(sub)
            except OSError:
                continue

    for path in candidates:
        try:
            if path.is_dir() and os.access(path, os.W_OK):
                return path
        except OSError:
            continue
    return None


def require_usb_path(media_root: str = "/media") -> Path:
    p = first_usb_mount(media_root)
    if p is None:
        raise FileNotFoundError("USB Not Found")
    return p
