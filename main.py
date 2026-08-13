"""Artist Toolkit - 左侧页签工具集主界面。

当前页签:批量导出(拖图 → 选裁切类型/尺寸 → 选输出路径 → 运行)。
后续新增脚本功能 = 新增一个 build_xxx_page() 并注册到 PAGES。
"""
import os
import queue
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import core

# Windows 高分屏清晰度
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

APP_TITLE = "Artist Toolkit"
SIZES = (32, 64, 128, 256)
DEFAULT_DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
if not os.path.isdir(DEFAULT_DESKTOP):
    DEFAULT_DESKTOP = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
if not os.path.isdir(DEFAULT_DESKTOP):
    DEFAULT_DESKTOP = os.path.expanduser("~")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")


class ImageList(tk.Frame):
    """可滚动的缩略图网格(4 列),右键可移除单张。"""

    COLS = 4
    THUMB = 96

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change
        self.paths = []
        self._thumbs = []  # 保持 PhotoImage 引用,防 GC
        self._cards = []

        self.canvas = tk.Canvas(self, bg="#f2f2f2", highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.inner = tk.Frame(self.canvas, bg="#f2f2f2")
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._redraw()

    def add(self, path):
        path = os.path.normpath(path)
        if not path.lower().endswith(IMAGE_EXTS) or path in self.paths:
            return False
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((self.THUMB, self.THUMB))
        except Exception:
            return False
        self.paths.append(path)
        self._thumbs.append(ImageTk.PhotoImage(img))
        self._redraw()
        if self.on_change:
            self.on_change()
        return True

    def add_many(self, paths):
        added = sum(1 for p in paths if self.add(p))
        return added

    def remove(self, index):
        del self.paths[index]
        del self._thumbs[index]
        self._redraw()
        if self.on_change:
            self.on_change()

    def clear(self):
        self.paths.clear()
        self._thumbs.clear()
        self._redraw()
        if self.on_change:
            self.on_change()

    def _redraw(self):
        for c in self._cards:
            c.destroy()
        self._cards.clear()
        for i, path in enumerate(self.paths):
            card = tk.Frame(self.inner, bd=1, relief="solid", bg="white")
            tk.Label(card, image=self._thumbs[i], bg="white").pack(padx=2, pady=(2, 0))
            name = os.path.basename(path)
            tk.Label(card, text=name if len(name) <= 16 else name[:13] + "...",
                     bg="white", font=("Microsoft YaHei UI", 8)).pack(padx=2, pady=(0, 2))
            card.bind("<Button-3>", lambda e, idx=i: self._menu(idx))
            card.grid(row=i // self.COLS, column=i % self.COLS, padx=4, pady=4)
            self._cards.append(card)
        if not self.paths:
            tk.Label(self.inner, text="将图片拖到此处,或点击下方按钮选择",
                     bg="#f2f2f2", fg="#888", font=("Microsoft YaHei UI", 11)).grid(
                row=0, column=0, columnspan=self.COLS, pady=40)

    def _menu(self, index):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label=f"移除: {os.path.basename(self.paths[index])}",
                      command=lambda: self.remove(index))
        m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())


class ExportPage(ttk.Frame):
    """批量导出页:拖图 → 选裁切类型/尺寸 → 选输出路径 → 运行。"""

    def __init__(self, master):
        super().__init__(master, padding=12)
        self.q = queue.Queue()
        self.running = False

        self._build_dropzone()
        self._build_options()
        self._build_runbar()
        self._build_log()

        self.after(100, self._poll)

    # ---------- UI ----------
    def _build_dropzone(self):
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="1. 添加图片(支持单张/多张,PNG/JPG/WebP):",
                  font=("Microsoft YaHei UI", 10)).pack(anchor="w")

        self.image_list = ImageList(top, on_change=self._sync_state)
        self.image_list.pack(fill="both", expand=True, pady=(4, 8))
        self.image_list.canvas.drop_target_register(DND_FILES)
        self.image_list.canvas.dnd_bind("<<Drop>>", self._on_drop)

        btn = ttk.Frame(top)
        btn.pack(anchor="w")
        ttk.Button(btn, text="选择图片…", command=self._pick).pack(side="left")
        ttk.Button(btn, text="清空", command=self.image_list.clear).pack(side="left", padx=6)
        self.drop_hint = ttk.Label(top, text="", foreground="#666")
        self.drop_hint.pack(anchor="w", pady=(2, 0))

    def _build_options(self):
        box = ttk.LabelFrame(self, text="2. 输出选项", padding=10)
        box.pack(fill="x", pady=(4, 8))

        row = ttk.Frame(box)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="裁切类型(单选):").pack(side="left")
        self.crop_var = tk.StringVar(value="circle")
        for key, label in core.CROP_TYPES.items():
            ttk.Radiobutton(row, text=label, value=key, variable=self.crop_var).pack(side="left", padx=6)

        row2 = ttk.Frame(box)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="输出尺寸(可多选):").pack(side="left")
        self.size_vars = {s: tk.BooleanVar(value=(s == 128)) for s in SIZES}
        for s in SIZES:
            ttk.Checkbutton(row2, text=f"{s}×{s}", variable=self.size_vars[s]).pack(side="left", padx=6)

        row3 = ttk.Frame(box)
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="输出路径:").pack(side="left")
        self.out_var = tk.StringVar(value=DEFAULT_DESKTOP)
        ttk.Entry(row3, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(row3, text="浏览…", command=self._pick_dir).pack(side="left")

        row4 = ttk.Frame(box)
        row4.pack(fill="x", pady=2)
        self.normalize_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="统一图标视觉大小(跑完脚本后再运行 normalize)",
                        variable=self.normalize_var).pack(anchor="w")

    def _build_runbar(self):
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.run_btn = ttk.Button(bar, text="▶ 运行", command=self._start)
        self.run_btn.pack(side="left")
        self.progress = ttk.Progressbar(bar, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

    def _build_log(self):
        ttk.Label(self, text="运行日志:").pack(anchor="w")
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.log = tk.Text(wrap, height=8, state="disabled", font=("Consolas", 9),
                           wrap="word", bg="#1e1e1e", fg="#d4d4d4")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=vsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ---------- 交互 ----------
    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        added = self.image_list.add_many(paths)
        self.drop_hint.config(text=f"已添加 {added} 张图片" if added else "未添加(重复或格式不支持)")

    def _pick(self):
        files = filedialog.askopenfilenames(
            title="选择图片", filetypes=[("图片", "*.png *.jpg *.jpeg *.webp"), ("所有文件", "*.*")])
        if files:
            added = self.image_list.add_many(files)
            self.drop_hint.config(text=f"已添加 {added} 张图片")

    def _pick_dir(self):
        d = filedialog.askdirectory(title="选择输出保存路径", initialdir=self.out_var.get() or DEFAULT_DESKTOP)
        if d:
            self.out_var.set(d)

    def _sync_state(self):
        self.drop_hint.config(text=f"已添加 {len(self.image_list.paths)} 张图片")

    def _write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self):
        if self.running:
            return
        paths = list(self.image_list.paths)
        crop = self.crop_var.get()
        sizes = sorted(s for s, v in self.size_vars.items() if v.get())
        out = self.out_var.get().strip()
        normalize = self.normalize_var.get()
        if not paths:
            messagebox.showwarning(APP_TITLE, "请先添加图片(拖入或点击“选择图片”)。")
            return
        if not sizes:
            messagebox.showwarning(APP_TITLE, "请至少勾选一个输出尺寸。")
            return
        if not out:
            messagebox.showwarning(APP_TITLE, "请填写输出保存路径。")
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.progress.start(12)
        self._write_log(f"开始: {len(paths)} 张图, 裁切类型【{core.CROP_TYPES[crop]}】, "
                        f"尺寸 {sizes}, 统一大小={'开' if normalize else '关'}, 输出到 {out}")
        threading.Thread(target=self._worker, args=(paths, crop, sizes, out, normalize), daemon=True).start()

    def _worker(self, paths, crop, sizes, out, normalize):
        try:
            core.process_batch(paths, crop, sizes, out, normalize=normalize,
                               log=lambda m: self.q.put(("log", m)))
            self.q.put(("done", f"全部完成!结果已保存到:\n{out}"))
        except Exception as e:
            import traceback
            self.q.put(("log", traceback.format_exc()))
            self.q.put(("done", f"处理出错:{e}"))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._write_log(val)
                elif kind == "done":
                    self.running = False
                    self.progress.stop()
                    self.run_btn.config(state="normal")
                    messagebox.showinfo(APP_TITLE, val)
        except queue.Empty:
            pass
        self.after(100, self._poll)


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
    sidebar.add_page("批量图标导出", page)


def main():
    # 打包验证模式:windowed exe 无控制台,自检结果写入 _selftest.txt
    if "--selftest" in sys.argv:
        try:
            ok, msg = core.selftest()
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
