# -*- mode: python ; coding: utf-8 -*-
# Python 抠图引擎后端:Electron 主进程 spawn 它,stdio JSON 通信。
# 产物: dist/backend/ArtistToolkit-backend.exe
from PyInstaller.utils.hooks import copy_metadata

a = Analysis(
    ['tools/icon_export/backend.py'],
    pathex=['.'],
    binaries=[],
    datas=(
        copy_metadata('rembg')
        + copy_metadata('pymatting')   # importlib.metadata 需要,缺失会 ImportError
        + copy_metadata('pooch')
    ),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 本机环境里无关的重库(与主 spec 一致)
        'torch', 'torchvision', 'torchmcubes', 'einops', 'functorch',
        'gradio', 'transformers', 'fastapi',
        'uvicorn', 'starlette', 'pandas',
        'matplotlib', 'huggingface_hub', 'jax', 'dask', 'sympy',
    ],
    noarchive=False,
)

# 过滤 onnxruntime 的 CUDA / TensorRT provider(CPU 通用版用不到)
a.binaries = [
    b for b in a.binaries
    if not any(k in b[0].lower() for k in ('providers_cuda', 'providers_tensorrt', 'cudnn', 'cublas', 'cufft', 'curand', 'cusparse', 'cusolver'))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ArtistToolkit-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # 后端进程保留控制台无妨,stdio 通信
    disable_windowed_traceback=False,
)
