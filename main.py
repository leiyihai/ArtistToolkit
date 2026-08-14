"""Artist Toolkit - 左侧页签工具集主界面(外壳)。

每个 TAB 页 = tools/ 下一个自包含功能文件夹(如 tools/icon_export)。
新增脚本功能 = 新建 tools/<name>/ 并提供页面类,然后在 build_pages() 注册。
"""
import sys

import tkinter as tk
from tkinter import messagebox

from tkinterdnd2 import TkinterDnD

from tools.icon_export import ExportPage, selftest

# Windows 高分屏清晰度
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

APP_TITLE = "Artist Toolkit"


class Sidebar(tk.Frame):
    """左侧页签栏:一个按钮列表 + 右侧内容区,后续新脚本功能注册到这里即可。"""

    def __init__(self, master):
        super().__init__(master, bg="#ececec")
        self._btns = []
        self._frames = []
        self._current = None

        self.content = tk.Frame(master, bg="#f5f5f5")
        # 左侧栏 + 1px 分隔线
        tk.Frame(self, width=1, bg="#c8c8c8").pack(side="right", fill="y")
        tk.Label(self, text=APP_TITLE, bg="#ececec", fg="#444",
                 font=("Microsoft YaHei UI", 11, "bold")).pack(fill="x", padx=12, pady=(14, 6))

    def add_page(self, title, frame):
        """注册一个页签。frame 的 master 应为 self.content。"""
        idx = len(self._frames)
        btn = tk.Button(self, text=title, relief="flat", anchor="w", bd=0,
                        padx=14, pady=10, bg="#ececec", activebackground="#dcdcdc",
                        font=("Microsoft YaHei UI", 10),
                        command=lambda i=idx: self.show(i))
        btn.pack(fill="x")
        self._btns.append(btn)
        self._frames.append(frame)
        if self._current is None:
            self.show(0)

    def show(self, idx):
        if self._current is not None:
            self._frames[self._current].pack_forget()
            self._btns[self._current].config(bg="#ececec", relief="flat")
        self._frames[idx].pack(fill="both", expand=True)
        self._btns[idx].config(bg="#ffffff", relief="sunken")
        self._current = idx


# ---------- 页签注册 ----------
def build_pages(sidebar):
    page = ExportPage(sidebar.content)
    sidebar.add_page("图标批处理", page)


def main():
    # 打包验证模式:windowed exe 无控制台,自检结果写入 _selftest.txt
    if "--selftest" in sys.argv:
        try:
            ok, msg = selftest()
        except Exception as e:
            import traceback
            ok, msg = False, f"{e}\n{traceback.format_exc()}"
        with open("_selftest.txt", "w", encoding="utf-8") as f:
            f.write(("OK\n" if ok else "FAIL\n") + str(msg))
        sys.exit(0 if ok else 1)

    root = TkinterDnD.Tk()
    root.title(APP_TITLE)
    root.geometry("880x660")
    root.minsize(760, 560)

    sidebar = Sidebar(root)
    sidebar.pack(side="left", fill="y")
    sidebar.content.pack(side="left", fill="both", expand=True)
    build_pages(sidebar)

    def on_close():
        for f in sidebar._frames:
            if isinstance(f, ExportPage) and f.running:
                if not messagebox.askyesno(APP_TITLE, "正在处理中,确定退出吗?"):
                    return
                break
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
