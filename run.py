import os, sys
import gc
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.signal import find_peaks
from rembg import remove, new_session

TEMP = "_tmp"
OUT = "output"
MAX_MATTING_PIXELS = 3_000_000  # 超过此像素数禁用 alpha_matting，防内存溢出
os.makedirs(TEMP, exist_ok=True)
os.makedirs(f"{OUT}/icons", exist_ok=True)
os.makedirs(f"{OUT}/128", exist_ok=True)
os.makedirs(f"{OUT}/32", exist_ok=True)

session = new_session("birefnet-general")


def split_by_gaps(mask):
    # ponytail: 规则网格假设——检测贯穿行/列的投影谷底切分。
    # 非规则排列（错位/斜排）的图标集无法切分，需时换基于形态学/模板的算法。
    """按行列投影缝隙把 mask 切成网格子块，返回局部 (x1,y1,x2,y2) 列表"""
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
            if sub.sum() < 500:
                continue
            ys, xs = np.where(sub)
            # 加格子起点偏移，返回区域局部坐标
            blocks.append((x1 + xs.min(), y1 + ys.min(), x1 + xs.max(), y1 + ys.max()))
    return blocks


def process_image(name):
    base = os.path.splitext(name)[0]
    img = Image.open(os.path.join("input", name)).convert("RGBA")

    # 判断是否已抠图：有透明通道且 ≥5% 像素透明
    alpha_pixels = np.array(img)[:, :, 3]
    already_done = (alpha_pixels < 10).sum() / alpha_pixels.size >= 0.05

    if already_done:
        print(f"[1/3] 跳过抠图（已是透明背景）: {name}")
        out = img
    else:
        print(f"[1/3] 抠图: {name}")
        matting = img.size[0] * img.size[1] <= MAX_MATTING_PIXELS
        out = remove(img, session=session, alpha_matting=matting,
                     alpha_matting_foreground_threshold=230,
                     alpha_matting_background_threshold=20,
                     alpha_matting_erode_size=5)
        if not matting:
            print("      （图较大，已自动关闭边缘平滑）")
        out.save(os.path.join(TEMP, name), "PNG")

    # 2. 拆分图标
    print(f"[2/3] 拆分: {name}")
    alpha = np.array(out)[:, :, 3]
    mask = alpha > 10
    labeled, num = ndimage.label(mask)
    sizes = ndimage.sum(mask, labeled, range(1, num + 1))

    boxes = []
    for i in range(1, num + 1):
        if sizes[i - 1] < 500:
            continue
        ys, xs = np.where(labeled == i)
        x1, y1, x2, y2 = xs.min(), ys.min(), xs.max(), ys.max()
        # 疑似图标集（尺寸大）→ 检测网格缝隙再切分
        if (x2 - x1) > 300 or (y2 - y1) > 300:
            sub = mask[y1:y2 + 1, x1:x2 + 1]
            for bx1, by1, bx2, by2 in split_by_gaps(sub):
                boxes.append((x1 + bx1, y1 + by1, x1 + bx2, y1 + by2))
        else:
            boxes.append((x1, y1, x2, y2))

    # 过滤细条噪声（宽或高过小，非图标）
    boxes = [b for b in boxes if min(b[2] - b[0], b[3] - b[1]) >= 30]

    merged = []
    for bx in sorted(boxes):
        found = False
        for i, (mx, my, mx2, my2) in enumerate(merged):
            if bx[0] <= mx2 and bx[2] >= mx and bx[1] <= my2 and bx[3] >= my:
                merged[i] = (min(mx, bx[0]), min(my, bx[1]), max(mx2, bx[2]), max(my2, bx[3]))
                found = True
                break
        if not found:
            merged.append(bx)

    merged.sort(key=lambda b: (b[1], b[0]))
    for i, (x1, y1, x2, y2) in enumerate(merged):
        icon = out.crop((x1, y1, x2 + 1, y2 + 1))
        icon_name = f"{base}_{i+1}.png"
        icon.save(os.path.join(f"{OUT}/icons", icon_name), "PNG")

        # 3. 缩放到 128 和 32
        for size in (128, 32):
            w, h = icon.size
            scale = size / max(w, h)
            nw, nh = int(w * scale), int(h * scale)
            resized = icon.resize((nw, nh), Image.LANCZOS)
            canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            canvas.paste(resized, ((size - nw) // 2, (size - nh) // 2), resized)
            canvas.save(os.path.join(f"{OUT}/{size}", icon_name), "PNG")

    print(f"      → {len(merged)} 个图标")


for name in os.listdir("input"):
    if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        continue
    try:
        process_image(name)
    except Exception as e:
        print(f"  !! 处理失败 {name}: {e}")
    gc.collect()  # 释放内存，防止大图叠加溢出

# 清理临时文件
for f in os.listdir(TEMP):
    os.remove(os.path.join(TEMP, f))
os.rmdir(TEMP)
print(f"\n完成！结果在 output/icons/（原图）、output/128/、output/32/")
