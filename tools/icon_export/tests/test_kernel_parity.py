"""差分测试:图标拆分的 Rust 移植与 Python 原实现,同一批输入必须完全一致。

`tools/icon_export/core.py` 被 rust-anything 用带标记的代码块接到 PyO3 扩展上,
`RUST_ANYTHING_MODE=old` 会走 Python 原实现。本测试在同一进程里分别加载两条路径比较:
连通域外接框逐个相同,且 `segment_icons` 拆出的图标逐个逐字节相同。

运行:
    python tools/icon_export/tests/test_kernel_parity.py
"""
from __future__ import annotations

import importlib
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.icon_export import core  # noqa: E402


def load_kernel(mode):
    os.environ["RUST_ANYTHING_MODE"] = mode
    try:
        importlib.reload(core)
    finally:
        os.environ.pop("RUST_ANYTHING_MODE", None)
    return core


def images():
    """(名称, RGBA 图):覆盖多连通域、单大块、碎块、细条、空图与阈值边界。"""
    out = {}

    im = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((4, 4, 28, 28), fill=(255, 0, 0, 255))
    d.rectangle((34, 34, 58, 58), fill=(0, 255, 0, 255))
    out["两块"] = im

    im = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for row in range(2):
        for col in range(2):
            x, y = col * 48 + 6, row * 48 + 6
            d.ellipse((x, y, x + 34, y + 34), fill=(40, 90, 200, 255))
    out["2x2"] = im

    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((5, 5, 94, 94), fill=(210, 120, 40, 255))
    out["单大块"] = im

    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i in range(12):
        x, y = (i * 7) % 56, (i * 11) % 56
        d.rectangle((x, y, x + 2, y + 2), fill=(255, 255, 255, 255))
    d.rectangle((8, 20, 40, 52), fill=(20, 40, 200, 255))
    out["碎块+图标"] = im

    im = Image.new("RGBA", (186, 186), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((1, 1, 160, 160), fill=(255, 255, 255, 255))     # 2% 阈值基准
    d.rectangle((162, 1, 183, 23), fill=(255, 0, 0, 255))        # 506 px → 滤掉
    d.rectangle((162, 30, 185, 54), fill=(0, 255, 0, 255))       # 600 px → 保留
    d.rectangle((162, 60, 182, 80), fill=(0, 0, 255, 255))       # 441 px → 滤掉
    out["阈值边界"] = im

    im = Image.new("RGBA", (64, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in range(4, 60, 12):
        d.rectangle((x, 4, x + 1, 19), fill=(255, 0, 0, 255))
    out["细条"] = im

    out["空图"] = Image.new("RGBA", (16, 16), (0, 0, 0, 0))

    arr = np.zeros((40, 40, 4), dtype=np.uint8)
    arr[..., :3] = 180
    arr[..., 3] = np.clip(np.arange(40, dtype=np.int16)[None, :] * 7, 0, 255).astype(np.uint8)
    out["Alpha 渐变"] = Image.fromarray(arr, "RGBA")

    for seed, density in ((11, 0.5), (12, 0.2), (13, 0.9)):
        rng = np.random.default_rng(seed)
        noise = np.zeros((72, 72, 4), dtype=np.uint8)
        noise[..., :3] = rng.integers(0, 256, (72, 72, 3), dtype=np.uint8)
        noise[..., 3] = np.where(rng.random((72, 72)) < density, 255, 0).astype(np.uint8)
        out[f"随机{seed}"] = Image.fromarray(noise, "RGBA")
    return out


def test_boxes_match():
    python_boxes = load_kernel("old").segment_component_boxes
    cases = [(name, img.tobytes(), img.width, img.height) for name, img in images().items()]
    expected = [(name, python_boxes(data, width, height)) for name, data, width, height in cases]

    rust_box = load_kernel("new").segment_component_boxes
    assert "icon_export_rs" in getattr(rust_box, "__module__", ""), (
        f"预期调用 Rust 内核,实际是 {rust_box.__module__};先运行 "
        "rust-anything build rust/icon-export-rs"
    )

    mismatches = [(name, want, rust_box(data, width, height))
                  for (name, want), (_n, data, width, height) in zip(expected, cases)
                  if want != rust_box(data, width, height)]
    assert not mismatches, "\n".join(
        f"{name}: python={want!r} rust={got!r}" for name, want, got in mismatches[:3]
    )
    return len(expected)


def test_icons_match():
    python_icons = load_kernel("old").segment_icons
    expected = {name: [(img.size, img.tobytes()) for img in python_icons(img.copy())]
                for name, img in images().items()}
    rust_icons = load_kernel("new").segment_icons
    for name, img in images().items():
        got = [(icon.size, icon.tobytes()) for icon in rust_icons(img.copy())]
        assert got == expected[name], f"{name}: 拆出的图标不一致"


def test_invalid_inputs_raise_the_same_error():
    python_box = load_kernel("old").segment_component_boxes
    rust_box = load_kernel("new").segment_component_boxes

    def call(fn, *args):
        try:
            return ("ok", fn(*args))
        except Exception as error:  # noqa: BLE001 - 两侧异常类型与文案都要一致
            return ("error", type(error).__name__, str(error))

    for args in ((b"", 1, 1), (b"\x01\x02\x03", 2, 2), (b"\x00\x00\x00\x00", 0, 1)):
        assert call(rust_box, *args) == call(python_box, *args), args


if __name__ == "__main__":
    total = test_boxes_match()
    test_icons_match()
    test_invalid_inputs_raise_the_same_error()
    print(f"parity OK: {total} 张图,连通域与拆分结果均与 Python 原实现一致")
