# Artist Toolkit

将个人小脚本工具打包成带界面的软件,左侧页签栏可扩展。当前包含:

- **图标批处理**:拖入/选择图片 → 抠图去背景 → 自动拆分图标 → 按所选裁切类型(正圆/圆角方形/方形/无=直接缩放)与尺寸(32/64/128/256,可多选)输出,可选"统一图标视觉大小"(normalize)。
- **AI 抠图**:图片一键去背景,输出透明 PNG。
- **批量缩放**:递归扫描图片,精确缩放到指定尺寸,保持目录结构。
- **去底(UnMult)**:去黑底/去白底/自动判断,反预乘恢复直通色,输出透明 PNG(内核已移植到 Rust,见下)。
- **HDRI 转天空盒**:HDRI 全景图 → Blender 烘焙 → 4×3 网格切图 → 6 个天空盒面(含 bedwars 版),内置 3D 预览(需本地安装 Blender,页面指定路径)。

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
│   └── icon_export/        # 【图标批处理】页
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
├── ui/                     # Rust/GPUI 桌面前端(gpui-kit),逐步替换 Electron 外壳
├── rust/                   # Rust 加速:rust-anything 生成的 crate + 录制用例
│   ├── unmult-rs/          # 去底像素内核的 Rust 移植(PyO3),含 291 条录制与 REPORT.md
│   ├── icon-export-rs/     # 图标连通域/外接框的 Rust 移植,含 156 条录制与 REPORT.md
│   └── PORT_MAP.md         # 移植进度地图(已移植/待移植单位)
├── docs/
│   ├── new-tab-guide.md    # ★ 新增一个 TAB 页的完整指南(照着做即可)
│   └── rust-migration-plan.md  # rust-anything analyze 生成的迁移计划
└── requirements.txt
```

### 架构:Electron 界面 + Python 抠图引擎

- **界面**:Electron(`app/`,Web 技术,现代美观);每个 TAB 页 = `tools/<name>/frontend/` 一个脚本,经 `registerPage` 注册到外壳。
- **引擎**:Python(`tools/<name>/core.py`)打包成独立 exe(`dist/ArtistToolkit-backend.exe`),Electron 主进程 spawn 它,stdio 逐行 JSON 通信,进程常驻(rembg 模型只加载一次)。
- **开发运行**:`cd app && npm start`(无后端 exe 时自动退回 `python backend.py`)。

### Rust 加速:去底内核 + 图标拆分

用 [rust-anything](https://github.com/erkamyaman/rust-anything) 把两个纯计算内核移植成 Rust(PyO3),
Python 接口与界面都不变,`process_batch` 只在内部换成 Rust 实现:

| 内核 | 所在 crate | 录制用例 | 实测加速 |
| --- | --- | ---: | --- |
| `unmult_rgba`(去底:反预乘 + 3×3 去边) | `rust/unmult-rs` | 291 | **约 21×**(50.8 µs → 2.4 µs) |
| `segment_component_boxes`(Alpha 连通域 + 外接框,替换 scipy 逐块全图扫描) | `rust/icon-export-rs` | 156 | **约 3.9×**(14.7 µs → 3.8 µs) |

- **行为录制**:用例由 Python 原实现录制(Rust 侧必须逐字节/逐值复现),
  `rust-anything diff <crate>` 应输出 `291/291`、`156/156`;`rust-anything gate <crate>` 是完成门禁
  (fmt、clippy、cargo test、无 panic、行为一致)。
- **差分测试**:`python tools/unmult/tests/test_kernel_parity.py`、
  `python tools/icon_export/tests/test_kernel_parity.py` 在同一进程里比较 Rust 与 Python 两条路径。
- **开关**:`RUST_ANYTHING_MODE=old`(或 `RUST_ANYTHING_UNIT_<NAME>=original`)回到 Python 实现;
  打包环境没有 `.pyd` 时也会自动回退,不影响 `build.bat` 产物。
- **改 Rust 后**:`rust-anything build <crate>` 重新编译(需要 Rust 1.97+ 与 MSVC Build Tools)。
- **打包**:`ArtistToolkit-backend.spec` 会把两个 `.pyd` 按 `rust/<crate>/python/<module>` 收进
  PyInstaller 包,所以 `dist/ArtistToolkit-backend.exe` 里同样走 Rust;没编译扩展时自动回退 Python。
  想确认包内用的是 Rust(缺扩展会直接报错而不是回退):`RUST_ANYTHING_MODE=new dist\ArtistToolkit-backend.exe`。

进度与后续单位(批量缩放、抠图、HDRI 切图等)见 `rust/PORT_MAP.md` 与 `docs/rust-migration-plan.md`。

### 新增一个 TAB 页

**完整指南见 `docs/new-tab-guide.md`**(三步:写 core → 根 backend.py 注册命令 → index.html 加一行 script + view.js 注册 → 界面调 `window.api`)。

核心约定:**一个功能 = `tools/<name>/` 一个自包含文件夹**,外壳 `app/` 只做页签栏和路由,不装功能代码。

> 旧版 Tkinter GUI(`main.py`)为过渡期保留,Electron 完全接管后移除。
> 界面设计遵循 frontend-design 技能规范。
