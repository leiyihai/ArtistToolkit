# 新增一个 TAB 页(功能)指南

**一个功能 = `tools/<name>/` 一个自包含文件夹。** 按本指南添加,功能之间不会混淆。
完整参考实现:`tools/icon_export/`。

## 目录结构模板

```
tools/<name>/
├── core.py          # 功能核心逻辑(纯 Python,无界面)
├── frontend/
│   └── view.js      # 该 TAB 页界面,registerPage 注册
└── docs/            # (可选)该功能的文档/参考
```

- **纯前端功能**(不需要 Python):只写 `frontend/view.js` 即可,不用建 core。
- **需要后台处理**(抠图/计算/文件批处理):写 `core.py`,界面经 `window.api.call` 调用;命令统一注册到项目根 `backend.py`(聚合后端,所有功能共用一个进程,模型只加载一次)。

## 三步接入

### 1. 写后端逻辑(core.py)

`core.py` 提供纯 Python 函数(如 `process_batch(paths, out, log=print)`),在项目根 `backend.py` 里 import 并注册命令:

- **stdin**:每行一个请求 `{"id": 1, "cmd": "xxx", ...参数}`
- **stdout**:每行一个消息
  - 结果 `{"id": 1, "ok": true, "result": ...}` 或 `{"id": 1, "ok": false, "error": "..."}`
  - 进度/日志事件 `{"id": 1, "event": "log"|"progress", ...}`
- 记得在入口强制 UTF-8(Windows 下避免日志乱码):
  ```python
  import sys
  sys.stdout.reconfigure(encoding="utf-8")
  ```

### 2. 注册页面(一处)

在 `app/renderer/features.js` 的 `__FEATURES__` 数组里登记功能文件夹名(**数组顺序 = 侧边栏显示顺序,调整排序只改这里**):

```js
// 页签配置:功能目录名 + 顺序(数组顺序 = 显示顺序)
window.__FEATURES__ = ['icon_export', 'ai_matting', 'image_resize'];
```

`tools/<name>/frontend/view.js` 里:

```js
window.__PAGES__ = window.__PAGES__ || [];
window.__PAGES__.push({
  id: '<name>',                 // 唯一,建议与文件夹同名
  title: '页签标题',             // 侧边栏显示名
  mount(container) { /* 构建 DOM + 绑定事件 */ },
  unmount() { /* 清理:事件解绑、URL.revokeObjectURL 等 */ },
});
```

外壳启动时按 `FEATURES` 动态加载各功能脚本并渲染侧边栏页签,无需再改 `index.html`。
`tools/` 目录会被 `build.bat` 内置进打包产物(功能页脚本随包分发)。

### 3. 界面调后端

`preload.js` 已暴露全局 `window.api`,直接使用:

```js
// 调用后端(经主进程转发到 backend.py/exe)
const r = await window.api.call('<cmd>', { ...参数 });
// 订阅后端日志事件(返回取消函数,unmount 时调用)
const off = window.api.onLog((msg) => { if (msg.event === 'log') ... });
// 文件相关
window.api.pathFor(file)   // 拖放 File -> 真实路径
window.api.pickDir()       // 选目录 -> 路径
window.api.defaultOut()    // 默认输出目录(桌面)
```

## 样式与主题

复用 `app/renderer/styles.css` 的 Claude 主题 tokens(CSS 变量),新页面无需自带样式表:

- `--bg` / `--panel` / `--border` 背景层次,`--text` / `--muted` 文字
- `--accent`(珊瑚橙)强调;`.btn` / `.btn-primary` / `.seg` / `.chip` / `.card` / `.field` / `.text-input` / `.dropzone` / `.thumb` / `.log` 等现成控件
- 页面结构建议:`page-head`(标题+副标题)→ 多个 `card`(分区,`h2` 小标题)→ `runbar`(进度+主按钮)→ 日志卡片

## 打包注意

后端打包入口为项目根 `backend.py`(聚合所有功能命令);`ArtistToolkit-backend.spec` 已指向它,无需每次改动。
