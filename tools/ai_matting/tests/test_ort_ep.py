"""推理后端选择(tools/ort_ep)的行为测试:GPU 优先、按模型白名单、失败回退 CPU。

不需要显卡:可用提供器与 rembg 的建会话函数都在测试里被替换。

运行:
    python tools/ai_matting/tests/test_ort_ep.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import rembg  # noqa: E402

from tools import ort_ep  # noqa: E402


def reset():
    ort_ep._sessions.clear()
    ort_ep._broken.clear()
    os.environ.pop("ATK_ORT_PROVIDERS", None)


def with_env(value):
    os.environ["ATK_ORT_PROVIDERS"] = value


def test_cpu_only_model_never_uses_gpu():
    reset()
    with_env("dml")
    assert ort_ep.providers_for("birefnet-general") == ["CPUExecutionProvider"]
    reset()
    assert ort_ep.providers_for("birefnet-general") == ["CPUExecutionProvider"]


def test_forced_cpu():
    reset()
    with_env("cpu")
    assert ort_ep.providers_for("isnet-general-use") == ["CPUExecutionProvider"]
    # 别名与大小写
    with_env("  CPU ")
    assert ort_ep.providers_for("isnet-general-use") == ["CPUExecutionProvider"]


def test_forced_gpu_chain():
    reset()
    with_env("dml")
    assert ort_ep.providers_for("isnet-general-use") == [
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]
    reset()
    with_env("DirectML, cuda")
    assert ort_ep.providers_for("u2net") == [
        "DmlExecutionProvider",
        "CPUExecutionProvider",
    ]


def test_auto_prefers_directml_then_cuda():
    reset()
    ort_ep._available = lambda: {"DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"}
    try:
        assert ort_ep.providers_for("isnet-general-use")[0] == "DmlExecutionProvider"
        ort_ep._broken.add("DmlExecutionProvider")
        assert ort_ep.providers_for("isnet-general-use")[0] == "CUDAExecutionProvider"
        ort_ep._broken.add("CUDAExecutionProvider")
        assert ort_ep.providers_for("isnet-general-use") == ["CPUExecutionProvider"]
    finally:
        ort_ep._available = lambda: set(ort_ep.ort.get_available_providers())


def test_session_falls_back_and_remembers():
    """GPU 建会话失败 → 记一次 broken,同进程后续直接走 CPU,不再重试。"""
    reset()
    with_env("dml")
    calls = []

    class FakeInner:
        @staticmethod
        def get_providers():
            return ["CPUExecutionProvider"]

    class FakeSession:
        inner_session = FakeInner()

    def fake_new_session(model, providers=None, **kwargs):
        calls.append(list(providers or []))
        if (providers or ["CPUExecutionProvider"])[0] != "CPUExecutionProvider":
            raise RuntimeError("DmlExecutionProvider 不可用")
        return FakeSession()

    original = rembg.new_session
    rembg.new_session = fake_new_session
    try:
        logs = []
        sess = ort_ep.session("isnet-general-use", log=logs.append)
        assert calls[0] == ["DmlExecutionProvider", "CPUExecutionProvider"], calls
        assert calls[1] == ["CPUExecutionProvider"], calls
        assert "DmlExecutionProvider" in ort_ep._broken
        assert ort_ep.device(sess) == "CPU"
        assert any("回退 CPU" in line for line in logs), logs

        # 再来一次:直接用缓存/CPU,不再尝试 GPU
        before = len(calls)
        ort_ep.session("isnet-general-use")
        assert len(calls) == before, calls
    finally:
        rembg.new_session = original


def test_device_labels():
    reset()

    class Inner:
        def __init__(self, providers):
            self._providers = providers

        def get_providers(self):
            return self._providers

    class Session:
        def __init__(self, providers):
            self.inner_session = Inner(providers)

    assert ort_ep.device(Session(["DmlExecutionProvider", "CPUExecutionProvider"])) == "DirectML(GPU)"
    assert ort_ep.device(Session(["CUDAExecutionProvider", "CPUExecutionProvider"])) == "CUDA(GPU)"
    assert ort_ep.device(Session(["CPUExecutionProvider"])) == "CPU"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    reset()
    print(f"OK, {len(tests)} 项推理后端选择测试通过")
