"""AI 抠图核心逻辑:去背景 → 输出透明背景 PNG。

从 tools/icon_export/core.py 裁减而来,只保留抠图(matting)部分。
"""
import os
import gc

from PIL import Image

try:
    from tools import matting_refine, ort_ep
except ImportError:  # `python tools/ai_matting/core.py` 直接跑自检时,仓库根不在 sys.path
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from tools import matting_refine, ort_ep

__all__ = ["process_batch"]



# ---------- 抠图(懒加载 rembg,首次调用才下载/加载模型) ----------
# 模型可选:同一个 session 按模型名缓存。默认 isnet-general-use——对扁平卡通素材、
# 带深色底的图集比 birefnet-general 干净(birefnet 会把整块深色底判成前景)。
MODELS = {
    "isnet-general-use": "通用(ISNet)",
    "u2net": "经典(U2Net)",
    "birefnet-general": "人像精细(BiRefNet)",
}
DEFAULT_MODEL = "isnet-general-use"
# 超过该像素数关闭 alpha_matting(pymatting 内存开销随像素数增长)
MAX_MATTING_PIXELS = 3_000_000
# 与原 run.py 一致的边缘参数
ALPHA_MATTING_FOREGROUND = 230
ALPHA_MATTING_BACKGROUND = 20
ALPHA_MATTING_ERODE = 5

_sessions = {}
_remove_fn = None

_MODEL_NAME = "birefnet-general"
_U2NET_DIR = os.path.join(os.path.expanduser("~"), ".u2net")
_MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-epoch_244.onnx"


def _model_home():
    """模型目录:打包版优先用包内模型(U2NET_HOME,免下载),否则用户缓存目录。"""
    d = os.environ.get("U2NET_HOME")
    if d and os.path.isfile(os.path.join(d, _MODEL_NAME + ".onnx")):
        return d
    return os.path.join(os.path.expanduser("~"), ".u2net")


def _ensure_model(log=None):
    """确保模型文件就绪:优先用包内模型(U2NET_HOME),缺失则下载到用户缓存并预热,按字节回调百分比。"""
    path = os.path.join(_model_home(), _MODEL_NAME + ".onnx")
    if os.path.exists(path) and os.path.getsize(path) > 100_000_000:
        total = os.path.getsize(path)
        read = 0
        last_pct = -1
        with open(path, "rb") as f:
            while chunk := f.read(64 * 1024 * 1024):
                read += len(chunk)
                pct = int(read / total * 100)
                if log and pct // 10 > last_pct // 10:
                    log(f"⏳ 加载模型: {min(pct, 100)}%")  # ⏳ 前缀=前端原地更新此行
                last_pct = pct
        return
    # 下载(固定到用户目录:包内目录可能只读,且模型属用户缓存)
    dl_dir = os.path.join(os.path.expanduser("~"), ".u2net")
    os.makedirs(dl_dir, exist_ok=True)
    dl_path = os.path.join(dl_dir, _MODEL_NAME + ".onnx")
    if log:
        log("⏳ 下载模型: 0%")
    import urllib.request
    req = urllib.request.Request(_MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dl_path, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        last_pct = -1
        while chunk := resp.read(1024 * 1024):
            f.write(chunk)
            got += len(chunk)
            if total:
                pct = int(got / total * 100)
                if log and pct // 5 > last_pct // 5:
                    log(f"⏳ 下载模型: {min(pct, 100)}%")
                last_pct = pct
    if log:
        log("⏳ 下载完成")


def matting(img, model=DEFAULT_MODEL, log=None):
    """去除背景,返回新 RGBA 图。model 取 MODELS 里的键。"""
    global _remove_fn
    if model not in MODELS:
        raise ValueError(f"未知模型: {model!r},可选 {tuple(MODELS)}")
    if model not in _sessions:
        if model == _MODEL_NAME:
            _ensure_model(log)  # 包内自带 birefnet,读一遍并按块打进度
        if log:
            log(f"  加载模型 {MODELS[model]}…")
        # 推理设备由 tools/ort_ep 选:Windows 优先 DirectML,失败回退 CPU
        _sessions[model] = ort_ep.session(model, log=log)
        if log:
            log(f"  推理设备: {ort_ep.device(_sessions[model])}")
    if _remove_fn is None:
        from rembg import remove

        _remove_fn = remove  # 缓存到全局,避免每次 import
    if log:
        log("  抠图中…")
    sess = _sessions[model]
    # 与原 run.py 相同的边缘参数:小图(≤3M 像素)启用 alpha 精修
    use_matting = matting_refine.matting_enabled(img.size[0] * img.size[1], MAX_MATTING_PIXELS)
    if use_matting:
        # 精修走本地实现:与 rembg 同一算法,但 CG 收敛阈值可调(默认 1e-5,实测约 1.7×)
        return matting_refine.refine_cutout(
            img,
            sess,
            foreground_threshold=ALPHA_MATTING_FOREGROUND,
            background_threshold=ALPHA_MATTING_BACKGROUND,
            erode_size=ALPHA_MATTING_ERODE,
            log=log,
        )
    return _remove_fn(img, session=sess, alpha_matting=False)


def is_transparent(img):
    """已有透明背景(≥5% 像素透明)则跳过抠图。"""
    import numpy as np
    alpha = np.array(img)[:, :, 3]
    return (alpha < 10).sum() / alpha.size >= 0.05


# ---------- 主流程 ----------
def process_batch(paths, out_dir, model=DEFAULT_MODEL, log=print, progress=None):
    """逐张:抠图 → 保存透明背景 PNG 到 out_dir(原名)。已透明图片跳过。

    model: MODELS 的键,默认 isnet-general-use。
    progress(done, total) 每处理完一张回调一次。
    """
    os.makedirs(out_dir, exist_ok=True)

    total = len(paths)
    done = 0
    for idx, path in enumerate(paths, 1):
        name = os.path.basename(path)
        base = os.path.splitext(name)[0]
        log(f"[{idx}/{total}] {name}")
        try:
            img = Image.open(path).convert("RGBA")
            if is_transparent(img):
                log("  跳过(已是透明背景)")
                continue
            img = matting(img, model=model, log=log)  # 模型加载进度 + 抠图提示在 matting 内输出
            save_path = os.path.join(out_dir, base + ".png")
            img.save(save_path, "PNG")
            log(f"  → {os.path.basename(save_path)}")
        except Exception as e:
            log(f"  !! 处理失败: {e}")
        done += 1
        if progress:
            progress(done, total)
        gc.collect()
    log(f"完成:{done} 张已输出到 {out_dir}")


def selftest():
    """不依赖推理的自检:is_transparent 判定 + rembg 可导入。返回 (ok, message)。"""
    img_opaque = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    img_trans = Image.new("RGBA", (64, 64), (255, 0, 0, 0))
    if is_transparent(img_opaque):
        return False, "纯不透明图应判定为需抠图"
    if not is_transparent(img_trans):
        return False, "全透明图应判定为已抠图"
    import rembg  # 验证打包环境 rembg 完整可用
    return True, f"OK, rembg {rembg.__version__}, {ort_ep.summary()}"


if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
