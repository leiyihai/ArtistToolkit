"""Generate extra recording cases for the Rust port of `tools/unmult/core.py::unmult_rgba`.

Writes `inputs.jsonl` next to this script. Each line is
{"fn": "unmult_rgba", "args": [{"$bytes": [...]}, width, height, mode, defringe, rebuild_alpha]}
which `rust-anything record --inputs inputs.jsonl` replays against the Python original.

Run: python rust/unmult-rs/record_cases.py
"""
from __future__ import annotations

import json
import os

import numpy as np

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inputs.jsonl")


def rgba(width, height, rgb, alpha):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = alpha
    return arr


def solid(width, height, color, alpha=255):
    return rgba(width, height, np.full((height, width, 3), color, dtype=np.uint8), alpha)


def black_blob(width=40, height=30, color=(230, 40, 40)):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., 3] = 255
    yy, xx = np.mgrid[0:height, 0:width]
    m = ((xx - width / 2) ** 2 / ((width / 3) ** 2) + (yy - height / 2) ** 2 / ((height / 3) ** 2)) <= 1
    arr[m, :3] = color
    return arr


def white_blob(width=40, height=30, color=(76, 76, 76)):
    arr = np.full((height, width, 4), 255, dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    m = ((xx - width / 2) ** 2 / ((width / 3) ** 2) + (yy - height / 2) ** 2 / ((height / 3) ** 2)) <= 1
    arr[m, :3] = color
    return arr


def gradient(width=16, height=16):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    ramp = np.linspace(0, 255, width, dtype=np.uint8)
    arr[..., 0] = ramp[None, :]
    arr[..., 1] = ramp[:, None]
    arr[..., 2] = 128
    arr[..., 3] = 255
    return arr


def noise(width=16, height=16, seed=7):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(height, width, 4), dtype=np.uint8)
    arr[..., 3] = 255
    return arr


def checker_alpha(width=33, height=17):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    arr[..., :3] = 190
    arr[..., 3] = np.where((xx // 3 + yy // 3) % 2 == 0, 255, 0).astype(np.uint8)
    return arr


def half_alpha(width=8, height=8):
    arr = np.full((height, width, 4), 120, dtype=np.uint8)
    arr[..., :3] = (200, 90, 40)
    arr[..., 3] = 128
    return arr


def near_opaque(width=8, height=8):
    arr = np.full((height, width, 4), 200, dtype=np.uint8)
    arr[..., :3] = (60, 140, 220)
    arr[..., 3] = 255
    arr[2, 3, 3] = 254  # alpha.min() = 254/255 < 0.999 → 保留给定 Alpha
    return arr


def main():
    images = {
        "1x1_black": solid(1, 1, 0),
        "1x1_white": solid(1, 1, 255),
        "2x3_black": solid(2, 3, 0),
        "4x4_zero": np.zeros((4, 4, 4), dtype=np.uint8),
        "8x8_full_white": np.full((8, 8, 4), 255, dtype=np.uint8),
        "8x8_black_blob": black_blob(8, 8),
        "8x8_white_blob": white_blob(8, 8),
        "40x30_black_blob": black_blob(),
        "40x30_white_blob": white_blob(),
        "16x16_gradient": gradient(),
        "16x16_noise": noise(),
        "33x17_checker": checker_alpha(),
        "8x8_half_alpha": half_alpha(),
        "8x8_near_opaque": near_opaque(),
        "6x5_tiny_corners": rgba(6, 5, np.full((5, 6, 3), 17, dtype=np.uint8),
                                 np.array([[0, 255, 0, 255, 0, 255]] * 5, dtype=np.uint8)),
    }
    args = []
    for name, arr in images.items():
        data = {"$bytes": list(arr.tobytes())}
        height, width = arr.shape[:2]
        for mode in ("black", "white"):
            for defringe_strength, rebuild in ((0.0, False), (0.7, False), (1.0, True), (0.35, True)):
                args.append([data, int(width), int(height), mode, defringe_strength, rebuild])
    # 边界与报错路径
    args += [
        [{"$bytes": [1, 2, 3]}, 0, 4, "black", 0.0, False],       # 尺寸为 0
        [{"$bytes": [1, 2, 3]}, -2, 4, "black", 0.0, False],      # 负尺寸
        [{"$bytes": []}, 1, 1, "black", 0.0, False],              # 长度不符(期望 4)
        [{"$bytes": [0, 0, 0, 0]}, 1, 1, "auto", 0.0, False],     # 未知模式
        [{"$bytes": [0, 0, 0, 0]}, 1, 1, "", 0.0, False],         # 空模式
        [{"$bytes": [0, 0, 0, 0]}, 1, 1, "BLACK", 0.0, False],    # 大小写不匹配
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        for case in args:
            f.write(json.dumps({"fn": "unmult_rgba", "args": case}, ensure_ascii=False) + "\n")
    print(f"wrote {len(args)} cases to {OUT}")


if __name__ == "__main__":
    main()
