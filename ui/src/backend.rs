//! 与 Python 后端(backend.py / ArtistToolkit-backend.exe)的 stdio JSON 通信。
//!
//! 协议与 Electron 版完全一致:每行一个 JSON。
//!   请求 {"id","cmd",...}
//!   结果 {"id":true,"ok":true,"result"|"error"}
//!   事件 {"id","event":"log"|"progress",...}

use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};

use serde_json::{Value, json};

/// 后端进程 + 写端。读端在独立线程里,把每行原文送进 channel。
pub struct Backend {
    child: Child,
    stdin: ChildStdin,
    next_id: u64,
}

impl Backend {
    /// 启动后端:优先用已打包的 exe,否则用 `python backend.py`。
    pub fn spawn(root: &Path) -> std::io::Result<(Self, smol::channel::Receiver<String>)> {
        let exe = root.join("dist").join("ArtistToolkit-backend.exe");
        let bundled = root.join("ArtistToolkit-backend.exe");
        let (cmd, _kind) = if bundled.is_file() {
            (Command::new(&bundled), "bundled")
        } else if exe.is_file() {
            (Command::new(&exe), "packaged")
        } else {
            let mut cmd = Command::new("python");
            cmd.arg("backend.py");
            (cmd, "python")
        };
        let mut cmd = cmd;
        cmd.current_dir(root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONUTF8", "1");
        // 与 Electron 版一致:优先用随包模型(免下载)。
        let models = root.join("models");
        if models.join("birefnet-general.onnx").is_file() {
            cmd.env("ATK_MODELS_DIR", &models);
        }
        // 天空盒预览的地面/展示模型目录。
        let viewer_models = root.join("tools").join("img2box").join("models");
        if viewer_models.is_dir() {
            cmd.env("ATK_VIEWER_MODELS", &viewer_models);
        }

        let mut child = cmd.spawn()?;
        let stdin = child.stdin.take().expect("stdin piped");
        let stdout = child.stdout.take().expect("stdout piped");
        let stderr = child.stderr.take().expect("stderr piped");

        let (tx, rx) = smol::channel::unbounded::<String>();
        let tx_err = tx.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                if tx.send_blocking(line).is_err() {
                    break;
                }
            }
        });
        // 后端的 traceback 也要能看到,否则出错只剩 "ok": false。
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines() {
                let Ok(line) = line else { break };
                if tx_err
                    .send_blocking(json!({"event": "stderr", "message": line}).to_string())
                    .is_err()
                {
                    break;
                }
            }
        });

        Ok((
            Self {
                child,
                stdin,
                next_id: 1,
            },
            rx,
        ))
    }

    /// 发送一条请求,返回它的 id。
    pub fn request(&mut self, cmd: &str, extra: Value) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        let mut msg = json!({"id": id, "cmd": cmd});
        if let (Some(map), Some(extra)) = (msg.as_object_mut(), extra.as_object()) {
            for (key, value) in extra {
                map.insert(key.clone(), value.clone());
            }
        }
        let _ = writeln!(self.stdin, "{msg}");
        let _ = self.stdin.flush();
        id
    }

    pub fn shutdown(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.shutdown();
    }
}

/// 应用根目录(后端 exe / backend.py 所在目录)。
///
/// 解析顺序:
/// 1. `ARTIST_TOOLKIT_ROOT` 环境变量(调试或自定义部署);
/// 2. exe 同目录有 `ArtistToolkit-backend.exe` 或 `backend.py` → 打包布局,用 exe 目录;
/// 3. 否则回退到编译期的仓库根目录(开发时 `cargo run`)。
pub fn app_root() -> PathBuf {
    if let Some(dir) = std::env::var_os("ARTIST_TOOLKIT_ROOT") {
        return PathBuf::from(dir);
    }
    if let Ok(exe) = std::env::current_exe()
        && let Some(dir) = exe.parent()
        && (dir.join("ArtistToolkit-backend.exe").is_file() || dir.join("backend.py").is_file())
    {
        return dir.to_path_buf();
    }
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(Path::to_path_buf)
        .unwrap_or_else(|| PathBuf::from("."))
}
