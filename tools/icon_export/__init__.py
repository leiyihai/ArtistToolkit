"""图标批处理模块:核心接口导出(GPUI 版只依赖 core,不再有 Tkinter 页面类)。"""

from .core import CROP_TYPES, process_batch, selftest

__all__ = ["CROP_TYPES", "process_batch", "selftest"]
