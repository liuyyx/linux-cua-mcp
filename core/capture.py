"""截图层：区域截取、网格标注、坐标可视化"""
import io
import os
from typing import Optional, Tuple, List, Dict, Any

import mss
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size=14):
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size, index=0)
            except Exception:
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
    return ImageFont.load_default()


class Capture:
    def __init__(self):
        self.sct = mss.mss()
        self.mon = self.sct.monitors[1]      # 主屏
        self.screen_w = self.mon["width"]
        self.screen_h = self.mon["height"]

    # ---------- 截图 ----------
    def grab(self, region: Optional[Tuple[int, int, int, int]] = None) -> Image.Image:
        """region = (left, top, width, height)，None = 全屏"""
        if region is None:
            mon = self.mon
        else:
            l, t, w, h = region
            mon = {"left": l, "top": t, "width": w, "height": h}
        raw = self.sct.grab(mon)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    def grab_rgb_array(self, region=None) -> np.ndarray:
        return np.array(self.grab(region))

    # ---------- 网格 ----------
    def draw_grid(self, img: Image.Image, step: int = 50, major: int = 100,
                  offset: Tuple[int, int] = (0, 0), labels: bool = True) -> Image.Image:
        """画网格。offset = 该图左上角在屏幕上的绝对坐标（用于标注真实坐标）"""
        im = img.copy()
        d = ImageDraw.Draw(im, "RGBA")
        w, h = im.size
        ox, oy = offset
        f = _font(11)

        # 细线
        for x in range(0, w, step):
            if x % major == 0:
                continue
            d.line([(x, 0), (x, h)], fill=(0, 0, 0, 26), width=1)
        for y in range(0, h, step):
            if y % major == 0:
                continue
            d.line([(0, y), (w, y)], fill=(0, 0, 0, 26), width=1)

        # 粗线 + 坐标
        for x in range(0, w, major):
            d.line([(x, 0), (x, h)], fill=(220, 60, 40, 120), width=1)
            if labels:
                d.text((x + 2, 2), str(x + ox), font=f, fill=(180, 30, 20, 230))
        for y in range(0, h, major):
            d.line([(0, y), (w, y)], fill=(220, 60, 40, 120), width=1)
            if labels:
                d.text((2, y + 1), str(y + oy), font=f, fill=(180, 30, 20, 230))
        return im

    # ---------- 标点 ----------
    def annotate(self, img: Image.Image, points: List[Dict[str, Any]],
                 offset: Tuple[int, int] = (0, 0), crosshair: bool = True) -> Image.Image:
        """points = [{'x':.., 'y':.., 'label':'..', 'color':(r,g,b), 'bbox':[x,y,w,h]}, ...]"""
        im = img.copy()
        d = ImageDraw.Draw(im, "RGBA")
        ox, oy = offset
        f = _font(13)

        for i, p in enumerate(points):
            x = p["x"] - ox
            y = p["y"] - oy
            color = p.get("color", (0, 120, 255))
            label = p.get("label", str(i))
            bbox = p.get("bbox")

            if bbox:
                bx, by, bw, bh = bbox
                d.rectangle([bx - ox, by - oy, bx - ox + bw, by - oy + bh],
                            outline=color + (200,) if len(color) == 3 else color, width=2)

            if crosshair:
                d.line([(x - 9, y), (x + 9, y)], fill=color, width=2)
                d.line([(x, y - 9), (x, y + 9)], fill=color, width=2)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=color, outline=(255, 255, 255))

            txt = f"{label}"
            try:
                tw = d.textlength(txt, font=f)
            except Exception:
                tw = len(txt) * 7
            pad = 3
            d.rectangle([x + 8, y - 10, x + 8 + tw + pad * 2, y + 8],
                        fill=(0, 0, 0, 175))
            d.text((x + 8 + pad, y - 9), txt, font=f, fill=(255, 255, 255))
        return im

    # ---------- 存盘 ----------
    def save(self, img: Image.Image, path: str, quality=92):
        os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
        if path.lower().endswith(".png"):
            img.save(path)
        else:
            img.save(path, quality=quality)
        return path


def hex_to_rgb(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
