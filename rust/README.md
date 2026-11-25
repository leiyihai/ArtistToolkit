# Rust 内核(rust-anything)

本目录是用 [rust-anything](https://github.com/erkamyaman/rust-anything) 把 ArtistToolkit 的
纯计算内核逐块移植到 Rust 的产物。**不是**重写整个应用:Electron 界面、Python 编排、
PIL/OpenCV/ONNX/Blender 这些「IO 与三方库」继续留在 Python,只把「字节/数字进 → 字节/数字出」
的纯函数搬到 Rust,行为由录制用例逐值校验。

## 已移植

| 内核 | 源位置 | crate | 作用 | 录制 | 实测加速 |
| --- | --- | --- | --- | ---: | --- |
| `unmult_rgba` | `tools/unmult/core.py` | [unmult-rs](unmult-rs) | 去底:反预乘 + 3×3 去边 | 291 | 约 21×(内核) |
| `segment_component_boxes` | `tools/icon_export/core.py` | [icon-export-rs](icon-export-rs) | Alpha 连通域 + 外接框(替代 scipy 标号 + 每个连通域全图扫描) | 156 | 约 3.9×(内核) |

端到端(含 PIL 读写与未移植部分,`RUST_ANYTHING_MODE=new` vs `old`,输出逐字节一致):

| 场景 | Python | Rust | 加速 |
| --- | ---: | ---: | ---: |
| 图标批处理:1600×1600 图集、100 个图标、两种尺寸、圆角方形 | 1.310 s | 0.575 s | **2.28×** |
| 去底:1024×1024、黑底、defringe=0.5 | 0.307 s | 0.065 s | **4.72×** |

进度与待移植单位见 [PORT_MAP.md](PORT_MAP.md);逐单位排序的迁移计划见
[../docs/rust-migration-plan.md](../docs/rust-migration-plan.md)。

## 接线方式

`enable` 会在源文件的末尾插入一段带标记的代码块(`# >>> rust-anything: <crate> is on`),
从 `<repo>/rust/<crate>/python` 导入扩展并覆盖同名函数。于是:

- 调用方与界面**零改动**,`core.py` 里的 `process_batch` 继续用 Python 写;
- `RUST_ANYTHING_MODE=old` 或 `RUST_ANYTHING_UNIT_<NAME>=original` 可临时回到 Python 实现;
- 扩展不存在(未编译 / 打包漏带)时静默回退 Python,不会让应用起不来;
- `rust-anything disable <crate>` 精确删除该块,源文件恢复原样。

## 新增一个内核的流程

```sh
# 0) 在 Python 侧把计算抽成纯函数:参数/返回值只用 bytes/int/float/str/bool/list[int],
#    不接收 PIL.Image、numpy 数组或回调(桥接无法跨界),错误消息写成固定文案。
python -m pytest tools/<name>/tests -q     # 有测试就先跑

rust-anything analyze .                     # 确认单位与可移植性
rust-anything bridge . tools/<name>/ --keep "<不可移植函数>: <原因>"
#   然后在 rust/<crate>/src/port.rs 写 Rust 实现

rust-anything record rust/<crate> --count 120 --inputs rust/<crate>/inputs.jsonl
rust-anything build  rust/<crate>
rust-anything diff   rust/<crate>           # 必须 N/N
rust-anything gate   rust/<crate>           # fmt/clippy/test/panic/行为
rust-anything bench  rust/<crate>
rust-anything enable rust/<crate>
rust-anything map . --write                 # 刷新 PORT_MAP.md
rust-anything report rust/<crate>           # REPORT.md + card.svg
```

### 约定(踩过的坑)

1. **类型必须可跨界**:Python 侧只暴露标量与 `bytes`/`list[int]`。numpy 数组、PIL 对象、回调
   都会让 `bridge` 拒绝整个导出。
2. **纯函数、无 IO**:文件读写、模型推理留在 Python,内核只处理内存里的数据。
3. **确定性输出**:连通域这类顺序不稳定的结果,在 Python 与 Rust 两侧都按固定键排序
   (如 `(y1,x1,y2,x2)`),`diff` 才能逐值比对;下游若再次排序,则行为不受影响。
4. **错误文案要一致**:`diff` 把 `ValueError: ...` 当返回值比较,两边文案必须逐字相同。
5. **浮点要按原顺序复刻**:numpy 的 float32 逐元素运算顺序、`np.round`(四舍六入五成双)
   在 Rust 里要一一对应,否则 `diff` 会在舍入边界上翻车。
6. **录制要用真实输入**:生成器只会造小随机值(多半落在报错分支),关键分支要写进
   `record_cases.py`(阈值边界、空图、超大块、错误路径)。

## 验证

```sh
rust-anything diff  rust/unmult-rs && rust-anything gate rust/unmult-rs
rust-anything diff  rust/icon-export-rs && rust-anything gate rust/icon-export-rs
rust-anything fuzz  rust/unmult-rs --time 20        # 新种子输入,查录制没覆盖的分歧
rust-anything fuzz  rust/icon-export-rs --time 20
python tools/unmult/tests/test_kernel_parity.py     # 同进程比较 Rust 与 Python 两条路径
python tools/icon_export/tests/test_kernel_parity.py
```

## 打包

`ArtistToolkit-backend.spec` 里的 `rust_extension_datas()` 会把
`rust/<crate>/python/<module>` 按原相对路径收进 PyInstaller 包,所以
`dist/ArtistToolkit-backend.exe` 里也走 Rust;若某个 `.pyd` 没编译,spec 自动跳过,exe 回退 Python。

验证包内确实加载了 Rust(缺扩展时该命令会直接失败,而不是静默回退):

```sh
echo {"id":1,"cmd":"selftest"} | RUST_ANYTHING_MODE=new dist/ArtistToolkit-backend.exe
```

## 不适用的迁移

- `rembg` / ONNX 推理:模型与运行时都在 Python 侧,没有可移植的纯计算内核。
- `PIL` 的 LANCZOS 重采样(`resize_image`、`crop_icon`、`_fit_square`):要与 PIL 逐字节一致
  就得复刻其重采样实现,收益远小于风险。
- Blender 烘焙(`img2box`):外部进程,Python 只做编排。
