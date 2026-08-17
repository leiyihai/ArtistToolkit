"""打包完整性校验:检查新增功能后的登记点,防止打包漏功能。

build.bat 打包前调用;任一登记点缺失即报错退出。
登记点(docs/new-tab-guide.md):
  1. shell.js FEATURES 数组登记页签
  2. tools/<name>/frontend/view.js 存在
  3. backend.py 已 import tools.<name>.core(命令可达)
  4. (非 .py 资源由人确认 spec datas / build.bat,脚本仅提示)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def read_features():
    shell = open(os.path.join(ROOT, "app", "renderer", "shell.js"), encoding="utf-8").read()
    m = re.search(r"const FEATURES = \[(.*?)\];", shell, re.S)
    if not m:
        raise SystemExit("shell.js 中找不到 FEATURES 数组")
    return re.findall(r"'([^']+)'", m.group(1))


def main():
    errors = []
    features = read_features()
    backend = open(os.path.join(ROOT, "backend.py"), encoding="utf-8").read()

    for name in features:
        if not os.path.exists(os.path.join(ROOT, "tools", name, "frontend", "view.js")):
            errors.append(f"FEATURES 登记了 '{name}' 但缺 tools/{name}/frontend/view.js")
        if f"from tools.{name}.core import" not in backend:
            errors.append(f"backend.py 未 import tools.{name}.core → 该功能页运行时报「未知命令」")

    for d in sorted(os.listdir(os.path.join(ROOT, "tools"))):
        full = os.path.join(ROOT, "tools", d)
        if not os.path.isdir(full) or d.startswith("__"):
            continue
        if d not in features:
            errors.append(f"tools/{d} 存在但未在 shell.js FEATURES 登记 → 侧边栏不出现页签")

    if errors:
        print("!! 打包完整性检查失败,修复以下登记点后重试:")
        for e in errors:
            print("  -", e)
        sys.exit(1)

    print(f"打包完整性检查通过:{len(features)} 个功能登记完整({', '.join(features)})")
    # 提示:功能带非 .py 资源(assets/models)时,须确认已在
    #   ArtistToolkit-backend.spec 的 datas / build.bat 的 extra-resource 中登记。
    print("提示:如新增功能带 assets/models 等非 .py 资源,请确认 spec datas 与 build.bat 已包含。")


if __name__ == "__main__":
    main()
