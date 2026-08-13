import os
from PIL import Image, ImageDraw, ImageOps

# ========== 配置项 ==========
# 导出的目标文件夹名称（会在当前目录下自动创建）
OUTPUT_DIR_NAME = "circle_icons"

# 放大比例（用于解决四周少量镂空/空白的问题）
# 1.05 代表放大 5%，1.1 代表放大 10%
# 如果边缘空缺较多，可以适度调大此数值（推荐 1.05 ~ 1.10）
SCALE_RATIO = 1.08

# 支持的图片格式
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
# ============================

def crop_to_circle():
    # 获取脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, OUTPUT_DIR_NAME)

    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"已创建输出文件夹: {OUTPUT_DIR_NAME}")

    renamed_count = 0

    for filename in os.listdir(current_dir):
        # 忽略输出文件夹本身和非图片文件
        if filename == OUTPUT_DIR_NAME or not filename.lower().endswith(IMAGE_EXTENSIONS):
            continue

        file_path = os.path.join(current_dir, filename)

        try:
            with Image.open(file_path) as img:
                # 统一转换为 RGBA 模式以支持透明通道
                img = img.convert("RGBA")
                width, height = img.size

                # 1. 微幅放大图片（消除四周镂空，确保正圆切面全满）
                new_w = int(width * SCALE_RATIO)
                new_h = int(height * SCALE_RATIO)
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # 2. 从中心居中裁剪回原图尺寸 (比如 128x128)
                left = (new_w - width) // 2
                top = (new_h - height) // 2
                right = left + width
                bottom = top + height
                img_cropped = img_resized.crop((left, top, right, bottom))

                # 3. 创建极高精度的圆形抗锯齿蒙版 (4倍超采样渲染)
                scale_up = 4
                mask_size = (width * scale_up, height * scale_up)
                mask = Image.new("L", mask_size, 0)
                draw = ImageDraw.Draw(mask)
                draw.ellipse((0, 0, mask_size[0], mask_size[1]), fill=255)

                # 将蒙版缩放回原始尺寸（得到非常平滑无锯齿的边缘）
                mask = mask.resize((width, height), Image.Resampling.LANCZOS)

                # 4. 应用蒙版生成最终的正圆图标
                circular_img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                circular_img.paste(img_cropped, (0, 0), mask=mask)

                # 5. 保存为 PNG 格式到新文件夹
                base_name = os.path.splitext(filename)[0]
                save_path = os.path.join(output_dir, f"{base_name}.png")
                circular_img.save(save_path, "PNG")

                print(f"处理成功: {filename} -> {OUTPUT_DIR_NAME}/{base_name}.png")
                renamed_count += 1

        except Exception as e:
            print(f"跳过/处理失败 {filename}: {e}")

    print(f"\n全部完成！共将 {renamed_count} 个图标裁切为正圆并保存至 '{OUTPUT_DIR_NAME}' 目录。")

if __name__ == "__main__":
    crop_to_circle()
