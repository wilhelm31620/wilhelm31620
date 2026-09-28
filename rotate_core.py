"""Core logic: find recent JPGs and write 90-degree clockwise rotated copies."""

import os
import time
from datetime import datetime

from PIL import Image, ImageOps

JPG_EXTENSIONS = (".jpg", ".jpeg")
JPEG_QUALITY = 95


def find_recent_jpgs(input_dir, days):
    """Return (path, modified_time) for .jpg/.jpeg files in input_dir modified within `days` days.

    Only the top-level folder is scanned (no subfolders). Newest files come first.
    """
    cutoff = time.time() - days * 86400
    found = []
    with os.scandir(input_dir) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            if not entry.name.lower().endswith(JPG_EXTENSIONS):
                continue
            mtime = entry.stat().st_mtime
            if mtime >= cutoff:
                found.append((entry.path, mtime))
    found.sort(key=lambda item: item[1], reverse=True)
    return found


def rotate_jpg(src_path, dst_path):
    """Save a copy of src_path rotated 90 degrees clockwise to dst_path.

    Any EXIF orientation flag is applied first, so the output is rotated relative
    to how the image actually displays. The file is written to a temporary name
    and then renamed, so a half-written file is never left under the real name.
    """
    with Image.open(src_path) as img:
        img = ImageOps.exif_transpose(img)
        rotated = img.transpose(Image.Transpose.ROTATE_270)  # 270 counter-clockwise == 90 clockwise

        save_kwargs = {"quality": JPEG_QUALITY}
        if "dpi" in img.info:
            save_kwargs["dpi"] = img.info["dpi"]
        if img.info.get("icc_profile"):
            save_kwargs["icc_profile"] = img.info["icc_profile"]
        if rotated.mode not in ("RGB", "L", "CMYK"):
            rotated = rotated.convert("RGB")

        tmp_path = dst_path + ".tmp"
        try:
            rotated.save(tmp_path, "JPEG", **save_kwargs)
            os.replace(tmp_path, dst_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


def process(input_dir, output_dir, days, log, should_stop=lambda: False):
    """Rotate every recent JPG in input_dir into output_dir, skipping ones already done.

    `log` is called with one message string per action. Returns a summary dict.
    """
    summary = {"found": 0, "created": 0, "skipped": 0, "errors": 0}

    if not os.path.isdir(input_dir):
        log(f"ERROR: Input folder not found: {input_dir}")
        summary["errors"] += 1
        return summary

    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            log(f"Created output folder: {output_dir}")
        except OSError as exc:
            log(f"ERROR: Could not create output folder {output_dir}: {exc}")
            summary["errors"] += 1
            return summary

    log(f"Scanning {input_dir} for .jpg files from the last {days} day(s)...")
    try:
        files = find_recent_jpgs(input_dir, days)
    except OSError as exc:
        log(f"ERROR: Could not read input folder: {exc}")
        summary["errors"] += 1
        return summary

    summary["found"] = len(files)
    log(f"Found {len(files)} file(s).")

    for src_path, mtime in files:
        if should_stop():
            log("Stopped by user.")
            break
        name = os.path.basename(src_path)
        dst_path = os.path.join(output_dir, name)
        modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")

        if os.path.exists(dst_path):
            log(f"Skipped (already rotated): {name}")
            summary["skipped"] += 1
            continue

        try:
            rotate_jpg(src_path, dst_path)
            log(f"Created rotated file: {name}  (modified {modified})")
            summary["created"] += 1
        except Exception as exc:  # keep going with the other files
            log(f"ERROR rotating {name}: {exc}")
            summary["errors"] += 1

    log(
        "Done. Found {found}, created {created}, skipped {skipped}, errors {errors}.".format(**summary)
    )
    return summary
