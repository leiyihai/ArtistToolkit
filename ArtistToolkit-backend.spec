# -*- mode: python ; coding: utf-8 -*-
# Python 抠图引擎后端:Electron 主进程 spawn 它,stdio JSON 通信。
# 产物: dist/backend/ArtistToolkit-backend.exe
import os

from PyInstaller.utils.hooks import copy_metadata


def rust_extension_datas():
    """把 rust/<crate>/python/<module> 按原相对位置放进包内。

    tools/*/core.py 里 rust-anything 生成的启用块会按 core.py 的相对位置找
    `rust/<crate>/python/<module>`;打包后 __file__ 在 _MEIPASS 下,所以这里保持同样的
    目录结构,扩展就能被找到,exe 里也走 Rust 实现(找不到时自动回退 Python)。
    """
    datas = []
    root = os.path.join(SPECPATH, 'rust')
    if not os.path.isdir(root):
        return datas
    for crate in sorted(os.listdir(root)):
        packages = os.path.join(root, crate, 'python')
        if not os.path.isdir(packages):
            continue
        for module in sorted(os.listdir(packages)):
            src = os.path.join(packages, module)
            if not os.path.isdir(src):
                continue
            if any(name.endswith('.pyd') for name in os.listdir(src)):
                datas.append((src, f'rust/{crate}/python/{module}'))
    return datas


a = Analysis(
    ['backend.py'],
    pathex=['.'],
    binaries=[],
    datas=(
        [('tools/img2box/assets', 'tools/img2box/assets')]  # .blend + bake_skybox.py(非 py 不自动收集)
        + rust_extension_datas()                            # 已编译的 Rust 内核(.pyd)
        + copy_metadata('rembg')
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
