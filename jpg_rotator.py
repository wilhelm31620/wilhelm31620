"""JPG Rotator - Windows GUI.

Looks in an input folder for .jpg files modified in the last N days and writes a
copy rotated 90 degrees clockwise, with the same name, to an output folder.
Files that already exist in the output folder are skipped.
"""

import json
import os
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

import rotate_core

APP_NAME = "JPG Rotator"
DEFAULT_SETTINGS = {
    "input_dir": r"L:\ScanPdf",
    "output_dir": r"L:\ScanPdf-R",
    "days": 7,
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


class RotatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("720x480")
        self.root.minsize(560, 360)

        self.log_queue = queue.Queue()
        self.worker = None
        self.stop_requested = False

        settings = load_settings()
        self.input_var = tk.StringVar(value=settings["input_dir"])
        self.output_var = tk.StringVar(value=settings["output_dir"])
        self.days_var = tk.StringVar(value=str(settings["days"]))
        self.autorun_var = tk.BooleanVar(value=bool(settings["autorun"]))

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._drain_log_queue)

        self.log(f"{APP_NAME} started. Settings file: {settings_path()}")
        if self.autorun_var.get():
            self.log("Autorun is on - starting processing.")
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
        ttk.Checkbutton(
            options,
            text="Autorun (start processing when the app opens)",
            variable=self.autorun_var,
            command=self._save,
        ).pack(side=tk.LEFT)

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        self.run_button = ttk.Button(buttons, text="Run", command=self.start)
        self.run_button.pack(side=tk.LEFT)
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=6)
        ttk.Button(buttons, text="Clear log", command=self.clear_log).pack(side=tk.RIGHT)

        ttk.Label(frame, text="Log:").grid(row=4, column=0, sticky="w", padx=6)
        self.log_box = scrolledtext.ScrolledText(frame, height=15, state=tk.DISABLED, wrap=tk.WORD)
        self.log_box.grid(row=5, column=0, columnspan=3, sticky="nsew", **pad)
        frame.rowconfigure(5, weight=1)

    def _browse(self, var):
        start = var.get() if os.path.isdir(var.get()) else None
        chosen = filedialog.askdirectory(initialdir=start)
        if chosen:
            var.set(os.path.normpath(chosen))
            self._save()

    # ---------- logging ----------

    def log(self, message):
        """Thread-safe: queue a message for the log box."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_queue.put(f"[{stamp}] {message}")

    def _drain_log_queue(self):
        lines = []
        while True:
            try:
                lines.append(self.log_queue.get_nowait())
            except queue.Empty:
                break
        if lines:
            self.log_box.configure(state=tk.NORMAL)
            self.log_box.insert(tk.END, "\n".join(lines) + "\n")
            self.log_box.see(tk.END)
            self.log_box.configure(state=tk.DISABLED)
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            self.run_button.configure(state=tk.NORMAL)
            self.stop_button.configure(state=tk.DISABLED)
        self.root.after(100, self._drain_log_queue)

    def clear_log(self):
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.configure(state=tk.DISABLED)

    # ---------- processing ----------

    def _read_days(self):
        try:
            days = int(self.days_var.get())
            if days < 1:
                raise ValueError
            return days
        except ValueError:
            return None

    def _save(self):
        days = self._read_days()
        save_settings(
            {
                "input_dir": self.input_var.get().strip(),
                "output_dir": self.output_var.get().strip(),
                "days": days if days is not None else DEFAULT_SETTINGS["days"],
                "autorun": bool(self.autorun_var.get()),
            }
        )

    def start(self):
        if self.worker is not None:
            return
        input_dir = self.input_var.get().strip()
        output_dir = self.output_var.get().strip()
        days = self._read_days()
        if days is None:
            messagebox.showerror(APP_NAME, "Days to look back must be a whole number of 1 or more.")
            return
        if not input_dir or not output_dir:
            messagebox.showerror(APP_NAME, "Please choose both an input and an output folder.")
            return
        if os.path.normcase(os.path.abspath(input_dir)) == os.path.normcase(os.path.abspath(output_dir)):
            messagebox.showerror(APP_NAME, "Input and output folders must be different.")
            return

        self._save()
        self.stop_requested = False
        self.run_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.worker = threading.Thread(
            target=rotate_core.process,
            args=(input_dir, output_dir, days, self.log, lambda: self.stop_requested),
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_requested = True
        self.log("Stop requested - finishing current file...")

    def on_close(self):
        self._save()
        self.root.destroy()


def main():
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    RotatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
