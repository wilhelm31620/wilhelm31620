"""Core logic: find recent JPGs and write 90-degree clockwise rotated copies."""

import io
import os
import re
import shutil
import threading
import traceback
import time
from datetime import datetime, timedelta

from PIL import Image, ImageOps

JPG_EXTENSIONS = (".jpg", ".jpeg")
JPEG_QUALITY = 95
LOG_FILE_NAME = "JpgRotator_log.txt"
MAX_PENDING_LOG_LINES = 1000
# An input counts as a new version only if it is this much newer than its rotated copy
# (allows for drives that store times coarsely, e.g. to 2 seconds).
MTIME_TOLERANCE_SECONDS = 2


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


def is_numeric_name(file_name):
    """True for names like '82008.jpg': the part before the extension is digits 0-9 only."""
    return re.fullmatch(r"[0-9]+", os.path.splitext(file_name)[0]) is not None


def find_recent_jpgs(input_dir, days):
    """Find .jpg/.jpeg files in input_dir modified within `days` days.

    Returns (found, ignored): `found` is a list of (path, modified_time) for files
    whose name is numbers only, newest first; `ignored` is how many other recent
    JPGs were left out because their name isn't numbers only.
    Only the top-level folder is scanned (no subfolders).
    """
    cutoff = time.time() - days * 86400
    found = []
    ignored = 0
    with os.scandir(input_dir) as entries:
        for entry in entries:
            if not entry.is_file():
                continue
            if not entry.name.lower().endswith(JPG_EXTENSIONS):
                continue
            mtime = entry.stat().st_mtime
            if mtime < cutoff:
                continue
            if is_numeric_name(entry.name):
                found.append((entry.path, mtime))
            else:
                ignored += 1
    found.sort(key=lambda item: item[1], reverse=True)
    return found, ignored


def next_free_name(path):
    """For L:\\out\\82008.jpg return L:\\out\\82008_N.jpg with the lowest N >= 1 not yet used."""
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{stem}_{n}{ext}"):
        n += 1
    return f"{stem}_{n}{ext}"


def move_file(src, dst):
    """Rename src to dst (dst must not exist). If the drive refuses renames, copy then delete."""
    if os.path.exists(dst):
        raise FileExistsError(f"{dst} already exists")
    try:
        os.rename(src, dst)
        return
    except OSError:
        pass
    shutil.copy2(src, dst)  # keeps the modified date
    try:
        os.remove(src)
    except OSError:
        os.remove(dst)  # undo the copy so we don't leave two copies behind
        raise


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

    # The rotated copy must never look older than its input, otherwise (e.g. if the
    # scanner's clock is ahead) the input would keep looking like a new version.
    src_mtime = os.path.getmtime(src_path)
    if src_mtime > os.path.getmtime(dst_path):
        try:
            os.utime(dst_path, (src_mtime, src_mtime))
        except OSError:
            pass


def new_state():
    """State carried between repeated checks so the same problem is not logged every time."""
    # failed: {input path: modified time} that failed; done: {input path: modified time} rotated this session
    return {"failed": {}, "done": {}, "folder_problem": None}


def _folder_problem(state, message, log):
    if state["folder_problem"] != message:
        log(message)
        state["folder_problem"] = message


def process(input_dir, output_dir, days, log, should_stop=lambda: False, state=None):
    """Rotate every recent numbers-only-named JPG in input_dir into output_dir.

    - No rotated copy yet: create it.
    - Rotated copy exists and the input is newer than it (a new scan with the same
      name): rename the old rotated copy to name_1.jpg (name_2.jpg, ... if taken)
      and create the new rotated copy under the original name.
    - Otherwise it's already done: skip.

    `log` is called once per file created, renamed or failed, plus a summary line
    when a check did something. Skipped and ignored files are only counted, so
    repeated checks don't flood the log. A file that failed is not retried (or
    re-logged) until its modified time changes. Returns a summary dict.
    """
    if state is None:
        state = new_state()
    summary = {"found": 0, "created": 0, "replaced": 0, "skipped": 0, "ignored": 0, "errors": 0}

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
        files, summary["ignored"] = find_recent_jpgs(input_dir, days)
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

        if state["failed"].get(src_path) == mtime:
            summary["errors"] += 1  # failed before and unchanged since; don't retry or re-log
            continue

        try:
            is_new_version = False
            if os.path.exists(dst_path):
                already_done = state["done"].get(src_path) == mtime
                if already_done or mtime <= os.path.getmtime(dst_path) + MTIME_TOLERANCE_SECONDS:
                    summary["skipped"] += 1
                    continue
                is_new_version = True
        except OSError as exc:
            log(f"ERROR checking {name}: {exc}")
            summary["errors"] += 1
            new_errors += 1
            state["failed"][src_path] = mtime
            continue

        modified = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        old_copy = None
        try:
            if is_new_version:
                old_copy = next_free_name(dst_path)
                try:
                    move_file(dst_path, old_copy)
                except Exception as exc:
                    raise RuntimeError(
                        f"a newer {name} arrived but the old rotated copy could not be renamed to "
                        f"{os.path.basename(old_copy)}, so nothing was changed: {exc}"
                    ) from exc
                log(f"Newer {name} found (modified {modified}). Renamed old rotated {name} -> {os.path.basename(old_copy)}")
            try:
                rotate_jpg(src_path, dst_path)
            except Exception:
                if old_copy and not os.path.exists(dst_path):
                    try:  # put the old rotated copy back under its original name
                        move_file(old_copy, dst_path)
                        log(f"Put old rotated {os.path.basename(old_copy)} back as {name}")
                    except Exception as undo_exc:
                        log(f"ERROR: could not rename {os.path.basename(old_copy)} back to {name}: {undo_exc}")
                raise
            log(f"Created rotated file: {name}  (modified {modified})")
            summary["replaced" if is_new_version else "created"] += 1
            state["failed"].pop(src_path, None)
            state["done"][src_path] = mtime
        except Exception as exc:  # keep going with the other files
            log(f"ERROR rotating {name}: {exc}")
            summary["errors"] += 1
            new_errors += 1
            state["failed"][src_path] = mtime

    if summary["created"] or summary["replaced"] or new_errors:
        log(
            "Check done. Found {found} numbered file(s) from the last {days} day(s): created {created}, "
            "new versions {replaced}, already rotated {skipped}, errors {errors}; "
            "{ignored} other .jpg file(s) ignored (name not numbers only).".format(days=days, **summary)
        )
    return summary


def watch(input_dir, output_dir, days, interval_seconds, log, status, stop_event):
    """Check the input folder now, then every `interval_seconds` until stop_event is set.

    An interval of 0 means check once only. `status` is called with a short one-line
    description of the last check, for display (it is not logged).
    """
    if interval_seconds > 0:
        log(
            f"Started. Watching {input_dir} every {interval_seconds} s for numbered .jpg files "
            f"(e.g. 82008.jpg) from the last {days} day(s); output to {output_dir}."
        )
    else:
        log(f"Checking {input_dir} once for numbered .jpg files from the last {days} day(s); output to {output_dir}.")

    state = new_state()
    while not stop_event.is_set():
        try:
            summary = process(input_dir, output_dir, days, log, stop_event.is_set, state)
        except Exception:
            log("ERROR: unexpected problem during check:\n" + traceback.format_exc().rstrip())
            summary = {"found": 0, "created": 0, "replaced": 0, "skipped": 0, "ignored": 0, "errors": 1}
        now = datetime.now()
        text = (
            "Last check {time}: found {found}, created {created}, new versions {replaced}, "
            "already rotated {skipped}, errors {errors}, ignored (not numbers) {ignored}.".format(time=now.strftime("%H:%M:%S"), **summary)
        )
        if interval_seconds <= 0:
            status(text)
            break
        next_check = now + timedelta(seconds=interval_seconds)
        status(f"{text}  Next check at {next_check.strftime('%H:%M:%S')}.")
        stop_event.wait(interval_seconds)

    log("Stopped." if stop_event.is_set() else "Finished.")
