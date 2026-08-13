@echo off
rem Start Artist Toolkit - Electron UI
cd /d "%~dp0app"
if not exist node_modules\electron\dist\electron.exe (
    echo Electron not found, installing dependencies. First run needs network...
    call npm install
    if errorlevel 1 (
        echo Install failed. Check your network and retry.
        pause
        exit /b 1
    )
)
npm start
