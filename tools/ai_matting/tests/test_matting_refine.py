"""alpha 精修(tools/matting_refine)的行为测试:开关、收敛阈值、失败回退。

运行:
    python tools/ai_matting/tests/test_matting_refine.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from tools import matting_refine  # noqa: E402


def reset_env():
    for name in ("ATK_ALPHA_MATTING", "ATK_ALPHA_MATTING_RTOL"):
        os.environ.pop(name, None)


def test_matting_enabled_auto_threshold():
    reset_env()
    assert matting_refine.matting_enabled(1_000_000, 3_000_000) is True
    assert matting_refine.matting_enabled(4_000_000, 3_000_000) is False


def test_matting_enabled_overrides():
    reset_env()
    for value in ("off", "0", "FALSE", "no"):
        os.environ["ATK_ALPHA_MATTING"] = value
        assert matting_refine.matting_enabled(100, 3_000_000) is False, value
    for value in ("on", "1", "true", "YES"):
        os.environ["ATK_ALPHA_MATTING"] = value
        assert matting_refine.matting_enabled(10_000_000, 3_000_000) is True, value
    reset_env()


def test_rtol_default_and_override():
    reset_env()
    assert matting_refine.rtol() == 1e-5
    os.environ["ATK_ALPHA_MATTING_RTOL"] = "1e-4"
    assert matting_refine.rtol() == 1e-4
    os.environ["ATK_ALPHA_MATTING_RTOL"] = "not-a-number"
    assert matting_refine.rtol() == 1e-5
    os.environ["ATK_ALPHA_MATTING_RTOL"] = "-3"
    assert matting_refine.rtol() == 1e-5
    reset_env()


class _FakeSession:
    """返回固定掩膜的假 session,避免测试依赖模型。"""

    def __init__(self, mask):
        self._mask = mask

    def predict(self, _img):
        return [self._mask]


def _sample():
    img = Image.new("RGB", (96, 96), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.ellipse((24, 24, 72, 72), fill=(60, 120, 70))
    mask = Image.new("L", (96, 96), 0)
    ImageDraw.Draw(mask).ellipse((22, 22, 74, 74), fill=255)
    return img, mask


def test_refine_produces_rgba():
    img, mask = _sample()
    out = matting_refine.refine_cutout(img, _FakeSession(mask))
    assert out.size == img.size, out.size
    assert out.mode == "RGBA", out.mode
    alpha = np.asarray(out)[..., 3]
    assert alpha[0, 0] == 0, "背景应透明"
    assert alpha[48, 48] > 250, "主体应不透明"
    assert (alpha > 0).sum() > 0


def test_refine_falls_back_when_solver_fails():
    img, mask = _sample()
    original = matting_refine._refine
    logs = []

    def boom(*_args, **_kwargs):
        raise ValueError("退化 trimap")

    matting_refine._refine = boom
    try:
        out = matting_refine.refine_cutout(img, _FakeSession(mask), log=logs.append)
    finally:
        matting_refine._refine = original
    assert out.mode == "RGBA"
    alpha = np.asarray(out)[..., 3]
    assert alpha[0, 0] == 0 and alpha[48, 48] == 255, "回退时应得到普通抠图结果"
    assert any("回退" in line or "普通抠图" in line for line in logs), logs


def test_finish_hardens_interior():
    """图标内部半透明的区域应填实;关掉收边时边缘保持渐变。"""
    img = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((18, 18, 78, 78), fill=(40, 110, 60, 200))  # 内部只有 200
    out = matting_refine.finish(img)
    alpha = np.asarray(out)[..., 3]
    assert alpha[48, 48] == 255, f"内部应填实,实际 {alpha[48, 48]}"

    soft = np.asarray(matting_refine.finish(img, edge_contrast=False))[..., 3]
    assert soft[48, 48] == 255, "内部仍应填实"
    assert soft[18, 48] == 200, f"关掉收边后边缘应保持渐变,实际 {soft[18, 48]}"


def test_finish_narrows_edges_on_uniform_background():
    """纯色背景的素材图,边缘应收窄成 1px 过渡(手抠的观感)。"""
    img = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    for i, alpha in enumerate(range(20, 256, 20)):
        draw.rectangle((20 + i, 20 + i, 76 - i, 76 - i), fill=(40, 110, 60, alpha))
    before = np.asarray(img)[..., 3].astype(np.int16)
    after = np.asarray(matting_refine.finish(img))[..., 3].astype(np.int16)
    semi_before = int(((before > 16) & (before < 240)).sum())
    semi_after = int(((after > 16) & (after < 240)).sum())
    assert semi_after < semi_before / 2, (semi_before, semi_after)
    assert after[48, 48] == 255, "主体中心仍应不透明"


def test_finish_bleeds_foreground_color():
    """透明区保留背景白时,缩放会把白色拉进边缘;finish 应换成最近的前景色。"""
    img = Image.new("RGBA", (64, 64), (255, 255, 255, 0))  # 透明且 RGB 全是白
    draw = ImageDraw.Draw(img)
    draw.rectangle((24, 24, 40, 40), fill=(0, 0, 0, 255))  # 黑色方块
    out = matting_refine.finish(img)
    arr = np.asarray(out)
    outside = arr[22, 32]  # 方块外 2px
    assert outside[3] == 0, outside
    assert int(outside[:3].max()) < 40, f"透明区应吸收前景黑,实际 {outside[:3]}"
    assert arr[32, 32][3] == 255, "不透明像素不受影响"


def test_finish_empty_image():
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    out = matting_refine.finish(img)
    assert np.asarray(out)[..., 3].max() == 0


def test_finish_trims_fringe_on_uniform_background():
    """纯色背景下,轮廓外的半透明背景色应被压成透明。"""
    img = Image.new("RGBA", (96, 96), (252, 252, 252, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((28, 28, 68, 68), fill=(30, 120, 60, 255))
    # 轮廓外一圈白背景的半透明像素(模型掩膜常见的"灰白毛边")
    for i in range(4):
        draw.rectangle((28 - i - 1, 28 - i - 1, 68 + i + 1, 68 + i + 1), outline=(252, 252, 252, 60))
    before = np.asarray(img)[..., 3].astype(np.int16)
    out = matting_refine.finish(img)
    after = np.asarray(out)[..., 3].astype(np.int16)
    assert before[26, 48] > 40, "构造失败:边缘应有半透明像素"
    assert after[26, 48] < 10, f"背景色毛边应被压掉,实际 {after[26, 48]}"
    assert after[48, 48] == 255, "主体不受影响"


def test_finish_keeps_white_detail_on_white_background():
    """白底上的白色高光不能因为"像背景"被删掉。"""
    img = Image.new("RGBA", (96, 96), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle((20, 20, 76, 76), fill=(30, 120, 60, 255))
    draw.rectangle((40, 40, 56, 56), fill=(255, 255, 255, 255))  # 内部纯白
    out = matting_refine.finish(img)
    alpha = np.asarray(out)[..., 3]
    assert alpha[48, 48] == 255, f"内部白色高光应保留,实际 {alpha[48, 48]}"


def test_finish_skips_trim_on_busy_background():
    """背景不纯(照片类)时不做颜色去边,避免误删主体。"""
    rng = np.random.default_rng(0)
    busy = rng.integers(0, 255, (96, 96, 3), dtype=np.uint8)
    alpha = np.full((96, 96, 1), 120, dtype=np.uint8)
    img = Image.fromarray(np.concatenate([busy, alpha], axis=-1), "RGBA")

    background, spread = matting_refine.background_color(busy)
    assert background is None, f"噪声背景应判定为没有纯色背景,实际 spread={spread}"

    before = np.asarray(img)[..., 3].copy()
    out = matting_refine.finish(img, harden_px=0, bleed_px=0)
    assert np.array_equal(before, np.asarray(out)[..., 3]), "背景不纯时不应改动 alpha"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    reset_env()
    print(f"OK, {len(tests)} 项 alpha 精修测试通过")
