@echo off
rem 打包 ArtistToolkit 为单文件 exe(使用 ArtistToolkit.spec,已排除无关重库)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean ArtistToolkit.spec
echo.
echo 完成: dist\ArtistToolkit.exe
pause
