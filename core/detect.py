"""UI 元素检测：OmniParser 的 icon_detect 模型（YOLOv8 在 UI 截图上微调）

用途：找出界面上所有"可点击元素"的 bbox——包括那些没有文字标签的图标按钮。
比远端视觉模型快两个数量级（CPU 0.2-0.5s/张）。
"""
import os
import time
from typing import List, Dict, Any, Optional

import numpy as np

_MODEL_CACHE = {}


class Detector:
    def __init__(self, model_path: Optional[str] = None, conf: float = 0.25,
                 imgsz: int = 1280):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "models", "icon_detect.pt")
        self.model_path = model_path
        self.conf = conf
        self.imgsz = imgsz
        self._model = None

    @property
    def model(self):
        if self._model is None:
            if self.model_path not in _MODEL_CACHE:
                from ultralytics import YOLO
                _MODEL_CACHE[self.model_path] = YOLO(self.model_path)
            self._model = _MODEL_CACHE[self.model_path]
        return self._model

    def detect(self, img: np.ndarray, offset: tuple = (0, 0),
               min_size: int = 8, max_size: int = 400) -> List[Dict[str, Any]]:
        """检测 UI 元素

        img    : RGB ndarray（或 PIL 转过来的）
        offset : 该图左上角在屏幕上的绝对坐标
        min_size/max_size: 过滤掉太小（噪点）和太大（整块背景）的框

        返回：[{bbox:[x,y,w,h], center:[cx,cy], conf, cls, area}, ...]
        bbox/center 都是**屏幕绝对坐标**
        """
        ox, oy = offset
        t0 = time.time()
        results = self.model.predict(img, conf=self.conf, imgsz=self.imgsz,
                                     verbose=False, device="cpu")[0]
        elapsed = (time.time() - t0) * 1000

        out = []
        for b in results.boxes:
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
            w, h = x2 - x1, y2 - y1
            if w < min_size or h < min_size:
                continue
            if w > max_size or h > max_size:
                continue
            out.append({
                "bbox": [int(x1) + ox, int(y1) + oy, int(w), int(h)],
                "center": [int((x1 + x2) / 2) + ox, int((y1 + y2) / 2) + oy],
                "conf": round(float(b.conf[0]), 3),
                "cls": int(b.cls[0]),
                "area": int(w * h),
            })

        out.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))
        return out, elapsed

    def detect_and_annotate(self, img: np.ndarray, offset=(0, 0), **kw):
        """检测并返回可直接用 capture.annotate 的点列表"""
        els, ms = self.detect(img, offset=offset, **kw)
        points = []
        for i, e in enumerate(els):
            points.append({
                "x": e["center"][0], "y": e["center"][1],
                "label": f"{i+1}",
                "bbox": e["bbox"],
                "color": (0, 130, 255),
            })
        return points, els, ms
