# -*- mode: python ; coding: utf-8 -*-
# ArtistToolkit 打包配置:排除无关重库(torch 全家等)与 CPU 用不到的 CUDA provider。
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=(
        collect_data_files('tkinterdnd2')
        + copy_metadata('rembg')
        + copy_metadata('pymatting')   # importlib.metadata 需要,缺失会 ImportError
        + copy_metadata('pooch')
    ),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 本机环境里无关的重库,去掉后 exe 从 2.9GB 降到 ~130MB
        # 注意:不要排除 numba/llvmlite(rembg alpha_matting 链)、skimage/networkx(rembg 需要)
        'torch', 'torchvision', 'torchmcubes', 'einops', 'functorch',
        'gradio', 'transformers', 'fastapi',
        'uvicorn', 'starlette', 'pandas',
        'matplotlib', 'huggingface_hub', 'jax', 'dask', 'sympy',
    ],
    noarchive=False,
)

# 过滤 onnxruntime 的 CUDA / TensorRT provider(CPU 通用版用不到,省 ~245MB)
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
    name='ArtistToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
