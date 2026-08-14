"""stdio JSON 后端:供 Electron 主进程调用,进程常驻。

协议:stdin 每行一个请求 {"id", "cmd", ...};stdout 每行一个消息:
  - 结果 {"id", "ok": bool, "result" | "error"}
  - 事件 {"id", "event": "log"|"progress", ...}
process 在独立线程执行,主线程持续读 stdin,可接收 cancel 中断。
开发模式:python backend.py;打包模式:PyInstaller 以本文件为入口。
"""
import json
import os
import sys
import threading

# 强制 stdout/stderr 用 UTF-8:Windows 默认 GBK,Electron 主进程按 UTF-8 解码会乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.image_resize.core import process, selftest  # noqa: E402

_lock = threading.Lock()  # stdout 多线程写入互斥
_cancel = threading.Event()


def emit(out, rid, **payload):
    msg = {"id": rid}
    msg.update(payload)
    with _lock:
        out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        out.flush()


def run_process(req, rid, out):
    _cancel.clear()
    try:
        process(
            req["input"], req["output"], req["width"], req["height"],
            log=lambda m: emit(out, rid, event="log", message=m),
            progress=lambda done, total: emit(out, rid, event="progress", done=done, total=total),
            cancel=_cancel,
        )
        emit(out, rid, ok=True, result="处理完成")
    except Exception as e:
        import traceback
        emit(out, rid, ok=False, error=str(e), trace=traceback.format_exc())


def main():
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        cmd = req.get("cmd")
        try:
            if cmd == "ping":
                emit(out, rid, ok=True, result="pong")
            elif cmd == "selftest":
                ok, msg = selftest()
                emit(out, rid, ok=bool(ok), result=str(msg))
            elif cmd == "process":
                threading.Thread(target=run_process, args=(req, rid, out), daemon=True).start()
            elif cmd == "cancel":
                _cancel.set()
                emit(out, rid, ok=True, result="cancelled")
            else:
                emit(out, rid, ok=False, error=f"未知命令: {cmd}")
        except Exception as e:
            import traceback
            emit(out, rid, ok=False, error=str(e), trace=traceback.format_exc())
        out.flush()


if __name__ == "__main__":
    main()
