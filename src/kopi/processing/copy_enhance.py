"""Pure-Python Pillow image enhancements for HP OfficeJet Pro 9010 Copy settings."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance


def apply_copy_enhancements_to_image(
    img: Image.Image,
    *,
    lighter_darker: int = 0,
    content_type: str = "mixed",
    resize_mode: str = "actual",
    resize_percent: int = 100,
) -> Image.Image:
    """Apply HP 9010 Copy settings (Content Type, Lighter/Darker, and Custom/91% Resize) to a page."""
    out = img.copy()
    if out.mode not in ("RGB", "L"):
        out = out.convert("RGB")

    # 1. Content Type enhancement
    ctype = content_type.strip().lower()
    if ctype == "text":
        out = ImageEnhance.Contrast(out).enhance(1.25)
        out = ImageEnhance.Sharpness(out).enhance(1.5)
    elif ctype == "photo" and out.mode == "RGB":
        out = ImageEnhance.Color(out).enhance(1.12)

    # 2. Lighter / Darker (-4 = lightest, 0 = normal, +4 = darkest)
    clamped_ld = max(-4, min(4, int(lighter_darker)))
    if clamped_ld != 0:
        brightness_factor = 1.0 - (clamped_ld * 0.08)
        out = ImageEnhance.Brightness(out).enhance(brightness_factor)
        if clamped_ld > 0:
            contrast_factor = 1.0 + (clamped_ld * 0.05)
            out = ImageEnhance.Contrast(out).enhance(contrast_factor)

    # 3. Image-level Resize (Full Page 91% or Custom 25%..400%)
    rmode = resize_mode.strip().lower()
    scale = 1.0
    if rmode == "full_page_91":
        scale = 0.91
    elif rmode == "custom":
        clamped_pct = max(25, min(400, int(resize_percent)))
        scale = clamped_pct / 100.0

    if abs(scale - 1.0) > 1e-4:
        orig_w, orig_h = out.size
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))
        scaled = out.resize((new_w, new_h), Image.Resampling.LANCZOS)

        bg_color: tuple[int, int, int] | int = (255, 255, 255) if out.mode == "RGB" else 255
        canvas = Image.new(out.mode, (orig_w, orig_h), color=bg_color)
        offset_x = (orig_w - new_w) // 2
        offset_y = (orig_h - new_h) // 2
        canvas.paste(scaled, (offset_x, offset_y))
        out = canvas

    return out


def enhance_scanned_image_file(
    path: Path,
    *,
    lighter_darker: int = 0,
    content_type: str = "mixed",
    resize_mode: str = "actual",
    resize_percent: int = 100,
) -> None:
    """In-place enhancement of a scanned PNG file if any non-default image option is active."""
    needs_processing = (
        int(lighter_darker) != 0
        or content_type.strip().lower() != "mixed"
        or resize_mode.strip().lower() in ("full_page_91", "custom")
    )
    if not needs_processing or not path.is_file():
        return

    with Image.open(path) as src:
        enhanced = apply_copy_enhancements_to_image(
            src,
            lighter_darker=lighter_darker,
            content_type=content_type,
            resize_mode=resize_mode,
            resize_percent=resize_percent,
        )
        enhanced.save(path, format="PNG")
