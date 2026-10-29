"""OCR 元素定位：RapidOCR（ONNX，不依赖 torch）

解决"有文字但拿不到 DOM/XPath"的场景：
  - 桌面应用的按钮（LibreOffice 菜单、系统对话框）
  - Canvas/图片里的按钮
  - 跨 iframe 的元素

实测 1920x1080: 3.7s / 77 块（全屏）
只 OCR 目标区域可压到 300-600ms。
"""
import time
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


class OcrDetector:
    def __init__(self, min_conf: float = 0.5):
        self.min_conf = min_conf

    def detect(self, img: np.ndarray, offset: Tuple[int, int] = (0, 0),
               min_conf: Optional[float] = None) -> Tuple[List[Dict[str, Any]], float]:
        """OCR 识别

        返回 (items, elapsed_ms)
        items: [{'text':.., 'conf':.., 'bbox':[x,y,w,h], 'center':[cx,cy]}]
               坐标已加 offset（屏幕绝对坐标）
        """
        t0 = time.time()
        ocr = _engine()
        result, _ = ocr(img)
        ms = (time.time() - t0) * 1000

        th = min_conf if min_conf is not None else self.min_conf
        ox, oy = offset
        items = []
        for r in (result or []):
            try:
                box, text, conf = r[0], r[1], float(r[2])
            except (IndexError, TypeError, ValueError):
                continue
            if conf < th:
                continue
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            items.append({
                "text": str(text),
                "conf": round(conf, 3),
                "bbox": [int(x1) + ox, int(y1) + oy, int(x2 - x1), int(y2 - y1)],
                "center": [int((x1 + x2) / 2) + ox, int((y1 + y2) / 2) + oy],
            })
        items.sort(key=lambda e: (e["bbox"][1] // 15, e["bbox"][0]))
        return items, ms

    def find(self, img: np.ndarray, keyword: str, offset=(0, 0),
             exact: bool = False, min_conf: Optional[float] = None) -> List[Dict[str, Any]]:
        """按关键词找元素（模糊匹配包含关系）"""
        items, _ = self.detect(img, offset=offset, min_conf=min_conf)
        kw = keyword.strip().lower()
        out = []
        for it in items:
            t = it["text"].strip().lower()
            if (t == kw) if exact else (kw in t):
                out.append(it)
        return out


def to_points(items: List[Dict[str, Any]], color=(0, 160, 90)) -> List[Dict[str, Any]]:
    """转成 capture.annotate 的点列表（标签用文字内容）"""
    pts = []
    for i, it in enumerate(items):
        pts.append({
            "x": it["center"][0], "y": it["center"][1],
            "label": it["text"][:20],
            "bbox": it["bbox"],
            "color": color,
        })
    return pts
