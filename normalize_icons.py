import os
from PIL import Image

# ========== 配置项 ==========
# 导出的目标文件夹名称（会在当前目录下自动创建）
OUTPUT_DIR_NAME = "normalized"

# 图标内容（非透明像素）面积占画布的目标比例
# 0.5 表示内容面积 = 128x128 的 50%，视觉大小统一
# 调大（如 0.6）→ 图标整体更大更满；调小（如 0.4）→ 图标更小、留白更多
TARGET_AREA_RATIO = 0.5

# 内容最长边上限（px），防止极端形状放大后超出画布
MAX_EDGE = 128

# 支持的图片格式
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
# ============================

def normalize_visual_size():
    # 获取脚本所在目录（处理同目录下的所有图片）
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, OUTPUT_DIR_NAME)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"已创建输出文件夹: {OUTPUT_DIR_NAME}")

    renamed_count = 0

    for filename in os.listdir(current_dir):
        if filename == OUTPUT_DIR_NAME or not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue

        file_path = os.path.join(current_dir, filename)

        try:
            with Image.open(file_path) as img:
                img = img.convert("RGBA")
                width, height = img.size  # 固定为 128x128
                canvas_area = width * height

                # 1. 内容包围盒 + 面积（alpha > 10 的像素数）
                mask = img.split()[3].point(lambda v: 255 if v > 10 else 0)
                bbox = mask.getbbox()
                if bbox is None:
                    print(f"跳过（无内容）: {filename}")
                    continue
                content = img.crop(bbox)
                cw, ch = content.size
                content_area = sum(1 for p in mask.getdata() if p > 10)

                # 2. 按面积等比缩放：内容面积 -> 画布面积 * TARGET_AREA_RATIO
                scale = (canvas_area * TARGET_AREA_RATIO / content_area) ** 0.5
                nw = max(1, round(cw * scale))
                nh = max(1, round(ch * scale))

                # 3. 保护：最长边不超过画布
                if max(nw, nh) > MAX_EDGE:
                    s2 = MAX_EDGE / max(nw, nh)
                    nw, nh = round(nw * s2), round(nh * s2)

                content = content.resize((nw, nh), Image.Resampling.LANCZOS)

                # 4. 居中贴回原尺寸画布（四周留透明 alpha）
                canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                canvas.paste(content, ((width - nw) // 2, (height - nh) // 2), content)

                # 5. 保存
                save_path = os.path.join(output_dir, filename)
                canvas.save(save_path, "PNG")

                print(f"处理成功: {filename}  内容 {cw}x{ch} (面积 {content_area/canvas_area*100:.0f}%) -> {nw}x{nh}")
                renamed_count += 1

        except Exception as e:
            print(f"跳过/处理失败 {filename}: {e}")

    print(f"\n全部完成！共将 {renamed_count} 个图标统一视觉大小并保存至 '{OUTPUT_DIR_NAME}' 目录。")

if __name__ == "__main__":
    normalize_visual_size()
