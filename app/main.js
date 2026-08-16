const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const os = require('os');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.join(__dirname, '..');
// 功能页脚本根目录:开发 = 项目根/tools;打包 = resources/tools(--extra-resource 放置)
const TOOLS_ROOT = path.join(ROOT, 'tools');

let win = null;
let backend = null;
let nextId = 1;
const pending = new Map(); // id -> {resolve, reject}
let outBuf = '';

// 后端进程查找:
//   打包模式 -> <app>/resources/ArtistToolkit-backend.exe(asar 外,--extra-resource 放置)
//   开发模式 -> 项目 dist/ArtistToolkit-backend.exe,或 python 直跑 backend.py
function findBackend() {
  const bundled = path.join(ROOT, 'ArtistToolkit-backend.exe');
  if (fs.existsSync(bundled)) return { cmd: bundled, args: [] };
  const exe = path.join(ROOT, 'dist', 'ArtistToolkit-backend.exe');
  if (fs.existsSync(exe)) return { cmd: exe, args: [] };
  const py = path.join(ROOT, 'backend.py');
  return { cmd: process.platform === 'win32' ? 'python' : 'python3', args: [py] };
}

function startBackend() {
  const { cmd, args } = findBackend();
  backend = spawn(cmd, args, {
    stdio: ['pipe', 'pipe', 'pipe'],
    cwd: ROOT,
    // 内置模型目录(打包模式 = resources/models,开发模式 = 项目根 models),后端据此免下载
    env: { ...process.env, ATK_MODELS_DIR: path.join(ROOT, 'models') },
  });

  backend.stdout.on('data', (chunk) => {
    outBuf += chunk.toString();
    let i;
    while ((i = outBuf.indexOf('\n')) >= 0) {
      const line = outBuf.slice(0, i).trim();
      outBuf = outBuf.slice(i + 1);
      if (!line) continue;
      let msg;
      try { msg = JSON.parse(line); } catch { continue; }
      if (msg.event) {
        // 日志事件转发给页面
        win && win.webContents.send('backend:log', msg);
      } else {
        const p = pending.get(msg.id);
        if (p) {
          pending.delete(msg.id);
          msg.ok ? p.resolve(msg) : p.reject(new Error(msg.error || '后端错误'));
        }
      }
    }
  });
  backend.stderr.on('data', (d) => console.error('[backend]', d.toString().trim()));
  backend.on('exit', (code) => {
    backend = null;
    for (const [, p] of pending) p.reject(new Error(`后端进程退出(code=${code})`));
    pending.clear();
  });
}

function callBackend(cmd, payload) {
  return new Promise((resolve, reject) => {
    if (!backend) { reject(new Error('后端未运行')); return; }
    const id = nextId++;
    pending.set(id, { resolve, reject });
    backend.stdin.write(JSON.stringify({ id, cmd, ...payload }) + '\n');
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1040, height: 720, minWidth: 880, minHeight: 600,
    backgroundColor: '#f5f4ef',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
  win.on('closed', () => { win = null; });
}

ipcMain.handle('backend:call', (_e, cmd, payload) => callBackend(cmd, payload));
ipcMain.handle('get-tools-root', () => TOOLS_ROOT);
ipcMain.handle('default-out', () => {
  const d = path.join(os.homedir(), 'Desktop');
  return fs.existsSync(d) ? d : path.join(os.homedir(), 'OneDrive', 'Desktop');
});
ipcMain.handle('dialog:pickDir', async () => {
  const r = await dialog.showOpenDialog(win, {
    title: '选择输出保存路径', properties: ['openDirectory'],
  });
  return r.canceled ? null : r.filePaths[0];
});

app.whenReady().then(() => {
  startBackend();
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('quit', () => { if (backend) backend.kill(); });
