"""HDRI → 天空盒(环境贴图盒):Blender 烘焙 + 4×3 网格切图 + 双版本输出。

移植自 Img2box(run_all.py + split_skybox.py),Blender 路径由用户在界面指定。
输出结构(到用户选择的 out_dir):
    <name>.png                    烘焙 4×3 图
    skybox/right|left|top|bottom|front|back.png    标准 6 面
    skybox_bedwars/<6 面>.png     front/back 互换版
"""
import json
import os
import shutil
import subprocess
import tempfile
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

FACE_NAMES = ["right", "left", "top", "bottom", "front", "back"]
# 4×3 网格编号(从左到右,从上到下):保留 2,5,6,7,8,10 → top,left,front,right,back,bottom
KEEP = {2: "top", 5: "left", 6: "front", 7: "right", 8: "back", 10: "bottom"}
COLS, ROWS = 4, 3
# bedwars 版:front/back 互换
BEDWARS_MAP = {"top": "top", "left": "left", "front": "back",
               "right": "right", "back": "front", "bottom": "bottom"}


def find_blender():
    """探测常见位置的 blender.exe,返回第一个存在的路径;找不到返回空串。"""
    cands = []
    for drive in ("D:", "C:"):
        for ver in ("5.2.0", "5.1.2", "5.0.0", "4.5.0", "4.4.0", "4.3.0"):
            cands.append(Path(f"{drive}\\blender-{ver}-windows-x64\\blender.exe"))
    base = Path("C:/Program Files/Blender Foundation")
    if base.is_dir():
        for sub in sorted(base.iterdir()):
            cands.append(sub / "blender.exe")
    for c in cands:
        if c.exists():
            return str(c)
    return ""


def detect_blender_version(blender_exe):
    """运行 blender --version 取主版本号(用于选对应 .blend 素材);失败返回 None。"""
    try:
        out = subprocess.run([str(blender_exe), "--version"],
                             capture_output=True, text=True, timeout=30).stdout
        for line in out.splitlines():
            for tok in line.split():
                if tok and tok[0].isdigit():
                    return int(tok.split(".")[0])
    except Exception:
        pass
    return None


def pick_blend(major):
    """按 Blender 主版本选素材;无匹配回退通用版。"""
    if major:
        cand = ASSETS_DIR / f"hdri2box_{major}.x.blend"
        if cand.exists():
            return cand
    return ASSETS_DIR / "hdri2box.blend"


def split_faces(baked_png, skybox_dir):
    """4×3 网格裁剪出 6 个面(移植 split_skybox.py)。"""
    from PIL import Image
    img = Image.open(baked_png).convert("RGB")
    w, h = img.size
    cw, ch = w // COLS, h // ROWS
    skybox_dir.mkdir(parents=True, exist_ok=True)
    for num, face in KEEP.items():
        col, row = (num - 1) % COLS, (num - 1) // COLS
        box = (col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)
        img.crop(box).save(skybox_dir / f"{face}.png")


def process(hdri_path, blender_exe, out_dir, log=print, progress=None):
    """HDRI → 天空盒。返回标准 6 面的完整路径列表(供前端预览)。

    progress(stage_text):阶段回调(启动/烘焙/切图),Blender Cycles bake 无逐步百分比。
    """
    hdri = Path(hdri_path)
    if not hdri.exists():
        raise FileNotFoundError(f"输入文件不存在: {hdri}")
    blender = Path(blender_exe)
    if not blender.exists():
        raise FileNotFoundError(f"找不到 Blender: {blender}(请在页面指定 blender.exe 路径)")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="img2box_"))

    def stage(text):
        if progress:
            progress(text)
        log(text)

    try:
        # ── 1. Blender 烘焙 ──
        blend_file = pick_blend(detect_blender_version(blender))
        baked = work / f"{hdri.stem}.png"
        env = {**os.environ,
               "BLENDER_USER_CONFIG": str(work / ".blender_config_tmp"),
               "BLENDER_USER_SCRIPTS": str(work / ".blender_config_tmp")}
        cmd = [str(blender), str(blend_file), "--background",
               "--python", str(ASSETS_DIR / "bake_skybox.py"), "--",
               str(hdri.resolve()), str(baked.resolve())]
        stage("启动 Blender(首次约 10-20 秒)…")
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", env=env)
        stage("烘焙中(Cycles 128 采样,CPU)…")
        for line in proc.stdout:
            line = line.strip()
            # 跳过 Cycles 进度噪音行
            if line and not line.startswith(("Fra:", "Mem:", "Saved:", "Time:")):
                log(line)
        proc.wait(timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"烘焙失败(返回码 {proc.returncode})")
        if not baked.exists():
            raise RuntimeError("烘焙未生成输出文件")

        # ── 2. 切 6 面 ──
        stage("切图…")
        skybox_dir = work / "skybox"
        split_faces(baked, skybox_dir)

        # ── 3. 复制到输出 ──
        shutil.copy2(baked, out / baked.name)
        faces = []
        for face in FACE_NAMES:
            src = skybox_dir / f"{face}.png"
            dst = out / "skybox" / f"{face}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            faces.append(str(dst))
        for src_name, dst_name in BEDWARS_MAP.items():
            dst = out / "skybox_bedwars" / f"{dst_name}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skybox_dir / f"{src_name}.png", dst)
        stage(f"完成: 烘焙图 + 6 面(skybox/)+ 6 面(skybox_bedwars/)→ {out}")
        return faces
    finally:
        shutil.rmtree(work, ignore_errors=True)


class _ViewerHandler(SimpleHTTPRequestHandler):
    """天空盒预览 HTTP 处理器:面图目录 + 可选模型根目录(/models.json、/models/ 路由)。"""

    def __init__(self, *args, models_root=None, **kw):
        self.models_root = models_root
        super().__init__(*args, **kw)

    def do_GET(self):
        if self.path == "/models.json":
            body = json.dumps({
                "ground": _list_models(self.models_root, "ground"),
                "display": _list_models(self.models_root, "display"),
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def translate_path(self, path):
        if self.models_root and path.startswith("/models/"):
            import urllib.parse
            # 必须 unquote:中文文件名经 encodeURIComponent 编码,原版 translate_path 会解码,覆写后需自行处理
            rel = urllib.parse.unquote(path[len("/models/"):]).replace("/", os.sep)
            return os.path.join(self.models_root, rel)
        return super().translate_path(path)


def _list_models(models_root, sub):
    """列出子目录(ground/display)下的模型文件,按名称排序。"""
    if not models_root:
        return []
    d = Path(models_root) / sub
    if not d.is_dir():
        return []
    exts = (".glb", ".gltf", ".obj")
    return sorted(f.name for f in d.iterdir()
                  if f.is_file() and f.name.lower().endswith(exts))


def start_preview(skybox_dir, models_root=None):
    """启动本地 HTTP 服务预览天空盒(浏览器打开),返回 URL。

    服务面图目录本身(6 张 right/left/top/bottom/front/back.png 所在),
    viewer.html 拷入同目录并直接引用面图;models_root 提供 /models.json 列表
    与 /models/ 模型文件路由(地面/展示模型切换)。重复调用会替换旧服务。
    """
    import functools
    import threading
    from http.server import ThreadingHTTPServer

    global _preview_httpd
    skybox = Path(skybox_dir)
    if not skybox.is_dir():
        raise FileNotFoundError(f"目录不存在: {skybox}")
    shutil.copy2(ASSETS_DIR / "viewer.html", skybox / "viewer.html")
    # 本地化 Three.js 库(浏览器离线可用,不依赖 CDN)
    vendor_src = ASSETS_DIR / "vendor"
    if vendor_src.is_dir():
        vendor_dst = skybox / "vendor"
        vendor_dst.mkdir(exist_ok=True)
        for f in vendor_src.iterdir():
            if f.is_file():
                shutil.copy2(f, vendor_dst / f.name)
    if _preview_httpd is not None:
        threading.Thread(target=_preview_httpd.shutdown, daemon=True).start()
    handler = functools.partial(_ViewerHandler, directory=str(skybox),
                                models_root=str(models_root) if models_root else None)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _preview_httpd = httpd
    return f"http://127.0.0.1:{httpd.server_address[1]}/viewer.html"


_preview_httpd = None


def selftest():
    """不依赖 Blender:验证 4×3 网格切图位置正确。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (400, 300), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for num in range(1, 13):  # 每格涂不同红色阶
        col, row = (num - 1) % COLS, (num - 1) // COLS
        d.rectangle([col * 100 + 2, row * 100 + 2, col * 100 + 98, row * 100 + 98],
                    fill=((num * 17) % 256, 0, 0))
    tmp = Path(tempfile.mkdtemp())
    try:
        p = tmp / "t.png"
        img.save(p)
        sd = tmp / "skybox"
        split_faces(p, sd)
        assert all((sd / f"{f}.png").exists() for f in FACE_NAMES), "切图缺失"
        top = Image.open(sd / "top.png")
        assert top.size == (100, 100), top.size
        # 格2 → top,色阶 = 2*17%256 = 34
        assert top.getpixel((50, 50))[0] == 34, top.getpixel((50, 50))
        return True, "OK 切图逻辑正确"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    ok, msg = selftest()
    print("img2box self-check:", msg)
    raise SystemExit(0 if ok else 1)
