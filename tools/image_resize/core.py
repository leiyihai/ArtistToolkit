"""批量图片缩放核心逻辑:递归扫描 → 精确缩放(拉伸到目标尺寸)→ 保持目录结构输出。

移植自 batch_images_rust(src/scanner.rs / resizer.rs / build_path.rs),算法语义保持一致。
"""
import os
import gc
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PIL import Image

__all__ = ["process"]

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def scan_images(input_dir):
    """递归扫描目录下的 jpg/png/jpeg,返回绝对路径列表(保持目录结构)。"""
    paths = []
    for root, _dirs, files in os.walk(input_dir):
        for name in files:
            if name.lower().endswith(IMAGE_EXTS):
                paths.append(os.path.join(root, name))
    return paths


def map_output_paths(images, input_dir, output_dir):
    """把输入路径映射到输出目录下的相同相对结构;无法映射的丢弃。"""
    out = []
    for img in images:
        try:
            rel = os.path.relpath(img, input_dir)
        except ValueError:  # 不同盘符等无法映射
            continue
        out.append(os.path.join(output_dir, rel))
    return out


def resize_image(src, dst, width, height):
    """单张:精确缩放到 width×height(Lanczos3,拉伸,与 Rust resize_exact 一致)。"""
    with Image.open(src) as img:
        if img.mode in ("RGBA", "LA", "P") and dst.lower().endswith((".jpg", ".jpeg")):
            img = img.convert("RGB")  # JPEG 不支持透明通道
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        resized = img.resize((width, height), Image.Resampling.LANCZOS)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    resized.save(dst)


def process(input_dir, output_dir, width, height, log=print, progress=None, cancel=None):
    """主流程:扫描 → 映射 → 并行缩放。

    progress(done, total) 每完成一张回调一次;cancel(threading.Event) 置位后跳过剩余任务。
    """
    input_dir = os.path.abspath(input_dir)
    output_dir = os.path.abspath(output_dir)
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        raise ValueError("尺寸必须为正整数")
    if os.path.normcase(input_dir) == os.path.normcase(output_dir):
        raise ValueError("输入和输出不能是同一文件夹")

    images = scan_images(input_dir)
    if not images:
        raise ValueError("未找到图片文件(jpg/png/jpeg)")
    new_images = map_output_paths(images, input_dir, output_dir)
    if not new_images:
        raise ValueError("没有文件能映射到输出目录(输入与输出结构不兼容)")
    if len(new_images) < len(images):
        log(f"警告:{len(images) - len(new_images)} 个文件路径无法映射,将处理其余 {len(new_images)} 个")

    total = len(new_images)
    log(f"扫描到 {len(images)} 张图片,开始缩放 {total} 张到 {width}×{height}…")
    done = 0
    succeeded = 0
    with ThreadPoolExecutor(max_workers=min(32, os.cpu_count() or 4)) as pool:
        futures = {
            pool.submit(resize_image, src, dst, width, height): i
            for i, (src, dst) in enumerate(zip(images, new_images))
        }
        for fut in as_completed(futures):
            if cancel is not None and cancel.is_set():
                log("已取消,停止处理剩余图片")
                for f in futures:
                    f.cancel()
                break
            done += 1
            try:
                fut.result()
                succeeded += 1
            except Exception as e:
                log(f"  !! {os.path.basename(new_images[futures[fut]])}: {e}")
            if progress:
                progress(done, total)
            gc.collect()
    log(f"完成:成功 {succeeded}/{total} 张,输出到 {output_dir}")


def selftest():
    """自检:缩放尺寸精确 + 目录结构映射 + 同目录防呆。返回 (ok, message)。"""
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            src_dir = os.path.join(tmp, "in", "sub")   # a.jpg 放在子目录 sub 下
            os.makedirs(src_dir)
            Image.new("RGB", (100, 80), (255, 0, 0)).save(os.path.join(src_dir, "a.jpg"))
            out_dir = os.path.join(tmp, "out")
            process(os.path.join(tmp, "in"), out_dir, 32, 64, log=lambda m: None)
            out_file = os.path.join(out_dir, "sub", "a.jpg")
            if not os.path.exists(out_file):
                return False, "输出应保持相对目录结构 sub/a.jpg"
            if Image.open(out_file).size != (32, 64):
                return False, "缩放尺寸应精确匹配"
            try:
                process(os.path.join(tmp, "in"), os.path.join(tmp, "in"), 32, 32)
                return False, "应拒绝输入输出同目录"
            except ValueError:
                pass
        return True, "OK"
    except Exception as e:
        return False, str(e)


if __name__ == "__main__":
    ok, msg = selftest()
    print("core self-check:", msg)
    raise SystemExit(0 if ok else 1)
