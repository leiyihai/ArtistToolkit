"""stdio JSON 后端:供 Electron 主进程调用,进程常驻(rembg 模型只加载一次)。

协议:stdin 每行一个请求 {"id", "cmd", ...};stdout 每行一个消息:
  - 结果 {"id", "ok": bool, "result" | "error"}
  - 事件 {"id", "event": "log", "message"}
开发模式:python backend.py(自动把项目根加入 sys.path)。
打包模式:PyInstaller 以本文件为入口。
"""
import json
import os
import sys

# 强制 stdout/stderr 用 UTF-8:Windows 默认 GBK,Electron 主进程按 UTF-8 解码会乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tools.ai_matting.core import process_batch, selftest  # noqa: E402


def emit(out, rid, **payload):
    msg = {"id": rid}
    msg.update(payload)
    out.write(json.dumps(msg, ensure_ascii=False) + "\n")
    out.flush()


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
            elif cmd == "process_batch":
                process_batch(
                    req["paths"], req["out"],
                    log=lambda m: emit(out, rid, event="log", message=m),
                )
                emit(out, rid, ok=True, result="处理完成")
            else:
                emit(out, rid, ok=False, error=f"未知命令: {cmd}")
        except Exception as e:
            import traceback
            emit(out, rid, ok=False, error=f"{e}", trace=traceback.format_exc())
        out.flush()


if __name__ == "__main__":
    main()
