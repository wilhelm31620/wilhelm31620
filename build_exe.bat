@echo off
REM Builds a single JpgRotator.exe in the dist folder (no Python needed on the target PC).
python -m pip install --upgrade pillow pyinstaller
python -m PyInstaller --onefile --windowed --name JpgRotator jpg_rotator.py
echo.
echo Done. The program is dist\JpgRotator.exe
pause
