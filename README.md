# Artist Toolkit

个人小脚本工具箱,带原生桌面界面(Rust + GPUI),左侧页签,功能按文件夹自包含。当前包含:

- **图标批处理**:拖入/选择图片 → 抠图去背景 → 自动拆分图标 → 按裁切类型(正圆/圆角方形/方形/无=直接缩放)与尺寸(32/64/128/256,可多选)输出,可选"统一图标视觉大小"。
- **AI 抠图**:图片一键去背景,输出透明 PNG;可选模型(通用 ISNet / 经典 U2Net / 人像精细 BiRefNet)。
- **批量缩放**:递归扫描图片,精确缩放到指定尺寸(含常用预设),保持目录结构,可取消。
- **去底(UnMult)**:去黑底/去白底/自动判断,反预乘恢复直通色,输出透明 PNG(像素内核已移植到 Rust)。
- **HDRI 转天空盒**:HDRI 全景图 → Blender 烘焙 → 4×3 网格切图 → 6 个天空盒面(含 bedwars 版),内置 3D 预览(需本地 Blender,页面指定路径)。

> 旧版 Electron / Tkinter 界面已在 GPUI 版稳定后移除(仍可从 git 历史找回)。

## 环境要求

- Python ≥ 3.10(后端依赖:`pip install -r requirements.txt`)
- Rust 1.97+ 与 MSVC Build Tools(编译界面与 Rust 内核)
- NVIDIA GPU(可选,有 GPU 自动加速,没 GPU 自动用 CPU)
- Blender(仅「天空盒烘焙」需要)

## 安装运行

双击 `start.vbs`(无控制台窗口),或运行 `start.bat`:

```
start.vbs     # 直接拉起已构建的界面 exe,不闪控制台
start.bat     # 命令行入口;缺构建产物时会先 cargo build --release
```

首次运行如果没有 `dist-gpui\ArtistToolkit.exe`,会先 `cargo build --release`(约 3-8 分钟,之后秒开)。
应用是 GUI 子系统、Python 后端用 `CREATE_NO_WINDOW` 启动,运行期不会弹控制台窗口。

开发界面:`cd ui && cargo run`。只跑后端:`python backend.py`(stdio JSON,见 `ui/README.md` 的协议说明)。

首次抠图会加载 AI 模型(约 1GB,缓存于 `~/.u2net`;仓库 `models/` 有模型时自动使用,免下载)。

## 使用

1. 把图片拖到界面(或点"选择图片"),可多张
2. 选裁切类型(单选)、输出尺寸(多选)、抠图模型(可选)
3. 可选"统一图标视觉大小"——裁切后按内容面积统一图标大小
4. 选输出保存路径(默认桌面),点"开始导出"

图标批处理的输出结构(以"正圆"+"32/128"为例):

```
<输出路径>/
├── icons/                    # 拆分出的原始图标(原尺寸)
└── circle/
    ├── 32/   0001.png …
    └── 128/  0001.png …
```

图片已是透明背景时自动跳过抠图。

## 打包成 exe(分享给他人)

```bat
package.bat
```

产物:`dist-gpui\ArtistToolkit.exe` + `ArtistToolkit-backend.exe` + `models\` + `tools\img2box\models\`。
整个目录拷给别人即可运行,对方无需装 Python(后端已打包,含 Rust 内核 `.pyd`);`start.bat` 会优先用它。

## 项目结构

```
ArtistToolkit/
├── ui/                     # Rust/GPUI 桌面前端(gpui-kit),默认界面
│   ├── src/main.rs         # 外壳:侧边栏、页头、后端连接、任务路由
│   ├── src/theme.rs        # 主题色板(还原原版 Claude 配色)
│   ├── src/widgets.rs      # 卡片/按钮/分段/chip/缩略图/日志等构件
│   ├── src/pages/          # 五个页面(一页一模块)
│   ├── src/backend.rs      # spawn Python 后端、stdio JSON 通信
│   └── scripts/            # 截图、打包脚本
├── tools/                  # 每个功能 = 一个自包含文件夹(只有 Python 核心)
│   ├── icon_export/core.py # 抠图/拆图标/裁切(连通域内核走 Rust)
│   ├── ai_matting/core.py  # 抠图(模型可选)
│   ├── image_resize/core.py
│   ├── unmult/core.py      # 去底(像素内核走 Rust)
│   ├── img2box/core.py     # Blender 烘焙 + 切图 + 预览服务
│   └── */tests/            # Rust 与 Python 的差分测试
├── backend.py              # stdio JSON 聚合后端(所有功能共用一个进程)
├── ArtistToolkit-backend.spec  # 后端 exe 的 PyInstaller 配置(含 .pyd)
├── package.bat             # 打包 GPUI 版分发包
├── start.bat / start.vbs   # 启动入口
├── rust/                   # Rust 加速:rust-anything 生成的 crate + 录制用例
│   ├── unmult-rs/          # 去底像素内核(PyO3),291 条录制 + REPORT.md
│   ├── icon-export-rs/     # 图标连通域(PyO3),156 条录制 + REPORT.md
│   └── PORT_MAP.md         # 移植进度地图
├── docs/
│   ├── rust-migration-plan.md  # rust-anything analyze 生成的迁移计划
│   └── (其余为历史文档)
└── requirements.txt
```

## 架构:GPUI 界面 + Python 引擎

- **界面**:Rust + [gpui-kit](https://github.com/longbridge/gpui-kit),五个页签;通过 stdio 逐行 JSON 调用后端,
  界面只做状态渲染,不重复实现业务逻辑。详见 `ui/README.md`。
- **引擎**:Python(`tools/<name>/core.py`)打包成独立 exe(`dist/ArtistToolkit-backend.exe`),前端 spawn 它,
  进程常驻(rembg 模型只加载一次)。
- **任务路由**:界面按 `JobKind` 把后端返回的 `log`/`progress` 送回发起页;一次性查询(如探测 Blender)走同一条通道。

## Rust 加速

用 [rust-anything](https://github.com/erkamyaman/rust-anything) 把两个纯计算内核移植成 Rust(PyO3),
Python 接口与界面都不变,`process_batch` 只在内部换成 Rust 实现:

| 内核 | 所在 crate | 录制用例 | 实测加速 |
| --- | --- | ---: | --- |
| `unmult_rgba`(去底:反预乘 + 3×3 去边) | `rust/unmult-rs` | 291 | **约 21×**(50.8 µs → 2.4 µs) |
| `segment_component_boxes`(Alpha 连通域 + 外接框,替换 scipy 逐块全图扫描) | `rust/icon-export-rs` | 156 | **约 3.9×**(14.7 µs → 3.8 µs) |

- **行为录制**:用例由 Python 原实现录制(Rust 侧必须逐字节/逐值复现),
  `rust-anything diff <crate>` 应输出 `291/291`、`156/156`;`rust-anything gate <crate>` 是完成门禁。
- **差分测试**:`python tools/unmult/tests/test_kernel_parity.py`、
  `python tools/icon_export/tests/test_kernel_parity.py` 在同一进程里比较 Rust 与 Python 两条路径。
- **开关**:`RUST_ANYTHING_MODE=old`(或 `RUST_ANYTHING_UNIT_<NAME>=original`)回到 Python 实现;
  没有 `.pyd` 时也会自动回退。
- **改 Rust 后**:`rust-anything build <crate>` 重新编译,再 `package.bat` 重打包。

进度与后续单位见 `rust/PORT_MAP.md` 与 `docs/rust-migration-plan.md`。

## 抠图模型

三处抠图统一支持模型选择,默认 `isnet-general-use`:

| 模型 | 适合 | 速度 |
| --- | --- | --- |
| 通用(ISNet)`isnet-general-use` | 卡通/扁平素材、深色底图集 | 快 |
| 经典(U2Net)`u2net` | 通用素材 | 快 |
| 人像精细(BiRefNet)`birefnet-general` | 人像照片,发丝边缘 | 慢(2048×1152 约 20s/张) |

> BiRefNet 会把整块深色底判成前景,卡通图集建议用通用模型。

## 新增一个 TAB 页

1. **核心**:新建 `tools/<name>/core.py`,实现无界面的纯逻辑(PIL/rembg 等都在这一层);
   需要跨进程的入口函数用 `__all__` 导出。
2. **后端**:在 `backend.py` 里 import 核心,并在 `main()` 加一个 `cmd` 分支(长任务用线程 + `emit` 回日志/进度)。
3. **界面**:在 `ui/src/pages/<name>.rs` 写页面状态与视图,`ui/src/main.rs` 的 `Tab` 枚举加一项并路由到它。
   卡片/按钮/分段等构件直接复用 `ui/src/widgets.rs`。

核心约定:**一个功能 = `tools/<name>/` 一个自包含文件夹**,界面层(`ui/`)只做壳和交互。
