@echo off
rem 一键打包 Artist Toolkit 分发版(内置抠图模型,分享免下载)
rem   1) Python 聚合后端 -> dist\ArtistToolkit-backend.exe
rem   2) Electron 免安装版 -> dist-electron\ArtistToolkit-win32-x64\ArtistToolkit.exe
rem   3) 抠图模型(972MB)内置 -> resources\models\birefnet-general.onnx
cd /d "%~dp0"

rem 0) 校验功能登记完整性(新增功能后漏登记会在此拦截)
python check_pack.py
if errorlevel 1 (pause & exit /b 1)

echo [0/3] 准备抠图模型(优先项目 models\,缺则从本机缓存复制)...
if not exist "models\birefnet-general.onnx" (
    if exist "%USERPROFILE%\.u2net\birefnet-general.onnx" (
        mkdir models
        copy /y "%USERPROFILE%\.u2net\birefnet-general.onnx" "models\" >nul
        echo   已从本机缓存复制到 models\
    ) else (
        echo   警告: 本机无模型缓存,产物将不含内置模型(对方首次抠图需下载约 1GB)
    )
) else (
    echo   模型已存在 models\birefnet-general.onnx
)

echo [1/3] 打包 Python 后端...
python -m PyInstaller --noconfirm --clean ArtistToolkit-backend.spec
if errorlevel 1 (echo 后端打包失败 & pause & exit /b 1)

echo [2/3] 打包 Electron 应用...
cd app
rem 打包工具本地安装(避免 npx 临时下载因网络失败)
if not exist "node_modules\.bin\electron-packager.cmd" (
    echo   正在安装打包工具 electron-packager(仅首次)...
    call npm install --save-dev electron-packager
    if errorlevel 1 (echo 安装 electron-packager 失败 & cd .. & pause & exit /b 1)
)
call node_modules\.bin\electron-packager.cmd . ArtistToolkit --platform=win32 --arch=x64 --out=..\dist-electron --overwrite --extra-resource ..\dist\ArtistToolkit-backend.exe --extra-resource ..\models --extra-resource ..\tools
cd ..
if errorlevel 1 (echo Electron 打包失败 & pause & exit /b 1)

rem 3) 天空盒默认模型(木板/宝箱等)内置到 exe 旁 models,用户可继续添加
if exist "%~dp0tools\img2box\models" (
    xcopy /e /i /y "%~dp0tools\img2box\models" "%~dp0dist-electron\ArtistToolkit-win32-x64\models\" >nul
    echo   默认天空盒模型已复制到产物 models)

echo [3/3] 完成.
echo 产物: dist-electron\ArtistToolkit-win32-x64\ArtistToolkit.exe(双击运行,含后端引擎与抠图模型)
pause
