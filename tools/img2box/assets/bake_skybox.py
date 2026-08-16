"""
Blender 烘焙脚本：将 HDRI PNG 烘焙到 Cube 的 "box" 贴图

用法（由主脚本调用）：
    blender hdri2box.blend --background --python bake_skybox.py -- <input_png> <output_png>
"""

import bpy
import sys
import os


def main():
    # 解析参数 (- 之后的是 Blender 传给脚本的参数)
    argv = sys.argv
    if "--" in argv:
        args = argv[argv.index("--") + 1:]
    else:
        print("错误: 缺少参数")
        print("用法: blender hdri2box.blend --background --python bake_skybox.py -- <input_png> <output_png>")
        return False

    if len(args) < 2:
        print("错误: 需要输入和输出路径")
        return False

    input_png = os.path.abspath(args[0])
    output_png = os.path.abspath(args[1])

    print(f"输入图片: {input_png}")
    print(f"输出图片: {output_png}")

    if not os.path.isfile(input_png):
        print(f"错误: 输入文件不存在: {input_png}")
        return False

    # ── 1. 更新世界环境的 Environment Texture ──
    world = bpy.context.scene.world
    env_tex = None
    for n in world.node_tree.nodes:
        if n.type == 'TEX_ENVIRONMENT':
            env_tex = n
            break

    if not env_tex:
        print("错误: 未找到 Environment Texture 节点")
        return False

    # 加载输入图片到 Blender
    old_img_name = env_tex.image.name if env_tex.image else "None"
    print(f"更新世界环境贴图: {old_img_name} -> {input_png}")

    # 加载新图片
    new_img = bpy.data.images.load(input_png, check_existing=True)
    env_tex.image = new_img
    print(f"  已设置为: {new_img.name}")

    # ── 2. 设置 Cube 和 "box" 纹理 ──
    cube = bpy.data.objects["Cube"]
    bpy.context.view_layer.objects.active = cube
    cube.select_set(True)

    # 获取 Cube 当前使用的材质（从材质槽取，不依赖名字）
    if not cube.material_slots:
        print("错误: Cube 没有材质槽")
        return False
    mat = cube.material_slots[0].material
    if not mat:
        print("错误: Cube 的材质槽为空")
        return False
    print(f"Cube 当前材质: {mat.name}")

    # 找到材质中的 Image Texture 节点（不依赖图片名）
    box_node = None
    for n in mat.node_tree.nodes:
        if n.type == 'TEX_IMAGE' and n.image:
            box_node = n
            break

    if not box_node:
        # 备用：从 bpy.data.images 中找
        print("材质中没有 Image Texture 节点，尝试查找 box 图片...")
        if 'box' in bpy.data.images:
            box_img = bpy.data.images['box']
        else:
            print(f"错误: 材质 '{mat.name}' 中没有 Image Texture 节点，也无 box 图片")
            return False
    else:
        box_img = box_node.image

    print(f"找到烘焙目标: 节点={box_node.name} 图片={box_img.name} ({box_img.generated_width}x{box_img.generated_height})")

    # 设节点为活动并选中
    mat.node_tree.nodes.active = box_node
    for n in mat.node_tree.nodes:
        n.select = False
    box_node.select = True
    # 设置纹理节点扩展模式为 EXTEND，避免 UV 边界接缝
    box_node.extension = 'EXTEND'

    # 确保图片尺寸合理
    bake_w = box_img.generated_width
    bake_h = box_img.generated_height
    print(f"烘焙目标尺寸: {bake_w} x {bake_h}")

    # 检查是否循环依赖（Image Texture 的图片 = 输入图片）
    # 如果是，创建临时空白图作为烘焙目标
    orig_img = None
    temp_img = None
    # 比较图片名称是否匹配输入文件名
    input_name = os.path.basename(input_png)
    if box_node and box_node.image and box_node.image.name.startswith(os.path.splitext(input_name)[0]):
        print("Image Texture 引用了输入图片，创建临时目标避免循环依赖")
        temp_img = bpy.data.images.new(
            name="__bake_target__",
            width=bake_w,
            height=bake_h,
            alpha=True,
            float_buffer=False,
        )
        orig_img = box_node.image
        box_node.image = temp_img
        box_img = temp_img

    # ── 3. 设置烘焙参数 ──
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.device = 'CPU'
    scene.render.bake.target = 'IMAGE_TEXTURES'
    scene.render.bake.margin = 16
    scene.render.bake.margin_type = 'ADJACENT_FACES'
    scene.render.bake.use_clear = True

    print(f"烘焙引擎: Cycles")
    print(f"烘焙类型: COMBINED")
    print(f"采样数: {scene.cycles.samples}")
    print(f"设备: {scene.cycles.device}")

    # ── 4. 执行烘焙 ──
    # Blender 5.x bake 支持 width/height;3.x/4.x 不支持(TypeError),回退兼容参数(尺寸由目标图片决定)
    print("开始烘焙...")
    try:
        bpy.ops.object.bake(
            type='COMBINED',
            margin=16,
            margin_type='ADJACENT_FACES',
            use_clear=True,
            width=box_img.generated_width,
            height=box_img.generated_height,
        )
    except TypeError:
        print("当前 Blender 版本 bake 不支持 width/height,改用兼容参数")
        bpy.ops.object.bake(
            type='COMBINED',
            margin=16,
            margin_type='ADJACENT_FACES',
            use_clear=True,
        )
    except Exception as e:
        print(f"烘焙失败: {e}")
        return False

    print("烘焙完成！")

    # ── 5. 保存烘焙结果 ──
    output_dir = os.path.dirname(output_png)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 如果用了临时图，把像素复制回原图
    if temp_img and orig_img:
        print("将烘焙结果写回原图...")
        orig_img.scale(bake_w, bake_h)
        pixels = list(temp_img.pixels)
        orig_img.pixels = pixels
        orig_img.update()
        box_node.image = orig_img
        bpy.data.images.remove(temp_img)
        box_img = orig_img

    # 保存为 PNG
    box_img.filepath_raw = output_png
    box_img.file_format = 'PNG'
    box_img.save()
    print(f"已保存: {output_png}")

    return True


if __name__ == "__main__":
    success = main()
    print(f"\n{'成功!' if success else '失败!'}")
    exit_code = 0 if success else 1
    sys.exit(exit_code)
