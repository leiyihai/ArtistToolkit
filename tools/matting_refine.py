"""Alpha 精修(边缘抠图)的可调实现:与 rembg 同一算法,但允许放宽 CG 收敛阈值。

背景:≤3M 像素的图会跑 `alpha_matting`,pymatting 的 closed-form 求解实测约 2.6 s/张
(RTX 4060,1024²,其中 93% 是 `estimate_alpha_cf` 的稀疏求解),此时推理只要 0.13 s,
求解成了真正的瓶颈。rembg 把 `cg_kwargs` 写死成默认值,所以这里按 rembg 的做法
(trimap → estimate_alpha_cf → estimate_foreground_ml → 合成)重写一遍,只多传一个
`rtol`。

实测(1024² 图集,55k 未知像素):
    rtol 默认 1e-7   2.57 s   (基准)
    rtol 1e-5        1.50 s   1.7×,alpha 平均差 0.009/255,最大 14
    rtol 1e-4        0.74 s   3.5×,alpha 平均差 0.155/255

环境变量:
    ATK_ALPHA_MATTING        auto(默认,沿用像素阈值) / on / off
    ATK_ALPHA_MATTING_RTOL   求解收敛阈值,默认 1e-5
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

__all__ = ["matting_enabled", "refine_cutout", "finish", "rtol"]

_FALSE = {"0", "off", "false", "no", "none"}
_TRUE = {"1", "on", "true", "yes"}


def matting_enabled(pixels: int, threshold: int) -> bool:
    """按 ATK_ALPHA_MATTING 与像素数决定是否做 alpha 精修(默认=原行为)。"""
    mode = os.environ.get("ATK_ALPHA_MATTING", "").strip().lower()
    if mode in _FALSE:
        return False
    if mode in _TRUE:
        return True
    return pixels <= threshold


def rtol() -> float:
    try:
        value = float(os.environ.get("ATK_ALPHA_MATTING_RTOL", "1e-5"))
    except ValueError:
        return 1e-5
    return value if value > 0 else 1e-5


def refine_cutout(img, session, foreground_threshold=230, background_threshold=20,
                  erode_size=5, tolerance=None, log=None):
    """模型掩膜 → alpha 精修 → RGBA 图;任何异常都退回普通抠图,不阻断批处理。"""
    from rembg.bg import fix_image_orientation, naive_cutout

    if tolerance is None:
        tolerance = rtol()
    img = fix_image_orientation(img)
    mask = session.predict(img)[0]
    try:
        return _refine(img, mask, foreground_threshold, background_threshold, erode_size, tolerance)
    except Exception as exc:  # noqa: BLE001 - pymatting 对退化 trimap 会抛 ValueError
        if log:
            log(f"  alpha 精修失败({exc}),改用普通抠图")
        return naive_cutout(img, mask)


def _refine(img, mask, foreground_threshold, background_threshold, erode_size, tolerance):
    from pymatting import estimate_alpha_cf, estimate_foreground_ml, stack_images
    from scipy.ndimage import binary_erosion

    if img.mode in ("RGBA", "CMYK"):
        img = img.convert("RGB")

    img_array = np.asarray(img)
    mask_array = np.asarray(mask)

    is_foreground = mask_array > foreground_threshold
    is_background = mask_array < background_threshold

    structure = np.ones((erode_size, erode_size), dtype=np.uint8) if erode_size > 0 else None
    if structure is not None:
        is_foreground = binary_erosion(is_foreground, structure=structure)
        is_background = binary_erosion(is_background, structure=structure, border_value=1)

    trimap = np.full(mask_array.shape, dtype=np.uint8, fill_value=128)
    trimap[is_foreground] = 255
    trimap[is_background] = 0

    img_normalized = img_array / 255.0
    trimap_normalized = trimap / 255.0

    alpha = estimate_alpha_cf(img_normalized, trimap_normalized, cg_kwargs={"rtol": tolerance})
    foreground = estimate_foreground_ml(img_normalized, alpha)
    cutout = stack_images(foreground, alpha)
    cutout = np.clip(cutout * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(cutout)


def finish(rgba, harden_px=3, bleed_px=3):
    """收尾两步,都是纯像素操作、几十毫秒:

    1. 内部填实:离透明区超过 harden_px 的前景像素一律 alpha=255。
       模型掩膜在图标内部偏白/偏亮处常给出 230~250,不填实就会"漏出"底色,
       看起来像是这些白块被抠掉了。
    2. 颜色外扩:把前景颜色向外扩散到半透明/透明区,替换那里残留的背景色。
       否则结果缩放(界面缩略图、导出小尺寸)时会把背景白拉进边缘,形成白毛边。

    只改 RGB 中 alpha 很低的部分,可见像素保持原样。
    """
    from scipy.ndimage import binary_erosion, distance_transform_edt

    arr = np.asarray(rgba).astype(np.uint8).copy()
    alpha = arr[..., 3]

    if harden_px > 0 and (alpha > 8).any():
        # 3×3 腐蚀 N 次 ≈ 离透明区 N 像素,比精确距离变换快 4 倍多
        core = binary_erosion(alpha > 8, structure=np.ones((3, 3), bool), iterations=harden_px)
        arr[..., 3] = np.where(core, 255, alpha)

    solid = alpha > 200
    if bleed_px > 0 and solid.any() and not solid.all():
        # 每个非不透明像素取最近的不透明像素颜色(只改 bleed_px 以内的那圈)
        distance, (iy, ix) = distance_transform_edt(~solid, return_indices=True)
        nearest = arr[..., :3][iy, ix]
        take = (~solid & (distance <= bleed_px))[..., None]
        arr[..., :3] = np.where(take, nearest, arr[..., :3])

    return Image.fromarray(arr)
