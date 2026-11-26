"""ONNX Runtime 执行提供器选择:Windows 上优先 DirectML(GPU),不可用时回退 CPU。

为什么单独成模块:三处抠图(icon_export / ai_matting)共用同一个 session,
而 rembg 的 `new_session` 只会自动挑 CUDA/ROCM,不会挑 DirectML;
不显式传 providers 时,装了 onnxruntime-directml 也仍然跑 CPU。

实测(RTX 4060,1024×1024,rembg.remove):
    isnet-general-use   CPU 0.64 s → DirectML 0.13 s
    u2net               CPU 0.26 s → DirectML 0.04 s
    birefnet-general    DirectML 上融合节点直接报错(DmlFusedNode),必须留在 CPU。

环境变量 ATK_ORT_PROVIDERS 覆盖自动选择:
    cpu                    强制 CPU
    dml / directml         强制 DirectML(GPU)
    cuda / rocm            强制对应提供器
    DmlExecutionProvider,CPUExecutionProvider   直接给完整链
显式值也走同一套回退:GPU 建会话失败时记一次日志,之后本进程都用 CPU。
"""
from __future__ import annotations

import os

import onnxruntime as ort

__all__ = ["CPU_ONLY", "providers_for", "session", "device", "summary"]

# DirectML 跑不了、且失败后会让同进程后续会话一起回退 CPU 的模型。
CPU_ONLY = frozenset({"birefnet-general"})

_ALIASES = {
    "dml": "DmlExecutionProvider",
    "directml": "DmlExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "rocm": "ROCMExecutionProvider",
    "cpu": "CPUExecutionProvider",
}
_GPU_ORDER = ("DmlExecutionProvider", "CUDAExecutionProvider", "ROCMExecutionProvider")
_LABELS = {
    "DmlExecutionProvider": "DirectML(GPU)",
    "CUDAExecutionProvider": "CUDA(GPU)",
    "ROCMExecutionProvider": "ROCm(GPU)",
    "CPUExecutionProvider": "CPU",
}

_sessions: dict[tuple[str, tuple[str, ...]], object] = {}
_broken: set[str] = set()  # 本进程里已确认不可用的提供器


def _available() -> set[str]:
    try:
        return set(ort.get_available_providers())
    except Exception:  # noqa: BLE001 - 缺 DLL 时 get_available_providers 也可能抛
        return set()


def providers_for(model: str) -> list[str]:
    """该模型该用的提供器链(首选在前,CPU 兜底)。"""
    if model in CPU_ONLY:
        return ["CPUExecutionProvider"]

    forced = os.environ.get("ATK_ORT_PROVIDERS", "").strip()
    chain: list[str] = []
    if forced:
        for raw in forced.split(","):
            name = _ALIASES.get(raw.strip().lower(), raw.strip())
            if name and name not in chain:
                chain.append(name)
    else:
        available = _available()
        chain = [p for p in _GPU_ORDER if p in available]

    chain = [p for p in chain if p not in _broken and p != "CPUExecutionProvider"]
    if not chain:
        return ["CPUExecutionProvider"]
    return [chain[0], "CPUExecutionProvider"]


def session(model: str, log=None):
    """按模型取(并缓存)一个推理 session;GPU 建不起来时回退 CPU。"""
    chain = providers_for(model)
    key = (model, tuple(chain))
    cached = _sessions.get(key)
    if cached is not None:
        return cached

    from rembg import new_session

    try:
        sess = new_session(model, providers=chain)
    except Exception as exc:  # noqa: BLE001 - ORT 的报错常带乱码,统一兜住
        if chain[0] == "CPUExecutionProvider":
            raise
        _broken.add(chain[0])
        if log:
            log(f"  {_LABELS.get(chain[0], chain[0])} 建会话失败,已回退 CPU({exc})")
        return session(model, log)

    used = list(sess.inner_session.get_providers())
    if chain[0] != "CPUExecutionProvider" and chain[0] not in used:
        # ORT 在提供器加载失败时会静默退回 CPU
        _broken.add(chain[0])
        if log:
            log(f"  {_LABELS.get(chain[0], chain[0])} 不可用,已回退 CPU")
    _sessions[key] = sess
    return sess


def device(sess) -> str:
    """session 实际在用的设备名。"""
    try:
        used = list(sess.inner_session.get_providers())
    except Exception:  # noqa: BLE001
        return "CPU"
    for provider in used:
        if provider != "CPUExecutionProvider":
            return _LABELS.get(provider, provider)
    return "CPU"


def summary() -> str:
    """给日志/自检用的一行环境说明。"""
    available = sorted(_available())
    return f"onnxruntime {ort.__version__},可用提供器 {available}"


def status() -> dict:
    """当前进程的推理后端状态(已建会话的实际设备、已确认坏掉的提供器)。"""
    return {
        "onnxruntime": ort.__version__,
        "available": sorted(_available()),
        "unavailable": sorted(_broken),
        "sessions": {model: device(sess) for (model, _chain), sess in _sessions.items()},
        "forced": os.environ.get("ATK_ORT_PROVIDERS", ""),
    }
