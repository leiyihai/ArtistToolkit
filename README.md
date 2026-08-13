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
├── app/                    # Electron 外壳(新界面,现代 Web UI)
│   ├── package.json        # npm start 启动开发版
│   ├── main.js             # 主进程:窗口 + Python 后端进程管理 + IPC
│   ├── preload.js          # contextBridge 暴露 api(安全桥)
│   └── renderer/           # 外壳界面(侧边栏页签 + 主题样式)
│       ├── index.html
│       ├── styles.css
│       └── shell.js        # 页签路由:一 TAB 一脚本,registerPage 注册
├── main.py                 # 旧版 Tkinter GUI 外壳(过渡期保留,入口)
├── tools/                  # 每个 TAB 页 = 一个自包含功能文件夹
│   └── icon_export/        # 【批量图标导出】页
│       ├── __init__.py     # 页面类与核心接口的导出
│       ├── core.py         # 抠图/拆图/裁切核心逻辑(无界面,Python)
│       ├── backend.py      # stdio JSON 后端:Electron 经子进程调用(进程常驻,模型只加载一次)
│       ├── frontend/       # 该页 Electron 前端(registerPage 注册)
│       │   └── view.js
│       ├── legacy/         # 原单脚本版(备用,逻辑已提炼进 core.py)
│       │   ├── run.py
│       │   ├── crop_to_circle.py
│       │   ├── crop_to_rounded_square.py
│       │   ├── crop_to_square.py
│       │   └── normalize_icons.py
│       └── docs/
│           └── rembg-api-docs.md
├── ArtistToolkit.spec      # 旧版 Tkinter GUI 的 PyInstaller 配置
├── ArtistToolkit-backend.spec  # Python 后端 exe 的 PyInstaller 配置
├── build.bat               # 打包 Python 后端 exe + 旧版 GUI exe
├── start.bat               # 双击启动 Electron 新版界面
├── docs/
│   └── new-tab-guide.md    # ★ 新增一个 TAB 页的完整指南(照着做即可)
└── requirements.txt
```

### 架构:Electron 界面 + Python 抠图引擎

- **界面**:Electron(`app/`,Web 技术,现代美观);每个 TAB 页 = `tools/<name>/frontend/` 一个脚本,经 `registerPage` 注册到外壳。
- **引擎**:Python(`tools/<name>/core.py`)打包成独立 exe(`dist/ArtistToolkit-backend.exe`),Electron 主进程 spawn 它,stdio 逐行 JSON 通信,进程常驻(rembg 模型只加载一次)。
- **开发运行**:`cd app && npm start`(无后端 exe 时自动退回 `python backend.py`)。

### 新增一个 TAB 页

**完整指南见 `docs/new-tab-guide.md`**(三步:写 core/backend → index.html 加一行 script + view.js 注册 → 界面调 `window.api`)。

核心约定:**一个功能 = `tools/<name>/` 一个自包含文件夹**,外壳 `app/` 只做页签栏和路由,不装功能代码。

> 旧版 Tkinter GUI(`main.py`)为过渡期保留,Electron 完全接管后移除。
> 界面设计遵循 frontend-design 技能规范。
