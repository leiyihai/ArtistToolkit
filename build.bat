@echo off
rem 打包 ArtistToolkit
rem   1) Python 抠图引擎后端 -> dist\ArtistToolkit-backend.exe(Electron 主进程调用)
rem   2) 旧版 Tkinter GUI(过渡期保留)-> dist\ArtistToolkit.exe
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean ArtistToolkit-backend.spec
python -m PyInstaller --noconfirm --clean ArtistToolkit.spec
echo.
echo 完成: dist\ArtistToolkit-backend.exe + dist\ArtistToolkit.exe
pause
