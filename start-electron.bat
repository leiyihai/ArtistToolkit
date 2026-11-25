@echo off
chcp 65001 >nul
rem 启动 Artist Toolkit 的 Electron 版(旧界面,保留用于对照/回退)。
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
