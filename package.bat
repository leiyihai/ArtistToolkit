@echo off
rem Package the GPUI build into dist-gpui\: Python backend exe + GPUI front end + models.
rem Electron packaging stays in build.bat; the two do not interfere.
cd /d "%~dp0"

echo [1/2] Building the Python backend exe...
python -m PyInstaller --noconfirm --clean ArtistToolkit-backend.spec
if errorlevel 1 goto failed

echo [2/2] Assembling dist-gpui...
powershell -NoProfile -ExecutionPolicy Bypass -File "ui\scripts\package.ps1" -WithModels
if errorlevel 1 goto failed

echo.
echo Done: dist-gpui\ArtistToolkit.exe (start.bat prefers it automatically)
pause
exit /b 0

:failed
echo Packaging failed.
pause
exit /b 1
