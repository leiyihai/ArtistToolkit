@echo off
rem Artist Toolkit launcher (Rust/GPUI front end).
rem The old Electron UI is still available: start-electron.bat
cd /d "%~dp0"

if exist "dist-gpui\ArtistToolkit.exe" goto packaged
if exist "ui\target\release\artist-toolkit-ui.exe" goto release
if exist "ui\target\debug\artist-toolkit-ui.exe" goto debug

echo [ArtistToolkit] No GPUI build found, building release (needs Rust, 3-8 min)...
where cargo >nul 2>nul
if errorlevel 1 goto nocargo
cargo build --release --manifest-path ui\Cargo.toml
if errorlevel 1 goto buildfail
goto release

:packaged
start "" "dist-gpui\ArtistToolkit.exe"
exit /b 0

:release
start "" "ui\target\release\artist-toolkit-ui.exe"
exit /b 0

:debug
start "" "ui\target\debug\artist-toolkit-ui.exe"
exit /b 0

:nocargo
echo [ArtistToolkit] cargo not found. Install Rust: https://rustup.rs
goto fallback

:buildfail
echo [ArtistToolkit] GPUI build failed.

:fallback
echo [ArtistToolkit] Falling back to the Electron UI...
call "%~dp0start-electron.bat"
exit /b 1
