const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // 后端调用:call('process_batch', {...}) -> Promise
  call: (cmd, payload) => ipcRenderer.invoke('backend:call', cmd, payload),
  // 后端日志事件订阅,返回取消函数(unmount 时调用)
  onLog: (cb) => {
    const listener = (_e, msg) => cb(msg);
    ipcRenderer.on('backend:log', listener);
    return () => ipcRenderer.removeListener('backend:log', listener);
  },
  // 拖放 File -> 真实路径(新版 Electron 已移除 File.path)
  pathFor: (file) => webUtils.getPathForFile(file),
  toolsRoot: () => ipcRenderer.invoke('get-tools-root'),
  defaultOut: () => ipcRenderer.invoke('default-out'),
  pickDir: () => ipcRenderer.invoke('dialog:pickDir'),
});
