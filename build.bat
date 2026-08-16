@echo off
rem 一键打包 Artist Toolkit 分发版
rem   1) Python 聚合后端 -> dist\ArtistToolkit-backend.exe
rem   2) Electron 免安装版 -> dist-electron\ArtistToolkit-win32-x64\ArtistToolkit.exe
cd /d "%~dp0"

echo [1/2] 打包 Python 后端...
python -m PyInstaller --noconfirm --clean ArtistToolkit-backend.spec
if errorlevel 1 (echo 后端打包失败 & pause & exit /b 1)

echo [2/2] 打包 Electron 应用...
cd app
call npx electron-packager . ArtistToolkit --platform=win32 --arch=x64 --out=..\dist-electron --overwrite --extra-resource ..\dist\ArtistToolkit-backend.exe
cd ..
if errorlevel 1 (echo Electron 打包失败 & pause & exit /b 1)

echo.
echo 完成: dist-electron\ArtistToolkit-win32-x64\ArtistToolkit.exe(双击运行,内置后端引擎)
pause
