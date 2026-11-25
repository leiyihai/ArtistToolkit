"""UnMult 去底核心逻辑:去黑底 / 去白底 / 自动判断,输出带 Alpha 的透明 PNG。

移植自 E:/vfx-unmult(src/unmult.py + src/utils.py + src/processor.py),算法保持一致。
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
from PIL import Image

__all__ = ["MODES", "process_batch", "unmult_rgba"]

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


# ---------- 像素内核(纯字节进出,无 IO) ----------
# 单独成段的理由:rust-anything 的 PyO3 桥接只接受字节/数字/字符串这类可跨界类型,
# PIL/numpy 对象不能跨界。本函数只做「像素进 → 像素出」,所以能整段移植到 Rust
# (rust/unmult-rs),而图片读写与批处理编排留在 Python。
def unmult_rgba(data: bytes, width: int, height: int, mode: str,
                defringe_strength: float, rebuild_alpha: bool) -> bytes:
    """RGBA8 字节 → 去底后的 RGBA8 字节;与 process_batch 的逐张流程等价。

    黑底:Alpha≈max(R,G,B),C_straight = C_premult / Alpha;
    白底:Alpha≈1-min(R,G,B),C_straight = (C_premult - (1-Alpha)) / Alpha。
    """
    if mode not in ("black", "white"):
        raise ValueError(f"未知模式: {mode},可选 black/white")
    if width <= 0 or height <= 0:
        raise ValueError("尺寸必须为正整数")
    if not math.isfinite(defringe_strength):
        raise ValueError("defringe 必须是有限数值")
    expected = width * height * 4
    if len(data) != expected:
        raise ValueError(f"数据长度应为 {expected}({width}×{height}×4),实际 {len(data)}")

    arr = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4).astype(np.float32) / 255.0
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    if alpha.min() >= 0.999:  # 有通道但完全不透明 → 视为无 Alpha(与原 load_image 一致)
        alpha = None
    unmix = black_unmult if mode == "black" else white_unmult
    rgb_out, a = unmix(rgb, alpha, defringe_strength, rebuild_alpha)
    rgba = np.clip(np.round(np.concatenate([rgb_out, a[..., None]], axis=-1) * 255.0), 0, 255)
    return rgba.astype(np.uint8).tobytes()


# ---------- 图片读写 / 背景判断 ----------
def load_rgba_bytes(path):
    """读取图片并归一化为 RGBA8 字节;返回 (字节, (宽, 高))。"""
    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        return rgba.tobytes(), rgba.size


def rgba_to_float(data, width, height):
    """RGBA8 字节 → float32 RGB(0..1),供背景判断使用。"""
    arr = np.frombuffer(data, dtype=np.uint8).reshape(height, width, 4)
    return arr[..., :3].astype(np.float32) / 255.0


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
            data, (w, h) = load_rgba_bytes(src)
            if mode == "auto":
                bg = estimate_background(rgba_to_float(data, w, h))
                if bg == "unknown":
                    raise ValueError("无法自动判断背景颜色,请改选 去黑底 或 去白底")
            else:
                bg = mode
            Image.frombytes("RGBA", (w, h),
                            unmult_rgba(data, w, h, bg, defringe, rebuild_alpha)).save(out, format="PNG")
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
            # 字节内核(process_batch 走的就是这条路径)
            black_rgba = np.zeros((8, 8, 4), dtype=np.uint8)
            black_rgba[..., 3] = 255
            black_rgba[3:5, 3:5, :3] = (255, 51, 51)
            kernel_out = np.frombuffer(
                unmult_rgba(black_rgba.tobytes(), 8, 8, "black", 0.0, False), dtype=np.uint8
            ).reshape(8, 8, 4)
            assert kernel_out[0, 0, 3] == 0, "内核:黑底区域 Alpha 应为 0"
            assert kernel_out[3, 3, 3] == 255, "内核:亮红区域 Alpha 应为 255"
            assert tuple(kernel_out[3, 3, :3]) == (255, 51, 51), "内核:颜色应恢复原值"
            # 端到端:黑底图 → 透明 PNG
            Image.new("RGB", (12, 10), (0, 0, 0)).save(os.path.join(tmp, "b.png"))
            ok_n, failed_n = process_batch([os.path.join(tmp, "b.png")],
                                           os.path.join(tmp, "out"), mode="black",
                                           log=lambda _m: None)
            assert (ok_n, failed_n) == (1, 0), "端到端:黑底图应处理成功"
            with Image.open(os.path.join(tmp, "out", "b.png")) as done:
                assert done.mode == "RGBA" and done.getpixel((0, 0))[3] == 0
        return True, "OK"
    except Exception as e:
        return False, str(e)


# >>> rust-anything: unmult-rs is on. `rust-anything disable ../../rust/unmult-rs` removes this block.
def _rust_anything_unmult_rs():
    import importlib, os, sys
    mode = os.environ.get("RUST_ANYTHING_MODE")
    if mode == "old" or os.environ.get("RUST_ANYTHING_UNIT_UNMULT") == "original":
        return
    at = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../rust/unmult-rs/python"))
    sys.path.insert(0, at)
    try:
        native = importlib.import_module("unmult_rs")
    except ImportError:
        if mode == "new":
            raise
        return
    finally:
        sys.path.remove(at)
    globals().update({name: getattr(native, name) for name in ["unmult_rgba"]})


_rust_anything_unmult_rs()
del _rust_anything_unmult_rs
# <<< rust-anything: unmult-rs
if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
