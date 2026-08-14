"""AI 抠图核心逻辑:去背景 → 输出透明背景 PNG。

从 tools/icon_export/core.py 裁减而来,只保留抠图(matting)部分。
"""
import os
import gc

from PIL import Image

__all__ = ["process_batch"]

MAX_MATTING_PIXELS = 3_000_000  # 超过此像素数禁用 alpha_matting,防内存溢出


# ---------- 抠图(懒加载 rembg,首次调用才下载/加载模型) ----------
_session = None
_remove_fn = None


def matting(img):
    """用 BiRefNet 去除背景,返回新 RGBA 图。"""
    global _session, _remove_fn
    if _session is None:
        from rembg import remove, new_session
        _remove_fn = remove  # 必须缓存到全局,否则第二次调用 remove 是未绑定局部变量
        _session = new_session("birefnet-general")
    w, h = img.size
    use_matting = w * h <= MAX_MATTING_PIXELS
    return _remove_fn(img, session=_session, alpha_matting=use_matting,
                      alpha_matting_foreground_threshold=230,
                      alpha_matting_background_threshold=20,
                      alpha_matting_erode_size=5)


def is_transparent(img):
    """已有透明背景(≥5% 像素透明)则跳过抠图。"""
    import numpy as np
    alpha = np.array(img)[:, :, 3]
    return (alpha < 10).sum() / alpha.size >= 0.05


# ---------- 主流程 ----------
def process_batch(paths, out_dir, log=print):
    """逐张:抠图 → 保存透明背景 PNG 到 out_dir(原名)。已透明图片跳过。"""
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
            log("  抠图中…(首次运行需下载约 1GB 模型,请耐心等待)")
            img = matting(img)
            save_path = os.path.join(out_dir, base + ".png")
            img.save(save_path, "PNG")
            done += 1
            log(f"  → {os.path.basename(save_path)}")
        except Exception as e:
            log(f"  !! 处理失败: {e}")
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
    return True, f"OK, rembg {rembg.__version__}"


if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
