"""批量图标导出核心逻辑:抠图 → 拆图标 → 按形状/尺寸裁切输出。

提炼自 run.py(抠图+拆分)与 crop_to_circle / crop_to_rounded_square / crop_to_square(裁切)。
GUI 不直接依赖本模块之外的脚本。
"""
import os
import gc

from PIL import Image, ImageDraw

__all__ = ["CROP_TYPES", "process_batch"]

# ---------- 配置 ----------
# 裁切类型:key -> 中文显示名(输出目录用 key,英文,文件系统安全)
CROP_TYPES = {
    "circle": "正圆",
    "rounded_square": "圆角方形",
    "square": "方形",
    "original": "无(直接缩放)",
}

MAX_MATTING_PIXELS = 3_000_000  # 超过此像素数禁用 alpha_matting,防内存溢出
CORNER_RADIUS_RATIO = 0.14      # 圆角半径 = 输出边长 * 0.14(128px 时约 18px,视觉一致)
SCALE_RATIO = 1.08              # 放大比例,消除裁切边缘少量镂空/半透明
MIN_ICON_PIXELS = 500           # 小于该像素数的连通域视为噪声
MIN_ICON_EDGE = 30              # 宽或高小于该值视为细条噪声


# ---------- 抠图(懒加载 rembg,首次调用才下载/加载模型) ----------
_session = None


def matting(img):
    """用 BiRefNet 去除背景,返回新 RGBA 图。"""
    global _session
    if _session is None:
        from rembg import remove, new_session
        _session = new_session("birefnet-general")
    w, h = img.size
    use_matting = w * h <= MAX_MATTING_PIXELS
    return remove(img, session=_session, alpha_matting=use_matting,
                  alpha_matting_foreground_threshold=230,
                  alpha_matting_background_threshold=20,
                  alpha_matting_erode_size=5)


def is_transparent(img):
    """已有透明背景(≥5% 像素透明)则跳过抠图。"""
    import numpy as np
    alpha = np.array(img)[:, :, 3]
    return (alpha < 10).sum() / alpha.size >= 0.05


# ---------- 拆图标 ----------
def split_by_gaps(mask):
    # ponytail: 规则网格假设——检测贯穿行/列的投影谷底切分。
    # 非规则排列(错位/斜排)的图标集无法切分,需时换基于形态学/模板的算法。
    """按行列投影缝隙把 mask 切成网格子块,返回局部 (x1,y1,x2,y2) 列表"""
    import numpy as np
    from scipy.signal import find_peaks
    h, w = mask.shape
    rs = mask.sum(axis=1)
    cs = mask.sum(axis=0)
    if rs.max() == 0:
        return []
    rv, _ = find_peaks(-rs, prominence=rs.max() * 0.1, width=2)
    cv, _ = find_peaks(-cs, prominence=cs.max() * 0.1, width=2)
    rows = [0] + [int(v) for v in rv] + [h]
    cols = [0] + [int(v) for v in cv] + [w]
    blocks = []
    for i in range(len(rows) - 1):
        for j in range(len(cols) - 1):
            y1, y2 = rows[i], rows[i + 1]
            x1, x2 = cols[j], cols[j + 1]
            sub = mask[y1:y2, x1:x2]
            if sub.sum() < MIN_ICON_PIXELS:
                continue
            ys, xs = np.where(sub)
            blocks.append((x1 + xs.min(), y1 + ys.min(), x1 + xs.max(), y1 + ys.max()))
    return blocks


def segment_icons(img):
    """把透明背景图拆成独立图标,返回 PIL.Image 列表(保持原始尺寸)。"""
    import numpy as np
    from scipy import ndimage
    alpha = np.array(img)[:, :, 3]
    mask = alpha > 10
    labeled, num = ndimage.label(mask)
    sizes = ndimage.sum(mask, labeled, range(1, num + 1))

    boxes = []
    for i in range(1, num + 1):
        if sizes[i - 1] < MIN_ICON_PIXELS:
            continue
        ys, xs = np.where(labeled == i)
        x1, y1, x2, y2 = xs.min(), ys.min(), xs.max(), ys.max()
        # 疑似图标集(尺寸大)→ 检测网格缝隙再切分
        if (x2 - x1) > 300 or (y2 - y1) > 300:
            sub = mask[y1:y2 + 1, x1:x2 + 1]
            for bx1, by1, bx2, by2 in split_by_gaps(sub):
                boxes.append((x1 + bx1, y1 + by1, x1 + bx2, y1 + by2))
        else:
            boxes.append((x1, y1, x2, y2))

    # 过滤细条噪声
    boxes = [b for b in boxes if min(b[2] - b[0], b[3] - b[1]) >= MIN_ICON_EDGE]

    # 合并重叠框(网格切分可能产生重叠)
    merged = []
    for bx in sorted(boxes):
        for i, (mx, my, mx2, my2) in enumerate(merged):
            if bx[0] <= mx2 and bx[2] >= mx and bx[1] <= my2 and bx[3] >= my:
                merged[i] = (min(mx, bx[0]), min(my, bx[1]), max(mx2, bx[2]), max(my2, bx[3]))
                break
        else:
            merged.append(bx)

    merged.sort(key=lambda b: (b[1], b[0]))
    return [img.crop((x1, y1, x2 + 1, y2 + 1)) for x1, y1, x2, y2 in merged]


# ---------- 裁切 ----------
def _fit_square(img, size):
    """等比放大(以最小边为基准撑满 size,再乘 SCALE_RATIO 防边缘镂空),中心裁出 size×size。"""
    w, h = img.size
    scale = (size / min(w, h)) * SCALE_RATIO
    nw, nh = max(int(w * scale), size), max(int(h * scale), size)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    l, t = (nw - size) // 2, (nh - size) // 2
    return resized.crop((l, t, l + size, t + size))


def _shape_mask(size, mode):
    """4x 超采样抗锯齿蒙版:mode = circle | rounded_square。"""
    up = 4
    m = Image.new("L", (size * up, size * up), 0)
    d = ImageDraw.Draw(m)
    if mode == "circle":
        d.ellipse((0, 0, size * up, size * up), fill=255)
    else:
        d.rounded_rectangle((0, 0, size * up, size * up),
                            radius=max(1, int(size * up * CORNER_RADIUS_RATIO)), fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)


def crop_icon(img, crop_type, size):
    """按形状裁切并缩放到 size×size,返回新 RGBA 图。"""
    if crop_type == "original":
        # 无(直接缩放):等比缩放,最长边撑满 size,居中贴透明画布,不裁切形状
        w, h = img.size
        scale = size / max(w, h)
        nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
        resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
        return canvas
    square = _fit_square(img, size)
    if crop_type == "square":
        return square
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(square, (0, 0), _shape_mask(size, crop_type))
    return out


def normalize_icon(img, target_ratio=0.5):
    """统一图标视觉大小:内容包围盒等比缩放,使其面积占画布 target_ratio,居中贴回。

    提炼自 normalize_icons.py(TARGET_AREA_RATIO=0.5)。
    """
    import numpy as np
    w, h = img.size
    canvas_area = w * h
    mask = img.split()[3].point(lambda v: 255 if v > 10 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return img
    content = img.crop(bbox)
    cw, ch = content.size
    content_area = int((np.array(img)[:, :, 3] > 10).sum())

    # 按面积等比缩放:内容面积 -> 画布面积 * target_ratio
    scale = (canvas_area * target_ratio / content_area) ** 0.5
    nw, nh = max(1, round(cw * scale)), max(1, round(ch * scale))
    # 保护:最长边不超过画布
    if max(nw, nh) > max(w, h):
        s2 = max(w, h) / max(nw, nh)
        nw, nh = round(nw * s2), round(nh * s2)
    content = content.resize((nw, nh), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(content, ((w - nw) // 2, (h - nh) // 2), content)
    return canvas


# ---------- 主流程 ----------
def process_batch(paths, crop_type, sizes, out_dir, normalize=False, log=print):
    """逐张:抠图 → 拆图标 → 按类型/尺寸裁切保存。

    输出结构:
        out_dir/icons/                 拆分出的原始图标(原尺寸)
        out_dir/<类型>/<尺寸>/xxx_N.png  裁切结果
    normalize=True 时,裁切结果再统一图标视觉大小(normalize_icons 逻辑)。
    """
    if crop_type not in CROP_TYPES:
        raise ValueError(f"未知裁切类型: {crop_type}")
    os.makedirs(out_dir, exist_ok=True)
    icons_dir = os.path.join(out_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    total = len(paths)
    for idx, path in enumerate(paths, 1):
        name = os.path.basename(path)
        base = os.path.splitext(name)[0]
        log(f"[{idx}/{total}] {name}")
        try:
            img = Image.open(path).convert("RGBA")
            if is_transparent(img):
                log("  跳过抠图(已是透明背景)")
            else:
                log("  抠图中…(首次运行需下载约 180MB 模型,请耐心等待)")
                img = matting(img)

            icons = segment_icons(img)
            log(f"  拆出 {len(icons)} 个图标")
            for i, icon in enumerate(icons, 1):
                bname = f"{base}_{i}"
                icon.save(os.path.join(icons_dir, bname + ".png"))
                for size in sizes:
                    out = crop_icon(icon, crop_type, size)
                    if normalize:
                        out = normalize_icon(out)
                    sub = os.path.join(out_dir, crop_type, str(size))
                    os.makedirs(sub, exist_ok=True)
                    out.save(os.path.join(sub, bname + ".png"))
        except Exception as e:
            log(f"  !! 处理失败: {e}")
        gc.collect()


def selftest():
    """不依赖 rembg 的自检:拆分 + 四种裁切 + normalize + rembg 可导入。返回 (ok, message)。"""
    canvas = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.rectangle((10, 10, 50, 50), fill=(255, 0, 0, 255))     # 图标 1
    d.rectangle((120, 120, 160, 160), fill=(0, 255, 0, 255))  # 图标 2
    icons = segment_icons(canvas)
    if len(icons) != 2:
        return False, f"拆分数量错误: 期望 2, 实际 {len(icons)}"
    for size in (32, 64, 128, 256):
        for ct in CROP_TYPES:
            out = crop_icon(icons[0], ct, size)
            assert out.size == (size, size), (ct, size, out.size)
            assert out.mode == "RGBA"
    corner = crop_icon(icons[0], "circle", 128).getpixel((0, 0))
    if corner[3] != 0:
        return False, "圆形蒙版角落应透明"
    # original(无)应保持内容比例:宽高比不变
    w, h = icons[0].size
    org = crop_icon(icons[0], "original", 128)
    if org.size != (128, 128):
        return False, f"original 输出尺寸错误: {org.size}"
    # normalize:统一视觉大小后内容仍在画布内
    n = normalize_icon(crop_icon(icons[0], "circle", 128))
    if n.size != (128, 128):
        return False, f"normalize 输出尺寸错误: {n.size}"
    import rembg  # 验证打包环境 rembg 完整可用
    return True, f"OK, 图标 {[i.size for i in icons]}, rembg {rembg.__version__}"


if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
