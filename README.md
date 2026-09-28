# JPG Rotator

A simple Windows program that looks in an input folder (default `L:\ScanPdf`) for `.jpg` / `.jpeg` files
modified in the last N days (default 7). For each one it saves a copy rotated **90° clockwise**, with the same name,
into an output folder (default `L:\ScanPdf-R`).

- If a file with the same name already exists in the output folder, it is **skipped**, so existing rotated files are never overwritten.
- **Seconds between checks** (default 60): after pressing Start, the input folder is re-checked this often until you press Stop.
  Set it to 0 to check just once.
- Each file created and each error is shown in the log area with a timestamp, and also appended to
  `JpgRotator_log.txt` in the output folder. Files already rotated are counted rather than listed one by one, so
  repeated checks don't flood the log. The status bar at the bottom shows the result of the last check and when the next one is due.
- A file that fails to rotate is logged once, then retried only when the file changes (e.g. once the scanner finishes writing it).
- **Autorun** tick box: when ticked, checking starts automatically each time the program is opened.
- Folders, days, seconds and the autorun setting are remembered in `%APPDATA%\JpgRotator\settings.json`.
- Only the top level of the input folder is scanned (not subfolders).

## Run from source
1. Install Python 3 from python.org (tick "Add python.exe to PATH").
2. `pip install -r requirements.txt`
3. Double-click `jpg_rotator.py`, or run `python jpg_rotator.py`.

## Build a standalone .exe
Double-click `build_exe.bat`. It creates the folder `dist\JpgRotator\` containing `JpgRotator.exe` and an `_internal`
folder. Copy the **whole folder** to wherever you want it (for example `E:\working\JPG Rotate`). The two must stay
together. It runs on PCs without Python.

A ready-built copy is also produced by GitHub Actions on every push (the **JpgRotator** download on the Actions run page).

The folder layout is used instead of a single-file exe because single-file exes unpack themselves to `%TEMP%` at
startup, which antivirus or security policies often block ("Failed to start embedded python interpreter!").

## Run at Windows login (optional)
Press `Win+R`, type `shell:startup`, and put a shortcut to `JpgRotator.exe` in that folder. With Autorun ticked,
the program will then process new scans every time you log in.
