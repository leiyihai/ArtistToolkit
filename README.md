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
- 显卡(可选):Windows 上抠图默认走 DirectML,任意 DX12 显卡(含核显)都能加速,不需要装 CUDA;没有可用显卡时自动回退 CPU
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

## 抠图加速(GPU)

推理默认走 **DirectML**(Windows 自带的 DX12 计算后端),不要求装 CUDA/cuDNN。
选择逻辑在 `tools/ort_ep.py`:DirectML → CUDA → CPU 依次尝试,GPU 建会话失败时
记一行日志并回退,不会让任务失败。

实测(RTX 4060,1024×1024,`rembg.remove` 单张,仅推理):

| 模型 | CPU | DirectML | 倍数 |
| --- | ---: | ---: | ---: |
| 通用(ISNet) | 0.64 s | 0.13 s | 4.9× |
| 经典(U2Net) | 0.26 s | 0.04 s | 6.5× |
| 人像精细(BiRefNet) | 12.0 s | — | 固定 CPU |

- **BiRefNet 固定走 CPU**:它的融合节点在 DirectML 上直接报错(`DmlFusedNode`),
  而且失败一次会让同进程后续会话一起回退,所以 `tools/ort_ep.py` 里按模型白名单
  (`CPU_ONLY`)隔离。
- **端到端倍数小于上表**:批处理还包含 PNG 解码/编码与掩膜合成,1024² 图更会跑
  `alpha_matting`(pymatting,纯 CPU)。实测(RTX 4060,`process_batch` 全流程,稳定后取最快一轮):

  | 场景 | 优化前(CPU) | DirectML + 精修调优 | 说明 |
  | --- | ---: | ---: | --- |
  | 图标图集 2048² ×2(抠图 + 拆分 + 裁切) | 8.65 s | 3.70 s(2.3×) | 含收尾处理约 +0.5 s/张 |
  | AI 抠图 2048² ×4(超 3M 像素,不做精修) | 0.91 s/张 | 0.47 s/张(1.9×) | 只走掩膜 + 收尾 |
  | AI 抠图 1024² ×6(开精修) | 3.43 s/张 | **1.85 s/张(1.9×)** | 精修 pymatting |

- **收尾处理(默认开启,`tools/matting_refine.finish`)**:抠完再做三步纯像素操作,
  2048² 约 0.5 s:
  1. **背景去边**:从图像四周估背景色;背景够纯(95 分位偏差 ≤16)时,把过渡带里
     接近背景色的半透明像素压成透明。模型掩膜常把轮廓外的背景带进 0.1~0.9 的 alpha,
     叠在深色底上就是灰白毛边;这一步按颜色判断,只动过渡带,不动已经确信的前景
     (图标内部的白块、白高光 alpha≈255,不在过渡带里)。背景是照片/花纹的图自动跳过。
  2. **边缘收窄**:同一类素材图上,alpha 过渡按 0.35~0.65 收成 1px 左右,贴合手抠观感。
  3. **内部填实 + 颜色外扩**:离透明区 3px 以内保持渐变,更内侧的 alpha 一律 255
     (模型在图标内部偏白处常只给 200~250,不填实会"透底");
     透明区用最近的不透明像素颜色填充,缩放导出时不再把背景色拉进边缘。

  前三步只在"纯色背景素材图"上生效;需要原始未收尾结果时按
  `finish(img, harden_px=0, bleed_px=0, trim=False)` 关闭。

- **小图的第二道瓶颈:alpha 精修**。≤3M 像素时 rembg 会跑 pymatting 的 closed-form
  求解(1024² 图集约 2.6 s,其中 93% 是 `estimate_alpha_cf`)。`tools/matting_refine.py`
  按同一算法重写这一步,只把 CG 收敛阈值从默认 `1e-7` 放宽到 `1e-5`:
  同一张 1024² 图集 4.38 s → 2.85 s(1.5×),alpha 最大差 14/255、平均 0.009,
  差值 >32 的像素 **0 个**。开关:
  - `ATK_ALPHA_MATTING=off` 跳过精修(最快,边缘变硬);
  - `ATK_ALPHA_MATTING_RTOL=1e-4` 再快约 2 倍,但软边缘会有成片差异,不建议默认;
  - 精修过程任何异常都会自动退回普通抠图,不阻断批处理。

- **质量**:CPU 与 DirectML 输出同一张 1024²/2048² 图,Alpha 最大通道差 1(逐像素比较),
  没有可见差异。
- **验证是否真的走了 GPU**:后端支持 `engine_info` 命令,返回
  `{"onnxruntime": ..., "sessions": {"isnet-general-use": "DirectML(GPU)"}, ...}`;
  界面日志里也会打印一行 `推理设备: DirectML(GPU)`。若显示 CPU,通常是打包时漏了
  `DirectML.dll`(见 `ArtistToolkit-backend.spec` 的 `directml_binaries()`)。
- **覆盖开关**:`ATK_ORT_PROVIDERS=cpu` 强制 CPU;`ATK_ORT_PROVIDERS=dml` 或 `cuda`
  强制对应后端(显式值同样会在失败时回退)。
- **装哪个包**:`onnxruntime-directml` / `onnxruntime-gpu` / `onnxruntime` 三选一
  (import 名都叫 `onnxruntime`),见 `requirements.txt`。

## 新增一个 TAB 页

1. **核心**:新建 `tools/<name>/core.py`,实现无界面的纯逻辑(PIL/rembg 等都在这一层);
   需要跨进程的入口函数用 `__all__` 导出。
2. **后端**:在 `backend.py` 里 import 核心,并在 `main()` 加一个 `cmd` 分支(长任务用线程 + `emit` 回日志/进度)。
3. **界面**:在 `ui/src/pages/<name>.rs` 写页面状态与视图,`ui/src/main.rs` 的 `Tab` 枚举加一项并路由到它。
   卡片/按钮/分段等构件直接复用 `ui/src/widgets.rs`。

核心约定:**一个功能 = `tools/<name>/` 一个自包含文件夹**,界面层(`ui/`)只做壳和交互。
