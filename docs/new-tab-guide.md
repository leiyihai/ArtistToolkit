# 新增一个 TAB 页(功能)指南

**一个功能 = `tools/<name>/` 一个自包含文件夹。** 按本指南添加,功能之间不会混淆。
完整参考实现:`tools/icon_export/`。

## 目录结构模板

```
tools/<name>/
├── core.py          # 功能核心逻辑(纯 Python,无界面)
├── backend.py       # (可选)stdio JSON 后端:Electron 经子进程调用,长驻进程
├── frontend/
│   └── view.js      # 该 TAB 页界面,registerPage 注册
└── docs/            # (可选)该功能的文档/参考
```

- **纯前端功能**(不需要 Python):只写 `frontend/view.js` 即可,不用建 core/backend。
- **需要后台处理**(抠图/计算/文件批处理):写 `core.py` + `backend.py`,界面经 `window.api.call` 调用。

## 三步接入

### 1. 写后端(可选)

参照 `tools/icon_export/backend.py` 的 stdio 协议,进程长驻、模型只加载一次:

- **stdin**:每行一个请求 `{"id": 1, "cmd": "xxx", ...参数}`
- **stdout**:每行一个消息
  - 结果 `{"id": 1, "ok": true, "result": ...}` 或 `{"id": 1, "ok": false, "error": "..."}`
  - 进度/日志事件 `{"id": 1, "event": "log", "message": "..."}`
- 记得在入口强制 UTF-8(Windows 下避免日志乱码):
  ```python
  import sys
  sys.stdout.reconfigure(encoding="utf-8")
  ```

### 2. 注册页面(两处)

`app/renderer/index.html`,在功能页脚本区加一行:

```html
<!-- 功能页:一 TAB 一脚本,registerPage 注册 -->
<script src="../../tools/icon_export/frontend/view.js"></script>
<script src="../../tools/<name>/frontend/view.js"></script>
<script src="shell.js"></script>
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

外壳(`shell.js`)自动渲染侧边栏页签并切换,无需其他改动。

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

后端参与打包时,在 `ArtistToolkit-backend.spec` 里入口改为新功能入口(或扩展 backend.py 增加 cmd 分支);无需新后端时保持现状。
