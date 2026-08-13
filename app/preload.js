const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // 后端调用:call('process_batch', {...}) -> Promise
  call: (cmd, payload) => ipcRenderer.invoke('backend:call', cmd, payload),
  // 后端日志事件订阅
  onLog: (cb) => ipcRenderer.on('backend:log', (_e, msg) => cb(msg)),
  // 拖放 File -> 真实路径(新版 Electron 已移除 File.path)
  pathFor: (file) => webUtils.getPathForFile(file),
  defaultOut: () => ipcRenderer.invoke('default-out'),
  pickDir: () => ipcRenderer.invoke('dialog:pickDir'),
});
