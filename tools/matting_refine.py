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

__all__ = ["matting_enabled", "refine_cutout", "finish", "background_color", "trim_background_fringe", "rtol"]

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


def background_color(rgb, band=8, max_spread=16.0):
    """从图像四周估一个纯色背景;背景不够纯时返回 None(照片类图不参与去边)。

    返回 (背景色, 95 分位偏差)。偏差超过 max_spread 视为"没有纯色背景"。
    """
    border = np.concatenate(
        [
            rgb[:band].reshape(-1, 3),
            rgb[-band:].reshape(-1, 3),
            rgb[:, :band].reshape(-1, 3),
            rgb[:, -band:].reshape(-1, 3),
        ]
    ).astype(np.float32)
    median = np.median(border, axis=0)
    spread = float(np.percentile(np.abs(border - median).max(axis=1), 95))
    if spread > max_spread:
        return None, spread
    return median, spread


def trim_background_fringe(alpha, rgb, background, edge_width=25.0, low=5 / 255, high=242 / 255):
    """把过渡带里"看起来就是背景色"的半透明像素压掉。

    模型掩膜会把轮廓外的背景带进 0.1~0.9 的 alpha,叠在深色底上就是灰白毛边/灰雾。
    纯色背景下可以直接用颜色判断:越接近背景色,越应该透掉。alpha 已经接近 1 的前景
    (图标内部的白色高光、白十字等)不在过渡带内,不会被误伤。
    """
    distance = np.abs(rgb.astype(np.float32) - np.asarray(background, dtype=np.float32)).max(axis=-1)
    factor = np.clip(distance / edge_width, 0.0, 1.0)
    band = (alpha > low * 255) & (alpha < high * 255)
    return np.where(band, alpha * factor, alpha).astype(np.uint8)


def finish(rgba, harden_px=3, bleed_px=3, trim=True, edge_contrast=True):
    """收尾三步,都是纯像素操作,2048² 约 0.4 s:

    1. 背景去边:纯色背景下,过渡带里近似背景色的半透明像素压成透明,
       去掉模型掩膜带出来的白/灰毛边(背景不够纯时自动跳过)。
    2. 内部填实:离透明区超过 harden_px 的前景像素一律 alpha=255。
       模型掩膜在图标内部偏白/偏亮处常给出 230~250,不填实就会"漏出"底色,
       看起来像是这些白块被抠掉了。
    3. 颜色外扩:把前景颜色向外扩散到透明区,替换那里残留的背景色,
       否则结果缩放(界面缩略图、导出小尺寸)时会把背景色拉进边缘。
    """
    from scipy.ndimage import binary_erosion, distance_transform_edt

    arr = np.asarray(rgba).astype(np.uint8).copy()
    alpha = arr[..., 3]

    if trim:
        background, _spread = background_color(arr[..., :3])
        if background is not None:
            alpha = trim_background_fringe(alpha, arr[..., :3], background)
            # 纯色背景通常意味着"素材图",边缘按手抠的习惯收窄成 1px 过渡
            if edge_contrast:
                alpha = np.clip((alpha.astype(np.float32) / 255.0 - 0.35) / 0.30, 0, 1) * 255
                alpha = alpha.astype(np.uint8)
            arr[..., 3] = alpha

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
