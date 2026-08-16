"""聚合 stdio 后端:所有 TAB 功能共用一个进程,模型只加载一次。

协议:stdin 每行一个请求 {"id","cmd",...};stdout 每行一个消息:
  - 结果 {"id","ok":bool,"result"|"error"}
  - 事件 {"id","event":"log"|"progress",...}
所有耗时命令在线程执行,主循环持续读 stdin(支持取消)。
开发:python backend.py;打包:PyInstaller 以本文件为入口。
新增功能:在下方 import + main() 里加一个 cmd 分支即可,无需另起进程。
"""
import json
import os
import sys
import threading

# 强制 stdin/stdout/stderr 用 UTF-8:Windows 默认 GBK,Electron 主进程按 UTF-8 传输会乱码
for _s in (sys.stdin, sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 内置模型(分享免下载):main.js 经 ATK_MODELS_DIR 传入模型目录,
# 存在则让 rembg 直接从该目录加载(U2NET_HOME),跳过下载;否则保持默认缓存目录。
_models_dir = os.environ.get("ATK_MODELS_DIR", "")
if _models_dir and os.path.exists(os.path.join(_models_dir, "birefnet-general.onnx")):
    os.environ.setdefault("U2NET_HOME", _models_dir)

from tools.icon_export.core import process_batch as icon_process, selftest as icon_selftest
from tools.ai_matting.core import process_batch as matting_process, selftest as matting_selftest
from tools.image_resize.core import process as resize_process, selftest as resize_selftest
from tools.img2box.core import process as img2box_process, selftest as img2box_selftest
from tools.img2box.core import find_blender as img2box_find_blender
from tools.img2box.core import start_preview as img2box_preview

# 预热:主线程完成重量级依赖的首次 import(懒加载的 numpy/scipy/rembg 若在请求线程首次加载会卡死)
import numpy  # noqa: E402
import scipy  # noqa: E402
import scipy.ndimage  # noqa: E402  (icon_export 拆图标用)
import scipy.signal  # noqa: E402    (icon_export 网格切分用)
import rembg  # noqa: E402

_lock = threading.Lock()      # stdout 多线程写入互斥
_resize_cancel = threading.Event()
# 天空盒预览模型根(地面/展示模型,由 main.js 传入):开发=项目 tools/img2box/models,打包=exe 旁 models
_VIEWER_MODELS = os.environ.get("ATK_VIEWER_MODELS", "")


def emit(out, rid, **payload):
    msg = {"id": rid}
    msg.update(payload)
    with _lock:
        out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        out.flush()


def run_job(out, rid, fn):
    try:
        result = fn()
        emit(out, rid, ok=True, result=result if result is not None else "处理完成")
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
                results = [icon_selftest(), matting_selftest(), resize_selftest(), img2box_selftest()]
                ok = all(r[0] for r in results)
                emit(out, rid, ok=ok, result="; ".join(f"{'OK' if r[0] else 'FAIL'} {r[1]}" for r in results))
            elif cmd == "icon_process":
                threading.Thread(target=run_job, args=(out, rid, lambda req=req, rid=rid: icon_process(
                    req["paths"], req["crop"], req["sizes"], req["out"],
                    normalize=req.get("normalize", False),
                    corner_ratio=req.get("corner_ratio"),
                    log=lambda m: emit(out, rid, event="log", message=m),
                )), daemon=True).start()
            elif cmd == "matting_process":
                threading.Thread(target=run_job, args=(out, rid, lambda req=req, rid=rid: matting_process(
                    req["paths"], req["out"],
                    log=lambda m: emit(out, rid, event="log", message=m),
                    progress=lambda d, t: emit(out, rid, event="progress", done=d, total=t),
                )), daemon=True).start()
            elif cmd == "resize_process":
                _resize_cancel.clear()
                threading.Thread(target=run_job, args=(out, rid, lambda req=req, rid=rid: resize_process(
                    req["input"], req["output"], req["width"], req["height"],
                    log=lambda m: emit(out, rid, event="log", message=m),
                    progress=lambda d, t: emit(out, rid, event="progress", done=d, total=t),
                    cancel=_resize_cancel,
                )), daemon=True).start()
            elif cmd == "resize_cancel":
                _resize_cancel.set()
                emit(out, rid, ok=True, result="cancelled")
            elif cmd == "img2box_process":
                threading.Thread(target=run_job, args=(out, rid, lambda req=req, rid=rid: img2box_process(
                    req["input"], req["blender_path"], req["out_dir"],
                    log=lambda m: emit(out, rid, event="log", message=m),
                    progress=lambda s: emit(out, rid, event="progress", message=s),
                )), daemon=True).start()
            elif cmd == "img2box_find_blender":
                emit(out, rid, ok=True, result=img2box_find_blender())
            elif cmd == "img2box_preview":
                emit(out, rid, ok=True, result=img2box_preview(
                    req["skybox_dir"], models_root=_VIEWER_MODELS or None))
            else:
                emit(out, rid, ok=False, error=f"未知命令: {cmd}")
        except Exception as e:
            import traceback
            emit(out, rid, ok=False, error=str(e), trace=traceback.format_exc())
        out.flush()


if __name__ == "__main__":
    main()
