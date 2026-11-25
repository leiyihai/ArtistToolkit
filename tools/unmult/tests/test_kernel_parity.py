"""差分测试:去底内核的 Rust 移植与 Python 原实现,同一批输入必须逐字节一致。

`tools/unmult/core.py` 被 rust-anything 用一段带标记的代码块接到 PyO3 扩展上,
`RUST_ANYTHING_MODE=old` 会走 Python 原实现。本测试在同一进程里分别加载两条路径比较,
因此不依赖 git 历史,也不需要重新录制。

运行:
    python tools/unmult/tests/test_kernel_parity.py
装了 pytest 时也可以:
    python -m pytest tools/unmult/tests -q
"""
from __future__ import annotations

import importlib
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools.unmult import core  # noqa: E402


def load_kernel(mode):
    """按 rust-anything 的开关重新加载模块,返回其 unmult_rgba。"""
    os.environ["RUST_ANYTHING_MODE"] = mode
    try:
        importlib.reload(core)
    finally:
        os.environ.pop("RUST_ANYTHING_MODE", None)
    return core.unmult_rgba


def cases():
    """(名称, RGBA 字节, 宽, 高, 模式, 去边强度, 是否重建 Alpha)。"""
    rng = np.random.default_rng(20260101)
    out = []

    def add(name, arr, mode, strength=0.0, rebuild=False):
        height, width = arr.shape[:2]
        out.append((name, arr.tobytes(), int(width), int(height), mode, strength, rebuild))

    add("1x1 全黑", np.zeros((1, 1, 4), dtype=np.uint8), "black")
    add("1x1 全白", np.full((1, 1, 4), 255, dtype=np.uint8), "white")
    add("2x3 灰", np.full((3, 2, 4), 128, dtype=np.uint8), "black")
    # 黑底红块 / 白底灰块
    black = np.zeros((12, 16, 4), dtype=np.uint8)
    black[..., 3] = 255
    black[4:8, 5:11, :3] = (230, 40, 40)
    add("黑底红块", black, "black")
    add("黑底红块+去边", black, "black", 0.6)
    white = np.full((12, 16, 4), 255, dtype=np.uint8)
    white[4:8, 5:11, :3] = (76, 76, 76)
    add("白底灰块", white, "white")
    add("白底灰块+去边", white, "white", 1.0, True)
    # 半透明 / 近不透明 Alpha
    half = np.full((8, 8, 4), 120, dtype=np.uint8)
    half[..., :3] = (200, 90, 40)
    half[..., 3] = 128
    add("半透明", half, "black", 0.35)
    near = np.full((8, 8, 4), 200, dtype=np.uint8)
    near[2, 3, 3] = 254
    add("近不透明", near, "white", 0.5, True)
    add("近不透明-黑", near, "black", 0.5)
    # 行/列长度为 1 时 edge padding 的边界
    add("单行", rng.integers(0, 256, (1, 7, 4), dtype=np.uint8), "black", 0.9)
    add("单列", rng.integers(0, 256, (9, 1, 4), dtype=np.uint8), "white", 0.9)
    # 随机图(覆盖各种舍入边界)
    for index, (height, width) in enumerate([(4, 4), (8, 8), (17, 33), (48, 64)]):
        arr = rng.integers(0, 256, (height, width, 4), dtype=np.uint8)
        for mode in ("black", "white"):
            for strength in (0.0, 0.7):
                add(f"随机{index}-{height}x{width}-{mode}-{strength}", arr, mode, strength, index % 2 == 1)
    return out


def call(fn, case):
    _, data, width, height, mode, strength, rebuild = case
    try:
        return ("ok", fn(data, width, height, mode, strength, rebuild))
    except Exception as error:  # noqa: BLE001 - 两侧异常类型与文案都要一致
        return ("error", type(error).__name__, str(error))


def test_rust_matches_python():
    python_kernel = load_kernel("old")
    expected = [(case[0], call(python_kernel, case)) for case in cases()]

    rust_kernel = load_kernel("new")
    assert "unmult_rs" in getattr(rust_kernel, "__module__", ""), (
        f"预期调用 Rust 内核,实际是 {rust_kernel.__module__};先运行 "
        "rust-anything build rust/unmult-rs"
    )

    mismatches = []
    for (name, want), case in zip(expected, cases()):
        got = call(rust_kernel, case)
        if got != want:
            mismatches.append((name, want, got))
    assert not mismatches, "\n".join(
        f"{name}: python={want!r} rust={got!r}" for name, want, got in mismatches[:5]
    )
    return len(expected)


def test_invalid_inputs_raise_the_same_error():
    python_kernel = load_kernel("old")
    rust_kernel = load_kernel("new")
    bad = [
        (b"\x00\x00\x00\x00", 1, 1, "auto", 0.0, False),
        (b"\x00\x00\x00\x00", 0, 1, "black", 0.0, False),
        (b"", 1, 1, "black", 0.0, False),
        (b"\x00\x00\x00\x00", 1, 1, "black", float("nan"), False),
    ]
    for args in bad:
        want = call(python_kernel, ("", *args))
        got = call(rust_kernel, ("", *args))
        assert got == want, f"{args}: python={want!r} rust={got!r}"


if __name__ == "__main__":
    total = test_rust_matches_python()
    test_invalid_inputs_raise_the_same_error()
    print(f"parity OK: {total} 个用例,Rust 内核与 Python 内核逐字节一致")
