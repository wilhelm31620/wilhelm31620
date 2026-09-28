"""Core logic: find recent JPGs and write 90-degree clockwise rotated copies."""

import io
import os
import threading
import traceback
import time
from datetime import datetime, timedelta

from PIL import Image, ImageOps

JPG_EXTENSIONS = (".jpg", ".jpeg")
JPEG_QUALITY = 95
LOG_FILE_NAME = "JpgRotator_log.txt"
MAX_PENDING_LOG_LINES = 1000


class LogFile:
    """Appends log lines to LOG_FILE_NAME in a folder. Safe to call from any thread.

    If the folder can't be written yet (e.g. drive not connected), lines are kept in
    memory and written the next time a write succeeds.
    """

    def __init__(self, folder=None):
        self._lock = threading.Lock()
        self._pending = []
        self.folder = folder

    @property
    def path(self):
        return os.path.join(self.folder, LOG_FILE_NAME) if self.folder else None

    def set_folder(self, folder):
        with self._lock:
            self.folder = folder

    def write(self, line):
        with self._lock:
            self._pending.append(line)
            del self._pending[:-MAX_PENDING_LOG_LINES]
            if not self.folder or not os.path.isdir(self.folder):
                return
            try:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write("\n".join(self._pending) + "\n")
                self._pending.clear()
            except OSError:
                pass


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
    to how the image actually displays. The JPEG is built in memory and written in
    one go; if writing fails part way, the partial file is deleted. (No temp-file +
    rename, because some network/cloud drives refuse renames - WinError 17.)
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

        buffer = io.BytesIO()
        rotated.save(buffer, "JPEG", **save_kwargs)

    # "xb" = create only; never overwrites a file that already exists.
    with open(dst_path, "xb") as f:
        try:
            f.write(buffer.getvalue())
        except BaseException:
            f.close()
            os.remove(dst_path)
            raise


def new_state():
    """State carried between repeated checks so the same problem is not logged every time."""
    return {"failed": {}, "folder_problem": None}


def _folder_problem(state, message, log):
    if state["folder_problem"] != message:
        log(message)
        state["folder_problem"] = message


def process(input_dir, output_dir, days, log, should_stop=lambda: False, state=None):
    """Rotate every recent JPG in input_dir into output_dir, skipping ones already done.

    `log` is called once per file created or failed, plus a summary line when a
    check did something. Files already in output_dir are counted as skipped but not
    logged one by one, so repeated checks don't flood the log. A file that failed is
    not retried (or re-logged) until its modified time changes. Returns a summary dict.
    """
    if state is None:
        state = new_state()
    summary = {"found": 0, "created": 0, "skipped": 0, "errors": 0}

    if not os.path.isdir(input_dir):
        _folder_problem(state, f"ERROR: Input folder not found: {input_dir}", log)
        summary["errors"] += 1
        return summary

    if not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
            log(f"Created output folder: {output_dir}")
        except OSError as exc:
            _folder_problem(state, f"ERROR: Could not create output folder {output_dir}: {exc}", log)
            summary["errors"] += 1
            return summary

    try:
        files = find_recent_jpgs(input_dir, days)
    except OSError as exc:
        _folder_problem(state, f"ERROR: Could not read input folder: {exc}", log)
        summary["errors"] += 1
        return summary

    if state["folder_problem"]:
        log("Folders are available again.")
        state["folder_problem"] = None

    summary["found"] = len(files)
    new_errors = 0

    for src_path, mtime in files:
        if should_stop():
            break
        name = os.path.basename(src_path)
        dst_path = os.path.join(output_dir, name)

        if os.path.exists(dst_path):
            summary["skipped"] += 1
            continue

        if state["failed"].get(src_path) == mtime:
            summary["errors"] += 1  # failed before and unchanged since; don't retry or re-log
            continue

        try:
            rotate_jpg(src_path, dst_path)
            modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            log(f"Created rotated file: {name}  (modified {modified})")
            summary["created"] += 1
            state["failed"].pop(src_path, None)
        except Exception as exc:  # keep going with the other files
            log(f"ERROR rotating {name}: {exc}")
            summary["errors"] += 1
            new_errors += 1
            state["failed"][src_path] = mtime

    if summary["created"] or new_errors:
        log(
            "Check done. Found {found} file(s) from the last {days} day(s): created {created}, "
            "already rotated {skipped}, errors {errors}.".format(days=days, **summary)
        )
    return summary


def watch(input_dir, output_dir, days, interval_seconds, log, status, stop_event):
    """Check the input folder now, then every `interval_seconds` until stop_event is set.

    An interval of 0 means check once only. `status` is called with a short one-line
    description of the last check, for display (it is not logged).
    """
    if interval_seconds > 0:
        log(
            f"Started. Watching {input_dir} every {interval_seconds} s for .jpg files "
            f"from the last {days} day(s); output to {output_dir}."
        )
    else:
        log(f"Checking {input_dir} once for .jpg files from the last {days} day(s); output to {output_dir}.")

    state = new_state()
    while not stop_event.is_set():
        try:
            summary = process(input_dir, output_dir, days, log, stop_event.is_set, state)
        except Exception:
            log("ERROR: unexpected problem during check:\n" + traceback.format_exc().rstrip())
            summary = {"found": 0, "created": 0, "skipped": 0, "errors": 1}
        now = datetime.now()
        text = (
            "Last check {time}: found {found}, created {created}, already rotated {skipped}, "
            "errors {errors}.".format(time=now.strftime("%H:%M:%S"), **summary)
        )
        if interval_seconds <= 0:
            status(text)
            break
        next_check = now + timedelta(seconds=interval_seconds)
        status(f"{text}  Next check at {next_check.strftime('%H:%M:%S')}.")
        stop_event.wait(interval_seconds)

    log("Stopped." if stop_event.is_set() else "Finished.")
