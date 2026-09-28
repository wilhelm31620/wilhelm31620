# JPG Rotator

A simple Windows program that looks in an input folder (default `L:\ScanPdf`) for `.jpg` / `.jpeg` files
modified in the last N days (default 7). For each one it saves a copy rotated **90° clockwise**, with the same name,
into an output folder (default `L:\ScanPdf-R`).

- If a file with the same name already exists in the output folder, it is **skipped**, so existing rotated files are never overwritten.
- Every action is shown in the log area with a timestamp, and each run ends with a summary.
- **Autorun** tick box: when ticked, processing starts automatically each time the program is opened.
- Folders, days and the autorun setting are remembered in `%APPDATA%\JpgRotator\settings.json`.
- Only the top level of the input folder is scanned (not subfolders).

## Run from source
1. Install Python 3 from python.org (tick "Add python.exe to PATH").
2. `pip install -r requirements.txt`
3. Double-click `jpg_rotator.py`, or run `python jpg_rotator.py`.

## Build a standalone .exe
Double-click `build_exe.bat`. The program is created at `dist\JpgRotator.exe`, and it runs on PCs without Python.

## Run at Windows login (optional)
Press `Win+R`, type `shell:startup`, and put a shortcut to `JpgRotator.exe` in that folder. With Autorun ticked,
the program will then process new scans every time you log in.
