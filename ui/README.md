# ArtistToolkit · Rust/GPUI 前端

用 [gpui-kit](https://github.com/longbridge/gpui-kit)(GPUI 组件库)重写的桌面界面,
目标是逐步替换掉 Electron 外壳。

## 现状

| 页签 | 状态 |
| --- | --- |
| 去底 | ✅ 已迁移(选图/模式/去边/进度/日志,端到端可用) |
| 图标批处理 | ⏳ 占位 |
| AI 抠图 | ⏳ 占位 |
| 批量缩放 | ⏳ 占位 |
| HDRI 转天空盒 | ⏳ 占位 |

界面外壳(侧边栏、页签、主题、中文渲染)已完成;Electron 版仍可继续用(`start.bat`)。

## 架构

```
ui/ (Rust + GPUI)
  └── stdio 逐行 JSON  ←→  Python 后端(backend.py 或 dist/ArtistToolkit-backend.exe)
                              └── tools/*/core.py
                                    └── 已移植的 Rust 内核(rust/unmult-rs、rust/icon-export-rs)
```

- 界面不重写业务逻辑:与 Electron 版共用同一套后端协议(`{"id","cmd"}` / `{"id","ok",...}` / `{"id","event":...}`)。
- 后端启动顺序:优先 `dist/ArtistToolkit-backend.exe`(打包版,含 Rust 内核),否则 `python backend.py`。
- 后端输出在后台线程读、经 channel 回到 GPUI 的 async 任务,界面只做状态渲染。

## 运行

```powershell
cd ui
cargo run                     # 开发运行
cargo build --release         # 发布构建: target\release\artist-toolkit-ui.exe
```

需要 Rust 1.97+ 与 MSVC Build Tools;首次编译 GPUI 约 3–4 分钟。

## 开发期自动化(仅 debug 构建)

```powershell
$env:ATK_UI_IMAGES='E:\path\a.png;E:\path\b.png'   # 预填图片
$env:ATK_UI_AUTORUN='1'                             # 启动后自动点「开始」
powershell -File scripts\screenshot.ps1 -Out _shot.png
```

`screenshot.ps1` 会启动应用、把窗口置顶、截全屏 PNG 再退出,用于验证界面改动。

## 后续

1. 把「图标批处理 / AI 抠图 / 批量缩放 / HDRI 转天空盒」四页逐页搬过来(每页对应一个 `src/pages/*.rs`
   + `tools/<name>/frontend/view.js` 的交互)。
2. 支持拖拽入队(gpui 的文件拖放)、任务取消(批量缩放的 `resize_cancel`)。
3. 打包:与 PyInstaller 产物一起分发给最终用户。
