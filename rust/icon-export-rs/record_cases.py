"""Generate extra recording cases for `tools/icon_export/core.py::segment_component_boxes`.

Writes `inputs.jsonl` next to this script; `rust-anything record --inputs` replays it against the
Python original. Images stay small (the numbers cross as JSON) but keep every branch: several
components, one giant component, specks below the noise filters, thin lines, empty alpha, and the
500 px / 2% thresholds.

Run: python rust/icon-export-rs/record_cases.py
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inputs.jsonl")


def canvas(width, height):
    return Image.new("RGBA", (width, height), (0, 0, 0, 0))


def two_icons():
    im = canvas(60, 60)
    d = ImageDraw.Draw(im)
    d.rectangle((4, 4, 28, 28), fill=(255, 0, 0, 255))
    d.rectangle((34, 34, 58, 58), fill=(0, 255, 0, 255))
    return im


def grid_2x2():
    im = canvas(96, 96)
    d = ImageDraw.Draw(im)
    for row in range(2):
        for col in range(2):
            x, y = col * 48 + 6, row * 48 + 6
            d.ellipse((x, y, x + 34, y + 34), fill=(40, 90, 200, 255))
    return im


def giant_blob():
    im = canvas(100, 100)
    ImageDraw.Draw(im).ellipse((5, 5, 94, 94), fill=(210, 120, 40, 255))
    return im


def specks_and_icon():
    im = canvas(64, 64)
    d = ImageDraw.Draw(im)
    for i in range(12):
        x, y = (i * 7) % 56, (i * 11) % 56
        d.rectangle((x, y, x + 2, y + 2), fill=(255, 255, 255, 255))
    d.rectangle((8, 20, 40, 52), fill=(20, 40, 200, 255))
    return im


def threshold_edges():
    """同时覆盖 500 px 绝对阈值与「最大块 2%」相对阈值。

    最大块 160×160=25600 → 2% = 512:
      * 22×23=506  → 过 500 但不足 512,被 2% 规则滤掉
      * 24×25=600  → 两个阈值都过,保留
      * 21×21=441  → 不足 500,滤掉
    """
    im = canvas(186, 186)
    d = ImageDraw.Draw(im)
    d.rectangle((1, 1, 160, 160), fill=(255, 255, 255, 255))
    d.rectangle((162, 1, 183, 23), fill=(255, 0, 0, 255))
    d.rectangle((162, 30, 185, 54), fill=(0, 255, 0, 255))
    d.rectangle((162, 60, 182, 80), fill=(0, 0, 255, 255))
    return im

def checker():
    im = canvas(64, 64)
    d = ImageDraw.Draw(im)
    for y in range(0, 64, 8):
        for x in range(0, 64, 8):
            if (x // 8 + y // 8) % 2 == 0:
                d.rectangle((x, y, x + 7, y + 7), fill=(255, 255, 255, 255))
    return im


def thin_lines():
    im = canvas(64, 24)
    d = ImageDraw.Draw(im)
    for x in range(4, 60, 12):
        d.rectangle((x, 4, x + 1, 19), fill=(255, 0, 0, 255))
    return im


def alpha_gradient():
    arr = np.zeros((40, 40, 4), dtype=np.uint8)
    arr[..., :3] = 180
    arr[..., 3] = np.clip(np.arange(40, dtype=np.int16)[None, :] * 7, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def random_mask(seed, size=72, density=0.5):
    rng = np.random.default_rng(seed)
    arr = np.zeros((size, size, 4), dtype=np.uint8)
    arr[..., :3] = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
    arr[..., 3] = np.where(rng.random((size, size)) < density, 255, 0).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def main():
    images = {
        "two-icons": two_icons(),
        "grid-2x2": grid_2x2(),
        "giant-blob": giant_blob(),
        "specks": specks_and_icon(),
        "thresholds": threshold_edges(),
        "checker": checker(),
        "thin-lines": thin_lines(),
        "alpha-gradient": alpha_gradient(),
        "random-half": random_mask(11),
        "random-sparse": random_mask(12, density=0.2),
        "random-dense": random_mask(13, density=0.9),
        "empty-16": canvas(16, 16),
        "single-pixel": Image.fromarray(
            np.array([[[0, 0, 0, 0], [0, 0, 0, 11]], [[0, 0, 0, 255], [9, 9, 9, 10]]],
                     dtype=np.uint8), "RGBA"),
    }
    args = []
    for img in images.values():
        args.append([{"$bytes": list(img.tobytes())}, int(img.width), int(img.height)])
    args += [
        [{"$bytes": []}, 1, 1],
        [{"$bytes": [1, 2, 3]}, 0, 4],
        [{"$bytes": [1, 2, 3]}, -1, 4],
        [{"$bytes": [1, 2, 3]}, 2, 2],
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        for case in args:
            f.write(json.dumps({"fn": "segment_component_boxes", "args": case},
                               ensure_ascii=False) + "\n")
    print(f"wrote {len(args)} cases to {OUT}")


if __name__ == "__main__":
    main()

