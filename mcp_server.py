"""linux-cua-mcp — Linux 桌面操控 MCP Server

能力：
  - 平滑移动（贝塞尔 + 变速 + 拟人抖动）
  - 内核级点击/拖拽/键盘（绕过滤）
  - 区域截图 + 网格 + 坐标标注
  - 多点序列操作（一次调用完成多步）

运行：DISPLAY=:0 venv/bin/python mcp_server.py
"""
import os
import time
import base64
import io
import json
from typing import Optional, List, Dict, Any

from fastmcp import FastMCP

from core.input import Mouse, Keyboard
from core.capture import Capture

# ---- 全局单例（MCP 常驻进程）----
_mouse: Optional[Mouse] = None
_kbd: Optional[Keyboard] = None
_cap: Optional[Capture] = None


def mouse() -> Mouse:
    global _mouse
    if _mouse is None:
        _mouse = Mouse()
    return _mouse


def kbd() -> Keyboard:
    global _kbd
    if _kbd is None:
        _kbd = Keyboard()
    return _kbd


def cap() -> Capture:
    global _cap
    if _cap is None:
        _cap = Capture()
    return _cap


def _b64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


app = FastMCP("linux-cua")


# ============ 感知 ============
@app.tool()
def screenshot(
    left: Optional[int] = None, top: Optional[int] = None,
    width: Optional[int] = None, height: Optional[int] = None,
    grid: bool = False, grid_step: int = 50, grid_major: int = 100,
    annotate_points: Optional[List[Dict[str, Any]]] = None,
    save_to: Optional[str] = None,
) -> Dict[str, Any]:
    """截屏。可指定区域、叠加网格（带绝对坐标）、标注点。

    annotate_points: [{"x":400,"y":300,"label":"P1","color":[0,120,255]}, ...]
    save_to: 可选，保存到本地路径
    返回：base64 PNG + 尺寸 + 区域偏移
    """
    c = cap()
    region = None
    if None not in (left, top, width, height):
        region = (left, top, width, height)
    img = c.grab(region)
    ox, oy = (region[0], region[1]) if region else (0, 0)

    if grid:
        img = c.draw_grid(img, step=grid_step, major=grid_major, offset=(ox, oy))
    if annotate_points:
        img = c.annotate(img, annotate_points, offset=(ox, oy))
    if save_to:
        c.save(img, save_to)

    return {
        "image_base64": _b64(img),
        "width": img.size[0], "height": img.size[1],
        "offset": [ox, oy],
        "screen": [c.screen_w, c.screen_h],
        "saved_to": save_to,
    }


@app.tool()
def get_cursor_position() -> Dict[str, int]:
    """当前光标屏幕坐标"""
    x, y = mouse().pos()
    return {"x": x, "y": y}


@app.tool()
def get_screen_size() -> Dict[str, int]:
    c = cap()
    return {"width": c.screen_w, "height": c.screen_h}


# ============ 动作 ============
@app.tool()
def move_to(x: int, y: int, duration: float = 0.55, curve: float = 0.28,
            jitter: float = 0.9, ease: str = "smooth") -> Dict[str, Any]:
    """平滑移动光标到 (x, y)。贝塞尔曲线 + 变速 + 拟人抖动。

    duration: 秒（0.4-0.9 最像人，太快像瞬移）
    curve: 0=直线，0.3=明显弧线
    ease: smooth / linear / ease_out
    """
    m = mouse()
    m.move_to(x, y, duration=duration, curve=curve, jitter=jitter, ease=ease)
    return {"ok": True, "position": m.pos()}


@app.tool()
def click(x: Optional[int] = None, y: Optional[int] = None,
          button: str = "left", count: int = 1, move_first: bool = True,
          duration: float = 0.5) -> Dict[str, Any]:
    """点击。不传 x/y 则原地点击。

    button: left / right / middle
    count: 1=单击 2=双击
    """
    from evdev import ecodes as e
    bmap = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
    b = bmap.get(button.lower(), e.BTN_LEFT)
    m = mouse()
    m.click(x, y, button=b, n=count, move=move_first, duration=duration)
    return {"ok": True, "position": m.pos(), "button": button, "count": count}


@app.tool()
def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 1.0,
         hold: float = 0.12, release_delay: float = 0.18) -> Dict[str, Any]:
    """拖拽：按住 → 平滑拖到目标 → 停顿 → 松开。

    release_delay 是滑块验证的关键（机器特征就是缺这一下）
    """
    m = mouse()
    m.drag(x1, y1, x2, y2, duration=duration, hold=hold, release_delay=release_delay)
    return {"ok": True, "position": m.pos()}


@app.tool()
def scroll(clicks: int = 3, direction: str = "down") -> Dict[str, Any]:
    """滚轮。clicks 为格数，direction: up / down"""
    d = 1 if direction.lower() == "down" else -1
    mouse().scroll(clicks, d)
    return {"ok": True}


@app.tool()
def type_text(text: str, wpm: int = 320) -> Dict[str, Any]:
    """键盘输入 ASCII 文本。中文请用 xdotool（走 fcitx）"""
    kbd().type(text, wpm=wpm)
    return {"ok": True, "length": len(text)}


@app.tool()
def press_key(name: str) -> Dict[str, Any]:
    """按单键：enter / esc / tab / backspace / delete / up / down / left / right / home / end"""
    kbd().key(name)
    return {"ok": True, "key": name}


@app.tool()
def hotkey(keys: List[str]) -> Dict[str, Any]:
    """组合键，如 ["ctrl","c"]"""
    kbd().combo(*keys)
    return {"ok": True, "keys": keys}


@app.tool()
def do_sequence(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """一次性执行多步操作（不用来回调工具）。

    steps 示例：
    [
      {"action":"move","x":500,"y":300,"duration":0.5},
      {"action":"click"},
      {"action":"wait","seconds":0.4},
      {"action":"type","text":"hello"},
      {"action":"key","name":"enter"},
      {"action":"drag","x1":100,"y1":500,"x2":400,"y2":500},
      {"action":"scroll","clicks":3,"direction":"down"}
    ]
    """
    m, k = mouse(), kbd()
    log = []
    for i, s in enumerate(steps):
        act = s.get("action")
        try:
            if act == "move":
                m.move_to(s["x"], s["y"], duration=s.get("duration", 0.5),
                          curve=s.get("curve", 0.28))
                log.append(f"{i}:move({s['x']},{s['y']})")
            elif act == "click":
                from evdev import ecodes as e
                bmap = {"left": e.BTN_LEFT, "right": e.BTN_RIGHT, "middle": e.BTN_MIDDLE}
                b = bmap.get(s.get("button", "left"), e.BTN_LEFT)
                m.click(s.get("x"), s.get("y"), button=b, n=s.get("count", 1),
                        move=s.get("x") is not None)
                log.append(f"{i}:click")
            elif act == "drag":
                m.drag(s["x1"], s["y1"], s["x2"], s["y2"],
                       duration=s.get("duration", 1.0))
                log.append(f"{i}:drag")
            elif act == "type":
                k.type(s["text"], wpm=s.get("wpm", 320))
                log.append(f"{i}:type({len(s['text'])})")
            elif act == "key":
                k.key(s["name"])
                log.append(f"{i}:key({s['name']})")
            elif act == "hotkey":
                k.combo(*s["keys"])
                log.append(f"{i}:hotkey")
            elif act == "scroll":
                m.scroll(s.get("clicks", 3), 1 if s.get("direction", "down") == "down" else -1)
                log.append(f"{i}:scroll")
            elif act == "wait":
                time.sleep(s.get("seconds", 0.3))
                log.append(f"{i}:wait")
            else:
                log.append(f"{i}:unknown({act})")
        except Exception as ex:
            log.append(f"{i}:ERROR {type(ex).__name__} {ex}")
    return {"ok": True, "executed": len(steps), "log": log, "position": m.pos()}


@app.tool()
def ocr_screen(
    left: Optional[int] = None, top: Optional[int] = None,
    width: Optional[int] = None, height: Optional[int] = None,
    min_conf: float = 0.5,
) -> Dict[str, Any]:
    """OCR 识别屏幕上的所有文字 + 坐标（RapidOCR，本地 ONNX，不依赖 torch）

    用于：桌面应用按钮、Canvas/图片里的文字、跨 iframe 的元素。
    实测全屏 1080p 约 3.7s；只 OCR 区域会快得多。

    返回：[{text, conf, bbox:[x,y,w,h], center:[cx,cy]}]，坐标为屏幕绝对坐标
    """
    from core.ocr import OcrDetector
    c = cap()
    region = None
    if None not in (left, top, width, height):
        region = (left, top, width, height)
    img = c.grab_rgb_array(region)
    ox, oy = (region[0], region[1]) if region else (0, 0)
    items, ms = OcrDetector().detect(img, offset=(ox, oy), min_conf=min_conf)
    return {"ok": True, "count": len(items), "elapsed_ms": round(ms),
            "items": items}


@app.tool()
def find_text(
    keyword: str, exact: bool = False, min_conf: float = 0.5,
    left: Optional[int] = None, top: Optional[int] = None,
    width: Optional[int] = None, height: Optional[int] = None,
    annotate: bool = False,
) -> Dict[str, Any]:
    """按文字内容找元素位置（OCR）。

    keyword: 要找的文字，如"新建文件夹""提交"。exact=True 时要求完全匹配。
    annotate: 是否返回标注好的截图（base64）

    返回匹配项列表，每项含 bbox/center（屏幕绝对坐标），可直接喂给 click()
    """
    from core.ocr import OcrDetector, to_points
    c = cap()
    region = None
    if None not in (left, top, width, height):
        region = (left, top, width, height)
    img_arr = c.grab_rgb_array(region)
    ox, oy = (region[0], region[1]) if region else (0, 0)
    matches = OcrDetector().find(img_arr, keyword, offset=(ox, oy),
                                 exact=exact, min_conf=min_conf)
    out: Dict[str, Any] = {"ok": True, "keyword": keyword, "count": len(matches),
                           "matches": matches}
    if annotate and matches:
        pts = to_points(matches)
        im = c.annotate(c.grab(region), pts, offset=(ox, oy))
        out["image_base64"] = _b64(im)
    return out


if __name__ == "__main__":
    app.run()
