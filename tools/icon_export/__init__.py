"""批量图标导出 TAB 页(工具集的一个功能页,一个文件夹自包含)。

外部(入口 main.py)只从这里取页面类与核心接口。
"""
from .core import CROP_TYPES, process_batch, selftest
from .page import ExportPage

__all__ = ["CROP_TYPES", "process_batch", "selftest", "ExportPage"]
