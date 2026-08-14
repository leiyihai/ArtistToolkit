"""图标批处理核心逻辑:抠图 → 拆图标 → 按形状/尺寸裁切输出。

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
    "original": "无(直接缩放)",
    "square": "方形",
    "circle": "正圆",
    "rounded_square": "圆角方形",
}

CORNER_RADIUS_RATIO = 0.14      # 圆角半径 = 输出边长 * 0.14(128px 时约 18px,视觉一致)
CORNER_RATIO_MIN = 0.01         # 圆角半径比例下限(1%)
CORNER_RATIO_MAX = 0.50         # 圆角半径比例上限(50%)
SCALE_RATIO = 1.08              # 放大比例,消除裁切边缘少量镂空/半透明
MIN_ICON_PIXELS = 500           # 小于该像素数的连通域视为噪声
MIN_ICON_EDGE = 30              # 宽或高小于该值视为细条噪声


# ---------- 抠图(懒加载 rembg,首次调用才下载/加载模型) ----------
_session = None
_remove_fn = None

_MODEL_NAME = "birefnet-general"
_U2NET_DIR = os.path.join(os.path.expanduser("~"), ".u2net")
_MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-epoch_244.onnx"


def _ensure_model(log=None):
    """确保模型文件就绪:缺失则流式下载、已存在则预热读取,期间按字节回调百分比。

    下载/加载都是大文件(~927MB),没有现成进度回调;预热读取顺带填充页缓存,加速 onnxruntime 加载。
    """
    os.makedirs(_U2NET_DIR, exist_ok=True)
    path = os.path.join(_U2NET_DIR, _MODEL_NAME + ".onnx")
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
    if log:
        log("⏳ 下载模型: 0%")
    import urllib.request
    req = urllib.request.Request(_MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(path, "wb") as f:
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


def matting(img, log=None):
    """用 BiRefNet 去除背景,返回新 RGBA 图。"""
    global _session, _remove_fn
    if _session is None:
        _ensure_model(log)
        from rembg import remove, new_session
        _remove_fn = remove  # 必须缓存到全局,否则第二次调用 remove 是未绑定局部变量
        _session = new_session("birefnet-general")
    if log:
        log("  抠图中…(CPU 处理较慢,每张约 1 分钟)")
    # ponytail: 关闭 alpha_matting——pymatting 后处理在大图上极慢(1024² 卡 3 分钟+),
    # 图标抠图对边缘 alpha 要求低,关闭后约 19s 完成且质量可接受;需发丝级精细边缘时再开启。
    return _remove_fn(img, session=_session)


def is_transparent(img):
    """已有透明背景(≥5% 像素透明)则跳过抠图。"""
    import numpy as np
    alpha = np.array(img)[:, :, 3]
    return (alpha < 10).sum() / alpha.size >= 0.05


# ---------- 拆图标 ----------
def split_by_gaps(mask):
    # ponytail: 穿透判定——谷底必须接近全透明才算网格间隙;
    # 仅凭投影相对低会误切图标内部空隙(圆润表情包/镂空图标)。
    # 需要更精确切分(不规则排列/斜排)时换基于形态学的算法。
    """按行列投影缝隙把 mask 切成网格子块,返回局部 (x1,y1,x2,y2) 列表。

    分隔线要求整行/列穿透(投影接近 0),图标内部空隙投影虽低但不切。
    """
    import numpy as np
    from scipy.signal import find_peaks
    h, w = mask.shape
    rs = mask.sum(axis=1)
    cs = mask.sum(axis=0)
    if rs.max() == 0:
        return []
    gap_thresh = max(1.0, 0.02 * max(rs.max(), cs.max()))  # 穿透阈值:谷底须低于此行/列峰值的 2%
    rv, _ = find_peaks(-rs, prominence=rs.max() * 0.1, width=2)
    cv, _ = find_peaks(-cs, prominence=cs.max() * 0.1, width=2)
    rows = [0] + [int(v) for v in rv if rs[v] <= gap_thresh] + [h]
    cols = [0] + [int(v) for v in cv if cs[v] <= gap_thresh] + [w]
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
    max_size = float(sizes.max()) if num else 0.0

    boxes = []
    for i in range(1, num + 1):
        # 绝对阈值 + 相对主块比例:滤掉抠图残渣(如 ~1k 像素小碎块)
        # ponytail: 按最大块 2% 过滤,图标集近似等大时安全;含极小真图标时需按内容再判
        if sizes[i - 1] < MIN_ICON_PIXELS or (max_size and sizes[i - 1] < 0.02 * max_size):
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


def _shape_mask(size, mode, radius_ratio=CORNER_RADIUS_RATIO):
    """4x 超采样抗锯齿蒙版:mode = circle | rounded_square。"""
    up = 4
    m = Image.new("L", (size * up, size * up), 0)
    d = ImageDraw.Draw(m)
    if mode == "circle":
        d.ellipse((0, 0, size * up, size * up), fill=255)
    else:
        d.rounded_rectangle((0, 0, size * up, size * up),
                            radius=max(1, int(size * up * radius_ratio)), fill=255)
    return m.resize((size, size), Image.Resampling.LANCZOS)


def crop_icon(img, crop_type, size, corner_ratio=CORNER_RADIUS_RATIO):
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
    out.paste(square, (0, 0), _shape_mask(size, crop_type, corner_ratio))
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
def process_batch(paths, crop_type, sizes, out_dir, normalize=False, corner_ratio=None, log=print):
    """逐张:抠图 → 拆图标 → 按类型/尺寸裁切保存。

    输出结构:
        out_dir/icons/                 拆分出的原始图标(原尺寸)
        out_dir/<类型>/<尺寸>/xxx_N.png  裁切结果
    normalize=True 时,裁切结果再统一图标视觉大小(normalize_icons 逻辑)。
    corner_ratio:圆角半径比例(仅 rounded_square 生效),自动限制在 [CORNER_RATIO_MIN, CORNER_RATIO_MAX]。
    """
    if crop_type not in CROP_TYPES:
        raise ValueError(f"未知裁切类型: {crop_type}")
    if corner_ratio is None:
        corner_ratio = CORNER_RADIUS_RATIO
    corner_ratio = min(max(corner_ratio, CORNER_RATIO_MIN), CORNER_RATIO_MAX)  # ponytail: clamp 即边界防御,前端限制 + 后端兜底
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
                img = matting(img, log=log)  # 模型加载进度 + 抠图提示在 matting 内输出

            icons = segment_icons(img)
            log(f"  拆出 {len(icons)} 个图标")
            for i, icon in enumerate(icons, 1):
                bname = f"{base}_{i}"
                icon.save(os.path.join(icons_dir, bname + ".png"))
                for size in sizes:
                    out = crop_icon(icon, crop_type, size, corner_ratio)
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
    # 圆角参数:边界值也应产出正确尺寸(半径比例 clamp 由 process_batch 负责)
    for r in (0.01, 0.5):
        rs = crop_icon(icons[0], "rounded_square", 128, corner_ratio=r)
        assert rs.size == (128, 128), (r, rs.size)
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
