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


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    reset_env()
    print(f"OK, {len(tests)} 项 alpha 精修测试通过")
