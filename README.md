# Artist Toolkit

将个人小脚本工具打包成带界面的软件,左侧页签栏可扩展。当前包含:

- **批量图标导出**:拖入/选择图片 → 抠图去背景 → 自动拆分图标 → 按所选裁切类型(正圆/圆角方形/方形/无=直接缩放)与尺寸(32/64/128/256,可多选)输出,可选"统一图标视觉大小"(normalize)。

## 环境要求

- Python ≥ 3.10
- NVIDIA GPU(可选,有 GPU 自动加速,没 GPU 自动用 CPU)

## 安装运行

```bash
pip install -r requirements.txt
python main.py
```

首次抠图会自动下载 AI 模型(约 1GB,缓存于 `~/.u2net`;也可手动把模型文件放到该目录跳过下载)。

## 使用

1. 把图片拖到界面(或点"选择图片"),可多张
2. 选裁切类型(单选:正圆/圆角方形/方形/无)与输出尺寸(多选)
3. 可选勾选"统一图标视觉大小"——裁切后按内容面积统一图标大小(normalize)
4. 选输出保存路径(默认桌面)
5. 点"运行"

输出结构(以选"正圆"+"32/128"为例):

```
<输出路径>/
├── icons/                    # 拆分出的原始图标(原尺寸)
└── circle/
    ├── 32/   图片名_1.png …
    └── 128/  图片名_1.png …
```

图片已透明背景时自动跳过抠图,直接拆分。

## 打包成 exe(分享给他人)

```bash
pip install pyinstaller
build.bat
```

产物:`dist/ArtistToolkit.exe`,单文件,双击即用,对方无需装 Python。

## 项目结构

```
ArtistToolkit/
├── main.py           # GUI 入口(左侧页签栏,后续脚本加在这里)
├── core.py           # 抠图/拆图/裁切核心逻辑
├── run.py            # 原命令行版主脚本(备用)
├── crop_to_*.py      # 原单脚本(备用)
├── normalize_icons.py
├── build.bat         # PyInstaller 打包脚本
└── requirements.txt
```
