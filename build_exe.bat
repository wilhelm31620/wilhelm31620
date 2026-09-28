@echo off
REM Builds dist\JpgRotator\ (JpgRotator.exe plus its _internal folder; no Python needed on the target PC).
REM Keep the exe and the _internal folder together when copying.
python -m pip install --upgrade pillow pyinstaller
python -m PyInstaller --noconfirm --onedir --windowed --name JpgRotator jpg_rotator.py
echo.
echo Done. Copy the whole dist\JpgRotator folder; run JpgRotator.exe inside it.
pause
