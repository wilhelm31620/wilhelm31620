"""JPG Rotator - Windows GUI.

Looks in an input folder for .jpg files modified in the last N days and writes a
copy rotated 90 degrees clockwise, with the same name, to an output folder.
Files that already exist in the output folder are skipped. The input folder is
re-checked every N seconds until Stop is pressed, and the log is also saved to
JpgRotator_log.txt in the output folder.
"""

import faulthandler
import json
import os
import queue
import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

import rotate_core

APP_NAME = "JPG Rotator"
DEFAULT_SETTINGS = {
    "input_dir": r"L:\ScanPdf",
    "output_dir": r"L:\ScanPdf-R",
    "days": 7,
    "interval_seconds": 60,
    "autorun": False,
}


def settings_path():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "JpgRotator", "settings.json")


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as f:
            settings.update(json.load(f))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings):
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass


def parse_int(text, minimum):
    try:
        value = int(str(text).strip())
    except ValueError:
        return None
    return value if value >= minimum else None


class RotatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("760x500")
        self.root.minsize(600, 380)

        self.ui_queue = queue.Queue()
        self.worker = None
        self.stop_event = threading.Event()

        settings = load_settings()
        self.input_var = tk.StringVar(value=settings["input_dir"])
        self.output_var = tk.StringVar(value=settings["output_dir"])
        self.days_var = tk.StringVar(value=str(settings["days"]))
        self.interval_var = tk.StringVar(value=str(settings["interval_seconds"]))
        self.autorun_var = tk.BooleanVar(value=bool(settings["autorun"]))
        self.status_var = tk.StringVar(value="Idle.")
        self.log_file = rotate_core.LogFile(settings["output_dir"])

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain_ui_queue)

        self.log(f"{APP_NAME} opened. Settings file: {settings_path()}")
        if self.autorun_var.get():
            self.log("Autorun is on - starting.")
            self.root.after(500, self.start)

    # ---------- UI ----------

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}
        frame = ttk.Frame(self.root, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Input folder:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Browse...", command=lambda: self._browse(self.input_var)).grid(
            row=0, column=2, **pad
        )

        ttk.Label(frame, text="Output folder:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frame, text="Browse...", command=lambda: self._browse(self.output_var)).grid(
            row=1, column=2, **pad
        )

        options = ttk.Frame(frame)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(options, text="Days to look back:").pack(side=tk.LEFT)
        ttk.Spinbox(options, from_=1, to=3650, width=6, textvariable=self.days_var).pack(
            side=tk.LEFT, padx=(6, 20)
        )
        ttk.Label(options, text="Seconds between checks (0 = once):").pack(side=tk.LEFT)
        ttk.Spinbox(options, from_=0, to=86400, width=7, textvariable=self.interval_var).pack(
            side=tk.LEFT, padx=(6, 20)
        )
        ttk.Checkbutton(
            options,
            text="Autorun when app opens",
            variable=self.autorun_var,
            command=self._save,
        ).pack(side=tk.LEFT)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        self.run_button = ttk.Button(buttons, text="Start", command=self.start)
        self.run_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Clear log", command=self.clear_log).pack(side=tk.RIGHT)

        ttk.Label(frame, text="Log:").grid(row=4, column=0, sticky="w", padx=6)
        self.log_box = scrolledtext.ScrolledText(frame, height=15, state=tk.DISABLED, wrap=tk.WORD)
        self.log_box.grid(row=5, column=0, columnspan=3, sticky="nsew", **pad)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w").grid(
            row=6, column=0, columnspan=3, sticky="ew", padx=6, pady=(4, 0)
        )

    def _browse(self, var):
        start = var.get() if os.path.isdir(var.get()) else None
        chosen = filedialog.askdirectory(initialdir=start)
        if chosen:
            var.set(os.path.normpath(chosen))
            self._save()

    # ---------- logging ----------

    def log(self, message):
        """Thread-safe: write a timestamped line to the log file and queue it for the log box."""
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        self.log_file.write(line)
        self.ui_queue.put(("log", line))

    def set_status(self, text):
        """Thread-safe: update the status bar."""
        self.ui_queue.put(("status", text))

    def _drain_ui_queue(self):
        lines = []
        while True:
            try:
                kind, text = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                lines.append(text)
            else:
                self.status_var.set(text)
        if lines:
            self.log_box.configure(state=tk.NORMAL)
            self.log_box.insert(tk.END, "\n".join(lines) + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state=tk.DISABLED)
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            self.run_button.configure(state=tk.NORMAL)
            self.stop_button.configure(state=tk.DISABLED)
            if self.stop_event.is_set():
                self.status_var.set("Stopped. " + self.status_var.get().split("  Next check")[0])
        self.root.after(100, self._drain_ui_queue)

    def clear_log(self):
        """Clears the on-screen log only; the log file is kept."""
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state=tk.DISABLED)

    # ---------- processing ----------

    def _save(self):
        days = parse_int(self.days_var.get(), 1)
        interval = parse_int(self.interval_var.get(), 0)
        save_settings(
            {
                "input_dir": self.input_var.get().strip(),
                "output_dir": self.output_var.get().strip(),
                "days": days if days is not None else DEFAULT_SETTINGS["days"],
                "interval_seconds": interval if interval is not None else DEFAULT_SETTINGS["interval_seconds"],
                "autorun": bool(self.autorun_var.get()),
            }
        )

    def start(self):
        if self.worker is not None:
            return
        input_dir = self.input_var.get().strip()
        output_dir = self.output_var.get().strip()
        days = parse_int(self.days_var.get(), 1)
        interval = parse_int(self.interval_var.get(), 0)
        if days is None:
            messagebox.showerror(APP_NAME, "Days to look back must be a whole number of 1 or more.")
            return
        if interval is None:
            messagebox.showerror(APP_NAME, "Seconds between checks must be a whole number of 0 or more.")
            return
        if not input_dir or not output_dir:
            messagebox.showerror(APP_NAME, "Please choose both an input and an output folder.")
            return
        if os.path.normcase(os.path.abspath(input_dir)) == os.path.normcase(os.path.abspath(output_dir)):
            messagebox.showerror(APP_NAME, "Input and output folders must be different.")
            return

        self._save()
        self.log_file.set_folder(output_dir)
        self.stop_event.clear()
        self.run_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.status_var.set("Checking...")
        self.worker = threading.Thread(
            target=rotate_core.watch,
            args=(input_dir, output_dir, days, interval, self.log, self.set_status, self.stop_event),
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_event.set()
        self.stop_button.configure(state=tk.DISABLED)

    def on_close(self):
        self._save()
        if self.worker is not None:
            self.stop_event.set()
            self.worker.join(timeout=5)
        self.log(f"{APP_NAME} closed.")
        self.root.destroy()


def self_test():
    """Used by the build to confirm the packaged exe starts: create and close a window, exit 0."""
    root = tk.Tk()
    root.withdraw()
    root.update()
    root.destroy()
    import PIL.Image  # noqa: F401  make sure Pillow is bundled
    sys.exit(0)


def crash_log_path():
    return os.path.join(os.path.dirname(settings_path()), "crash_log.txt")


def install_crash_logging():
    """Record any crash in crash_log.txt next to the settings file.

    The packaged exe has no console, so without this an unexpected error would make
    the program vanish without a trace.
    """
    path = crash_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        crash_file = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    crash_file.write(f"\n=== {APP_NAME} started {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
    faulthandler.enable(file=crash_file, all_threads=True)  # hard crashes

    def write_exception(title, exc_type, exc, tb):
        crash_file.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {title}\n")
        crash_file.write("".join(traceback.format_exception(exc_type, exc, tb)))

    sys.excepthook = lambda t, e, tb: write_exception("Unhandled error", t, e, tb)
    threading.excepthook = lambda a: write_exception(
        f"Unhandled error in thread {a.thread.name if a.thread else '?'}", a.exc_type, a.exc_value, a.exc_traceback
    )
    return write_exception


def main():
    if "--selftest" in sys.argv:
        self_test()
    write_exception = install_crash_logging()
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    app = RotatorApp(root)

    def report_callback_exception(exc_type, exc, tb):
        # An error in a button/timer handler: record it and keep the window open.
        if write_exception:
            write_exception("Error in window event", exc_type, exc, tb)
        app.log(f"ERROR: unexpected problem in the window: {exc!r} (details in {crash_log_path()})")

    root.report_callback_exception = report_callback_exception
    root.mainloop()


if __name__ == "__main__":
    main()
