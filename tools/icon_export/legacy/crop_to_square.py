import os
from PIL import Image

# ========== 配置项 ==========
# 导出的目标文件夹名称（会在当前目录下自动创建）
OUTPUT_DIR_NAME = "square_icons"

# 目标正方形边长（像素）
SQUARE_SIZE = 128

# 放大比例（解决边缘少量镂空/半透明的问题）
# 1.05 代表放大 5%，1.1 代表放大 10%
# 图标边缘空缺较多时，可以适度调大此数值（推荐 1.05 ~ 1.10）
SCALE_RATIO = 1.08

# 支持的图片格式
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp')
# ============================

def crop_to_square():
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

                # 1. 等比放大：以最小边为基准撑满 SQUARE_SIZE，再乘 SCALE_RATIO 消除边缘镂空
                scale = (SQUARE_SIZE / min(width, height)) * SCALE_RATIO
                new_w = max(int(width * scale), SQUARE_SIZE)
                new_h = max(int(height * scale), SQUARE_SIZE)
                img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                # 2. 从中心居中裁剪出 SQUARE_SIZE x SQUARE_SIZE
                left = (new_w - SQUARE_SIZE) // 2
                top = (new_h - SQUARE_SIZE) // 2
                img_cropped = img_resized.crop((left, top, left + SQUARE_SIZE, top + SQUARE_SIZE))

                # 3. 保存为 PNG 格式到新文件夹
                base_name = os.path.splitext(filename)[0]
                save_path = os.path.join(output_dir, f"{base_name}.png")
                img_cropped.save(save_path, "PNG")

                print(f"处理成功: {filename} ({width}x{height}) -> {OUTPUT_DIR_NAME}/{base_name}.png")
                renamed_count += 1

        except Exception as e:
            print(f"跳过/处理失败 {filename}: {e}")

    print(f"\n全部完成！共将 {renamed_count} 个图标裁切为 {SQUARE_SIZE}x{SQUARE_SIZE} 并保存至 '{OUTPUT_DIR_NAME}' 目录。")

if __name__ == "__main__":
    crop_to_square()
