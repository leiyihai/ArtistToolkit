"""UnMult 去底核心逻辑:去黑底 / 去白底 / 自动判断,输出带 Alpha 的透明 PNG。

移植自 E:/vfx-unmult(src/unmult.py + src/utils.py + src/processor.py),算法保持一致。
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image

__all__ = ["MODES", "process_batch"]

MODES = ("black", "white", "auto")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
_EPS = 1.0 / 255.0  # Alpha 低于该值视为背景噪声(8bit 下 1 级)


# ---------- 基础算法(与 AE UnMult 视觉一致) ----------
def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def safe_divide(numerator, denominator, eps=_EPS):
    den = np.maximum(denominator, eps)
    out = numerator / den
    return np.where(denominator > eps, out, 0.0)


def estimate_alpha_black(rgb):
    """黑底素材:不透明度 ≈ max(R,G,B)。"""
    return clamp01(rgb.max(axis=-1))


def estimate_alpha_white(rgb):
    """白底素材:不透明度 ≈ 1 - min(R,G,B)。"""
    return clamp01(1.0 - rgb.min(axis=-1))


def recover_from_black(rgb, alpha):
    """黑底:C_straight = C_premult / Alpha。"""
    return safe_divide(rgb, alpha[..., None])


def recover_from_white(rgb, alpha):
    """白底:C_straight = (C_premult - (1-Alpha)) / Alpha。"""
    return safe_divide(rgb - (1.0 - alpha[..., None]), alpha[..., None])


def defringe(rgb, alpha, strength):
    """清理边缘黑/白描边:半透明边缘颜色向 3×3 邻域内更实(Alpha 更高)的像素靠拢。"""
    if strength <= 0.0:
        return rgb
    strength = float(min(max(strength, 0.0), 1.0))
    h, w = alpha.shape
    rgb_p = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")
    a_p = np.pad(alpha, 1, mode="edge")
    acc = np.zeros_like(rgb, dtype=np.float32)
    weight_sum = np.zeros((h, w), dtype=np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            wgt = a_p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]
            acc += rgb_p[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] * wgt[..., None]
            weight_sum += wgt
    neighbor = acc / np.maximum(weight_sum, 1e-6)[..., None]
    edge_mask = ((alpha > 0.02) & (alpha < 0.98))[..., None]
    return np.where(edge_mask, rgb + strength * (neighbor - rgb), rgb)


def black_unmult(rgb, alpha=None, defringe_strength=0.0, rebuild_alpha=False):
    if alpha is None or rebuild_alpha:
        alpha = estimate_alpha_black(rgb)
    return clamp01(defringe(recover_from_black(rgb, alpha), alpha, defringe_strength)), clamp01(alpha)


def white_unmult(rgb, alpha=None, defringe_strength=0.0, rebuild_alpha=False):
    if alpha is None or rebuild_alpha:
        alpha = estimate_alpha_white(rgb)
    return clamp01(defringe(recover_from_white(rgb, alpha), alpha, defringe_strength)), clamp01(alpha)


# ---------- 图片读写 / 背景判断 ----------
def load_image(path):
    """读取图片,返回 (rgb_float[0,1], alpha_float_or_None)。"""
    with Image.open(path) as im:
        had_alpha = "A" in im.getbands()
        arr = np.asarray(im.convert("RGBA"), dtype=np.float32) / 255.0
    rgb, alpha = arr[..., :3], arr[..., 3] if had_alpha else None
    if alpha is not None and alpha.min() >= 0.999:  # 有通道但完全不透明 → 视为无 Alpha
        alpha = None
    return rgb, alpha


def save_png(rgba, path):
    rgba8 = np.clip(np.round(rgba * 255.0), 0, 255).astype(np.uint8)
    Image.fromarray(rgba8, mode="RGBA").save(path, format="PNG")


def estimate_background(rgb):
    """四角+边缘 5px 平均亮度判断背景:black / white / unknown。"""
    edge = np.concatenate([
        rgb[:5].reshape(-1, 3), rgb[-5:].reshape(-1, 3),
        rgb[:, :5].reshape(-1, 3), rgb[:, -5:].reshape(-1, 3),
    ])
    mean = float(edge.mean())
    if mean < 32.0 / 255.0:
        return "black"
    if mean > 223.0 / 255.0:
        return "white"
    return "unknown"


# ---------- 主流程 ----------
def process_batch(paths, out_dir, mode="auto", defringe=0.0, rebuild_alpha=False,
                  no_overwrite=False, log=print, progress=None):
    """逐张去底,输出同名透明 PNG。返回 (成功数, 失败数)。"""
    if mode not in MODES:
        raise ValueError(f"未知模式: {mode!r},可选 {MODES}")
    os.makedirs(out_dir, exist_ok=True)

    files = [p for p in paths if Path(p).suffix.lower() in SUPPORTED_EXTENSIONS]
    total = len(files)
    if total == 0:
        log(f"未找到支持的图片({', '.join(sorted(SUPPORTED_EXTENSIONS))})")
        return 0, 0

    ok = failed = 0
    for i, src in enumerate(files, 1):
        name = os.path.basename(src)
        out = os.path.join(out_dir, Path(src).stem + ".png")
        if no_overwrite and os.path.exists(out):
            log(f"[{i}/{total}] {name}  跳过(已存在)")
            ok += 1
            if progress:
                progress(ok + failed, total)
            continue
        try:
            rgb, alpha = load_image(src)
            if mode == "auto":
                bg = estimate_background(rgb)
                if bg == "unknown":
                    raise ValueError("无法自动判断背景颜色,请改选 去黑底 或 去白底")
            else:
                bg = mode
            rgb_out, a = (black_unmult if bg == "black" else white_unmult)(
                rgb, alpha, defringe, rebuild_alpha)
            save_png(np.concatenate([rgb_out, a[..., None]], axis=-1), out)
            ok += 1
            log(f"[{i}/{total}] {name}  OK({bg})")
        except Exception as e:
            failed += 1
            log(f"[{i}/{total}] {name}  失败: {e}")
        if progress:
            progress(ok + failed, total)
    log(f"完成:成功 {ok},失败 {failed},输出到 {out_dir}")
    return ok, failed


def selftest():
    """自检:黑底/白底图去底后的 Alpha 与颜色恢复正确。返回 (ok, message)。"""
    import tempfile
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # 黑底:纯黑背景,中央亮红块
            black_bg = np.zeros((32, 32, 3), dtype=np.float32)
            black_bg[8:24, 8:24] = (1.0, 0.2, 0.2)
            out1 = black_unmult(black_bg)
            assert out1[1][0, 0] < 0.01, "黑底区域 Alpha 应≈0"
            assert abs(out1[1][16, 16] - 1.0) < 0.01, "亮红区域 Alpha 应≈1"
            assert abs(out1[0][16, 16, 0] - 1.0) < 0.02, "颜色应恢复为纯红"
            # 白底:纯白背景,中央灰块
            white_bg = np.ones((32, 32, 3), dtype=np.float32)
            white_bg[8:24, 8:24] = 0.3
            out2 = white_unmult(white_bg)
            assert out2[1][0, 0] < 0.01, "白底区域 Alpha 应≈0"
            assert abs(out2[1][16, 16] - 0.7) < 0.02, "灰区域 Alpha 应≈1-0.3"
            # auto 判断(纯色背景)
            assert estimate_background(black_bg) == "black"
            assert estimate_background(white_bg) == "white"
        return True, "OK"
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
