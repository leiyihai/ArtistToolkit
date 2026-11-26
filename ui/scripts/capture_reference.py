"""通过 DevTools 协议给 Electron 版界面逐页截图,作为 GPUI 还原的视觉基准。

用法:
    # 1) 启动带调试端口的 Electron(注意:环境里的 ELECTRON_RUN_AS_NODE 要先去掉)
    cd app
    .\\node_modules\\electron\\dist\\electron.exe . --remote-debugging-port=9222 --remote-allow-origins=*
    # 2) 再运行本脚本
    python ui/scripts/capture_reference.py
"""
import base64
import json
import os
import sys
import time
import urllib.request

import websocket

PORT = 9222
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "reference")

# 侧边栏顺序来自 features.js:0 智能抠图 / 1 特效抠图 / 2 图集拆分 / 3 快捷尺寸 / 4 天空盒烘焙
PAGES = [
    ("ai-matting", 0),
    ("unmult", 1),
    ("icon-export", 2),
    ("image-resize", 3),
    ("img2box", 4),
]


def page_ws_url():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10) as resp:
        targets = json.load(resp)
    for target in targets:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return target["webSocketDebuggerUrl"]
    raise SystemExit("找不到页面调试目标")


class Cdp:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=20, suppress_origin=True)
        self.next_id = 1

    def call(self, method, **params):
        msg_id = self.next_id
        self.next_id += 1
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == msg_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression):
        result = self.call("Runtime.evaluate", expression=expression, returnByValue=True,
                           awaitPromise=True)
        return result.get("result", {}).get("value")

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(data))


def main():
    os.makedirs(OUT, exist_ok=True)
    cdp = Cdp(page_ws_url())
    cdp.call("Page.enable")
    cdp.call("Runtime.enable")
    time.sleep(1)

    titles = cdp.evaluate(
        "Array.from(document.querySelectorAll('.nav-btn')).map(b => b.textContent.trim())"
    )
    print("nav titles:", titles)

    for page_id, index in PAGES:
        click = (
            "(function(){const bs=document.querySelectorAll('.nav-btn');"
            f"if(!bs[{index}])return false;bs[{index}].click();return true;}})()"
        )
        if not cdp.evaluate(click):
            print(f"skip {page_id} (missing nav index {index})")
            continue
        time.sleep(1.5)
        path = os.path.join(OUT, f"electron-{page_id}.png")
        cdp.screenshot(path)
        print("saved", os.path.relpath(path, os.getcwd()))

    cdp.ws.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
