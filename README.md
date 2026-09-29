# JPG Rotator

A simple Windows program that looks in an input folder (default `L:\ScanPdf`) for `.jpg` / `.jpeg` / `.png` files
modified in the last N days (default 7). For each one whose name is **numbers only** (e.g. `82008.jpg`; not
`Scan 092350.jpg` or `82008_1.jpg`) it saves a copy rotated **90° clockwise**, with the same name, into an output folder
(default `L:\ScanPdf-R`).

- If the rotated copy already exists and the input file is **not newer** than it, the file is skipped.
- If the input file **is newer** than the existing rotated copy (a new scan with the same name), the old rotated copy
  is renamed to `82008_1.jpg` (or `_2`, `_3`, ... whichever is the next unused number) and the new rotated image is
  saved as `82008.jpg`. If the drive refuses renames, the old copy is copied to the new name and then deleted.
  Note: Windows keeps a file's modified date when copying, so an older file copied into the input folder is not
  treated as new.
- PNG files get a PNG rotated copy (lossless, transparency kept); JPGs get a JPG copy (quality 95).
- Images whose names aren't numbers only are ignored (counted in the status bar, not logged).
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
